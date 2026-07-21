#!/usr/bin/env python3
"""Install WishGraph project-local hooks without replacing existing hooks."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Optional


SKILL_ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = SKILL_ROOT / "assets" / "hooks"
CLAUDE_AGENT_ASSET = (
    SKILL_ROOT / "assets" / "claude-agents" / "wishgraph-worker.md"
)
CLAUDE_AGENT_RELATIVE_PATH = Path(".claude/agents/wishgraph-worker.md")
CLAUDE_AGENT_MARKER = "<!-- wishgraph-managed: wishgraph-worker -->"
CODEX_AGENT_ASSET = (
    SKILL_ROOT / "assets" / "codex-agents" / "wishgraph-worker.toml"
)
CODEX_AGENT_RELATIVE_PATH = Path(".codex/agents/wishgraph-worker.toml")
CODEX_AGENT_MARKER = "# wishgraph-managed: wishgraph-worker"
RUNTIME_FILES = (
    "memory_sync.py",
    "git_state.py",
    "workflow_state.py",
    "policy.py",
    "host_adapter.py",
    "codex_worker_provider.py",
    "claude_worker_provider.py",
    "tool_gate_provider.py",
)
RUNTIME_MANIFEST_NAME = "runtime-manifest.json"
HOST_OBSERVATION_EVENTS = ("session-start", "user-prompt-submit")
RECENT_HOST_OBSERVATION_SECONDS = 120
KNOWN_HOSTS = ("codex", "claude")
KNOWN_HOST_SURFACES = ("unknown", "codex-cli", "codex-desktop", "claude-cli")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Cannot merge invalid JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def write_bytes_atomic(path: Path, data: bytes, mode: Optional[int] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if mode is not None:
            os.chmod(temp_name, mode)
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _windows_git_candidates() -> list[Path]:
    candidates: list[Path] = []
    for environment_name, suffix in (
        ("ProgramFiles", "Git/cmd/git.exe"),
        ("ProgramFiles(x86)", "Git/cmd/git.exe"),
        ("LOCALAPPDATA", "Programs/Git/cmd/git.exe"),
    ):
        base = os.environ.get(environment_name)
        if base:
            candidates.append(Path(base) / suffix)
    return candidates


def git_preflight_diagnosis(
    *,
    platform_name: str = os.name,
    windows_candidates: Optional[list[Path]] = None,
) -> dict[str, str]:
    available = shutil.which("git")
    if available:
        return {"state": "available", "path": str(Path(available).resolve())}
    if platform_name == "nt":
        for candidate in windows_candidates or _windows_git_candidates():
            if candidate.is_file():
                return {"state": "stale_path", "path": str(candidate.resolve())}
    return {"state": "missing", "path": ""}


def snapshot_files(paths: list[Path]) -> dict[Path, tuple[bool, bytes, int]]:
    snapshot: dict[Path, tuple[bool, bytes, int]] = {}
    for path in paths:
        if path.is_file():
            snapshot[path] = (True, path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
        else:
            snapshot[path] = (False, b"", 0)
    return snapshot


def restore_snapshot(snapshot: dict[Path, tuple[bool, bytes, int]]) -> None:
    failures: list[str] = []
    for path, (existed, data, mode) in snapshot.items():
        try:
            if existed:
                write_bytes_atomic(path, data, mode)
            elif path.exists():
                path.unlink()
        except OSError as exc:
            failures.append(f"{path}: {exc}")
    if failures:
        raise OSError("WishGraph rollback failed: " + "; ".join(failures))


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def sha256_file(path: Path) -> str:
    # Git may materialize the bundled Python runtime with CRLF on Windows.
    # Fingerprints describe generated source content, so canonicalize only that
    # platform newline difference while preserving every other byte.
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def validate_runtime_manifest(value: dict[str, Any], *, source: str) -> dict[str, Any]:
    if value.get("schema_version") != 1:
        raise ValueError(f"{source} must use runtime manifest schema_version 1")
    version = value.get("runtime_version")
    files = value.get("files")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError(f"{source} runtime_version must be a positive integer")
    if not isinstance(files, dict) or set(files) != set(RUNTIME_FILES):
        raise ValueError(f"{source} files must list exactly the generated runtime files")
    if any(
        not isinstance(name, str)
        or not isinstance(digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
        for name, digest in files.items()
    ):
        raise ValueError(f"{source} contains an invalid SHA-256 fingerprint")
    known_versions = value.get("known_versions", {})
    if not isinstance(known_versions, dict):
        raise ValueError(f"{source} known_versions must be a JSON object")
    for known_version, fingerprints in known_versions.items():
        if not str(known_version).isdigit() or not isinstance(fingerprints, dict):
            raise ValueError(f"{source} contains an invalid known runtime version")
        if set(fingerprints) != set(RUNTIME_FILES) or any(
            not isinstance(digest, str)
            or (digest != "" and not re.fullmatch(r"[0-9a-f]{64}", digest))
            for digest in fingerprints.values()
        ):
            raise ValueError(f"{source} contains invalid known-version fingerprints")
    return value


def bundled_runtime_manifest() -> dict[str, Any]:
    path = ASSET_ROOT / RUNTIME_MANIFEST_NAME
    manifest = validate_runtime_manifest(read_json(path), source=str(path))
    actual = {name: sha256_file(ASSET_ROOT / name) for name in RUNTIME_FILES}
    if actual != manifest["files"]:
        raise ValueError("Bundled WishGraph runtime files do not match runtime-manifest.json")
    return manifest


def installed_runtime_hashes(target: Path) -> dict[str, str]:
    hook_dir = target / ".wishgraph" / "hooks"
    return {
        name: sha256_file(hook_dir / name) if (hook_dir / name).is_file() else ""
        for name in RUNTIME_FILES
    }


def fingerprints_match(actual: dict[str, str], expected: Any) -> bool:
    return isinstance(expected, dict) and all(
        actual.get(name) == expected.get(name) for name in RUNTIME_FILES
    )


def runtime_diagnosis(target: Path) -> dict[str, Any]:
    hook_dir = target / ".wishgraph" / "hooks"
    try:
        bundled_manifest = bundled_runtime_manifest()
    except ValueError as exc:
        return {
            "state": "bundled_invalid",
            "safe_to_upgrade": False,
            "error": str(exc),
            "files": {},
        }
    bundled_version = int(bundled_manifest["runtime_version"])
    actual_hashes = installed_runtime_hashes(target)
    files: dict[str, dict[str, Any]] = {}
    for name in RUNTIME_FILES:
        installed = hook_dir / name
        installed_hash = actual_hashes[name]
        bundled_hash = bundled_manifest["files"][name]
        files[name] = {
            "installed": installed.is_file(),
            "matches_bundled": installed_hash == bundled_hash,
            "installed_sha256": installed_hash,
            "bundled_sha256": bundled_hash,
        }
    installed_count = sum(1 for item in files.values() if item["installed"])
    installed_manifest_path = hook_dir / RUNTIME_MANIFEST_NAME
    installed_manifest: dict[str, Any] = {}
    installed_manifest_error = ""
    if installed_manifest_path.is_file():
        try:
            installed_manifest = validate_runtime_manifest(
                read_json(installed_manifest_path), source=str(installed_manifest_path)
            )
        except ValueError as exc:
            installed_manifest_error = str(exc)

    installed_version: Optional[int] = None
    if installed_manifest:
        installed_version = int(installed_manifest["runtime_version"])
    installed_manifest_matches = bool(installed_manifest) and fingerprints_match(
        actual_hashes, installed_manifest.get("files")
    )
    current_matches = fingerprints_match(actual_hashes, bundled_manifest["files"])
    known_version = ""
    for version, fingerprints in bundled_manifest.get("known_versions", {}).items():
        if fingerprints_match(actual_hashes, fingerprints):
            known_version = str(version)
            break

    if installed_count == 0:
        state = "missing"
        safe_to_upgrade = False
    elif current_matches:
        if installed_manifest_matches and installed_version == bundled_version:
            state = "current"
            safe_to_upgrade = False
        else:
            state = "metadata_missing"
            safe_to_upgrade = True
            installed_version = bundled_version
    elif known_version:
        installed_version = int(known_version)
        if installed_version < bundled_version:
            state = "upgrade_available"
            safe_to_upgrade = True
        elif installed_version > bundled_version:
            state = "newer_than_bundled"
            safe_to_upgrade = False
        else:
            state = "version_conflict"
            safe_to_upgrade = False
    elif installed_count != len(RUNTIME_FILES):
        state = "incomplete"
        safe_to_upgrade = False
    elif (
        installed_manifest_matches
        and installed_version is not None
        and installed_version > bundled_version
    ):
        state = "newer_than_bundled"
        safe_to_upgrade = False
    else:
        state = "modified"
        safe_to_upgrade = False
    return {
        "state": state,
        "safe_to_upgrade": safe_to_upgrade,
        "bundled_runtime_version": bundled_version,
        "installed_runtime_version": installed_version,
        "installed_manifest": {
            "path": str(installed_manifest_path),
            "present": installed_manifest_path.is_file(),
            "valid": bool(installed_manifest),
            "matches_installed_files": installed_manifest_matches,
            "error": installed_manifest_error,
        },
        "missing_files": [
            name for name, item in files.items() if not item["installed"]
        ],
        "non_bundled_files": [
            name
            for name, item in files.items()
            if item["installed"] and not item["matches_bundled"]
        ],
        "files": files,
    }


def contains_wishgraph_handler(value: Any) -> bool:
    if isinstance(value, dict):
        return any(contains_wishgraph_handler(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_wishgraph_handler(item) for item in value)
    return isinstance(value, str) and ".wishgraph/hooks/memory_sync.py" in value.replace(
        "\\", "/"
    )


def normalize_required_hosts(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(
            "required_hosts must be a non-empty array; use mode off instead"
        )
    if not all(isinstance(item, str) for item in value):
        raise ValueError("required_hosts entries must be strings")
    unknown = sorted(set(value) - set(KNOWN_HOSTS))
    if unknown:
        raise ValueError(
            "required_hosts contains unknown hosts: " + ", ".join(unknown)
        )
    selected = set(value)
    return [host for host in KNOWN_HOSTS if host in selected]


def validate_config_paths(config: dict[str, Any]) -> None:
    """Apply the runtime's repository-relative path boundary before activation."""
    paths = config.get("paths")
    if not isinstance(paths, dict):
        raise ValueError("paths must be a JSON object")

    def validate(value: Any, field: str) -> None:
        raw = str(value or "").strip().replace("\\", "/")
        if (
            not raw
            or raw.startswith(("/", "//"))
            or re.match(r"^[A-Za-z]:", raw)
            or any(part in {"", ".", ".."} for part in raw.split("/"))
            or (
                PurePosixPath(raw).parts
                and PurePosixPath(raw).parts[0].lower() == ".git"
            )
        ):
            raise ValueError(
                f"invalid paths.{field}: path must stay inside the repository"
            )

    for name in (
        "prd",
        "architecture",
        "codemap",
        "conventions",
        "project_status",
        "task_glob",
        "revision_glob",
        "run_report_glob",
    ):
        validate(paths.get(name), name)
    task_globs = paths.get("task_globs")
    if not isinstance(task_globs, list) or not task_globs:
        raise ValueError("paths.task_globs must be a non-empty array")
    for value in task_globs:
        validate(value, "task_globs")
    template = paths.get("run_report_template")
    if not isinstance(template, str) or not template:
        raise ValueError("paths.run_report_template must be a non-empty string")
    try:
        allocated = template.format(work_unit_id="001", attempt=1)
    except (KeyError, ValueError) as exc:
        raise ValueError("invalid paths.run_report_template placeholders") from exc
    validate(allocated, "run_report_template")


def hosts_for_selection(selection: str) -> list[str]:
    return list(KNOWN_HOSTS) if selection == "all" else [selection]


def host_config_path(target: Path, host: str) -> Path:
    if host == "codex":
        return target / ".codex" / "hooks.json"
    return target / ".claude" / "settings.json"


def host_asset_path(host: str) -> Path:
    return ASSET_ROOT / ("codex-hooks.json" if host == "codex" else "claude-settings.json")


def materialized_claude_worker_agent(python_executable: str) -> bytes:
    text = CLAUDE_AGENT_ASSET.read_text(encoding="utf-8")
    resolved = str(Path(python_executable).resolve())
    if os.name == "nt":
        escaped = resolved.replace("'", "''")
        python_command = f"& '{escaped}'"
    else:
        python_command = shlex.quote(resolved)
    return text.replace(
        "python3 .wishgraph/hooks/memory_sync.py",
        f"{python_command} .wishgraph/hooks/memory_sync.py",
    ).encode("utf-8")


def claude_worker_agent_diagnosis(
    target: Path, python_executable: str = sys.executable
) -> dict[str, Any]:
    path = target / CLAUDE_AGENT_RELATIVE_PATH
    if not path.is_file():
        return {"path": str(path), "state": "missing"}
    try:
        installed = path.read_bytes().replace(b"\r\n", b"\n")
        bundled = materialized_claude_worker_agent(python_executable).replace(
            b"\r\n", b"\n"
        )
    except OSError as exc:
        return {"path": str(path), "state": "invalid", "detail": str(exc)}
    if installed == bundled:
        return {"path": str(path), "state": "current"}
    text = installed.decode("utf-8", errors="replace")
    return {
        "path": str(path),
        "state": "outdated" if CLAUDE_AGENT_MARKER in text else "conflict",
    }


def codex_worker_agent_diagnosis(target: Path) -> dict[str, Any]:
    path = target / CODEX_AGENT_RELATIVE_PATH
    if not path.is_file():
        return {"path": str(path), "state": "missing"}
    try:
        installed = path.read_bytes().replace(b"\r\n", b"\n")
        bundled = CODEX_AGENT_ASSET.read_bytes().replace(b"\r\n", b"\n")
    except OSError as exc:
        return {"path": str(path), "state": "invalid", "detail": str(exc)}
    if installed == bundled:
        return {"path": str(path), "state": "current"}
    text = installed.decode("utf-8", errors="replace")
    return {
        "path": str(path),
        "state": "outdated" if CODEX_AGENT_MARKER in text else "conflict",
    }


def expected_host_groups(
    target: Path, host: str, python_executable: str
) -> dict[str, set[str]]:
    incoming = _materialize_python_commands(
        read_json(host_asset_path(host)),
        python_executable,
        claude_powershell=host == "claude" and os.name == "nt",
        runtime_path=target / ".wishgraph" / "hooks" / "memory_sync.py",
    )
    return {
        event: {
            json.dumps(group, sort_keys=True, separators=(",", ":")) for group in groups
        }
        for event, groups in incoming.get("hooks", {}).items()
        if isinstance(groups, list)
    }


def host_adapter_diagnosis(
    target: Path, host: str, python_executable: str
) -> dict[str, Any]:
    path = host_config_path(target, host)
    worker_agent = (
        claude_worker_agent_diagnosis(target, python_executable)
        if host == "claude"
        else codex_worker_agent_diagnosis(target)
    )
    if not path.is_file():
        result = {"host": host, "path": str(path), "state": "missing"}
        if worker_agent is not None:
            result["worker_agent"] = worker_agent
        return result
    try:
        existing = read_json(path)
    except ValueError as exc:
        result = {
            "host": host,
            "path": str(path),
            "state": "invalid",
            "detail": str(exc),
        }
        if worker_agent is not None:
            result["worker_agent"] = worker_agent
        return result
    if not contains_wishgraph_handler(existing):
        result = {"host": host, "path": str(path), "state": "missing"}
        if worker_agent is not None:
            result["worker_agent"] = worker_agent
        return result
    expected = expected_host_groups(target, host, python_executable)
    hooks = existing.get("hooks") if isinstance(existing.get("hooks"), dict) else {}
    missing_events: list[str] = []
    unexpected_events: list[str] = []
    for event, fingerprints in expected.items():
        current = hooks.get(event, []) if isinstance(hooks, dict) else []
        current_fingerprints = {
            json.dumps(group, sort_keys=True, separators=(",", ":"))
            for group in current
            if isinstance(group, dict)
        }
        if not fingerprints.issubset(current_fingerprints):
            missing_events.append(event)
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            continue
        expected_fingerprints = expected.get(event, set())
        if any(
            isinstance(group, dict)
            and contains_wishgraph_handler(group)
            and json.dumps(group, sort_keys=True, separators=(",", ":"))
            not in expected_fingerprints
            for group in groups
        ):
            unexpected_events.append(event)
    outdated_events = sorted(set(missing_events + unexpected_events))
    if host == "claude":
        worktree = existing.get("worktree")
        symlinks = (
            worktree.get("symlinkDirectories")
            if isinstance(worktree, dict)
            and isinstance(worktree.get("symlinkDirectories"), list)
            else []
        )
        if ".wishgraph" not in symlinks:
            outdated_events.append("ClaudeWorktree:.wishgraph")
    agent_current = worker_agent is None or worker_agent["state"] == "current"
    if not agent_current:
        outdated_events.append(
            ("ClaudeAgent:" if host == "claude" else "CodexAgent:")
            + "wishgraph-worker"
        )
    adapter_state = "current" if not outdated_events and agent_current else "outdated"
    if worker_agent is not None and worker_agent.get("state") == "conflict":
        adapter_state = "conflict"
    result = {
        "host": host,
        "path": str(path),
        "state": adapter_state,
        "missing_or_outdated_events": outdated_events,
    }
    if worker_agent is not None:
        result["worker_agent"] = worker_agent
    return result


def configured_python_diagnosis(config: dict[str, Any]) -> dict[str, Any]:
    configured = str(config.get("python_executable") or "")
    if not configured:
        return {"path": "", "state": "missing_from_config"}
    path = Path(configured).expanduser()
    if not path.is_file() or not os.access(path, os.X_OK):
        return {"path": configured, "state": "unavailable"}
    return {"path": str(path.resolve()), "state": "available"}


def project_git_common_dir(target: Path) -> Optional[Path]:
    result = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "--git-common-dir"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        return None
    path = Path(result.stdout.strip())
    return (path if path.is_absolute() else target / path).resolve()


def _parse_observed_at(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def host_execution_diagnosis(
    target: Path,
    host: str,
    expected_runtime_version: Optional[int],
    host_surface: str = "unknown",
) -> dict[str, Any]:
    def recovery(diagnosis: str) -> dict[str, Any]:
        result: dict[str, Any] = {
            "diagnosis": diagnosis,
            "restart_recommended": True,
            "fallback": {
                "surface": "codex_cli" if host == "codex" else "claude_code_cli",
                "command": "codex" if host == "codex" else "claude",
                "verification_command": "/hooks" if host == "codex" else "claude doctor",
                "working_directory": str(target),
            },
        }
        if host == "codex" and host_surface == "codex-cli":
            result["troubleshooting"] = "/hooks"
        elif host == "claude" and host_surface == "claude-cli":
            result["troubleshooting"] = "claude doctor"
        return result

    common_dir = project_git_common_dir(target)
    if common_dir is None:
        return {
            "state": "unavailable",
            "events": [],
            **recovery("host_verification_unavailable"),
        }
    base = common_dir / "wishgraph" / "host-observations" / host
    observations: list[dict[str, Any]] = []
    for event in HOST_OBSERVATION_EVENTS:
        path = base / f"{event}.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            isinstance(value, dict)
            and value.get("kind") == "host_observation"
            and value.get("host") == host
            and value.get("event") == event
            and _parse_observed_at(value.get("observed_at")) is not None
        ):
            observations.append(value)
    if not observations:
        return {
            "state": "unverified",
            "events": [],
            **recovery("unsupported_or_not_loaded"),
        }

    latest = max(observations, key=lambda item: str(item.get("observed_at") or ""))
    observed_at = _parse_observed_at(latest.get("observed_at"))
    assert observed_at is not None
    age_seconds = max(
        0, int((datetime.now(timezone.utc) - observed_at).total_seconds())
    )
    observed_version = latest.get("runtime_version")
    adapter_path = host_config_path(target, host)
    adapter_newer = False
    try:
        adapter_updated_at = datetime.fromtimestamp(
            adapter_path.stat().st_mtime, tz=timezone.utc
        )
        adapter_newer = (adapter_updated_at - observed_at).total_seconds() > 1
    except OSError:
        pass

    stale = (
        isinstance(observed_version, bool)
        or not isinstance(observed_version, int)
        or expected_runtime_version is None
        or observed_version != expected_runtime_version
        or adapter_newer
    )
    if stale:
        state = "stale"
    elif age_seconds <= RECENT_HOST_OBSERVATION_SECONDS:
        state = "confirmed_recently"
    else:
        state = "observed"
    diagnosis = {
        "state": state,
        "events": sorted(str(item["event"]) for item in observations),
        "last_event": latest["event"],
        "last_observed_at": latest["observed_at"],
        "age_seconds": age_seconds,
        "observed_runtime_version": observed_version,
    }
    if state != "confirmed_recently":
        diagnosis.update(recovery("host_receipt_stale"))
    return diagnosis


def doctor_report(
    target: Path,
    selected_host: Optional[str] = None,
    host_surface: str = "unknown",
) -> dict[str, Any]:
    config_path = target / ".wishgraph" / "config.json"
    config: dict[str, Any] = {}
    config_state = "missing"
    config_error = ""
    if config_path.is_file():
        try:
            config = read_json(config_path)
            required_hosts = normalize_required_hosts(config["required_hosts"])
            validate_config_paths(config)
            required_hosts_source = "configured"
            config_state = "active" if config.get("mode") in {"warn", "enforce"} else "off"
        except ValueError as exc:
            config_state = "invalid"
            config_error = str(exc)
            required_hosts = list(KNOWN_HOSTS)
            required_hosts_source = "invalid"
    else:
        required_hosts = list(KNOWN_HOSTS)
        required_hosts_source = "default_for_unconfigured_project"

    runtime = runtime_diagnosis(target)
    python_info = configured_python_diagnosis(config)
    python_executable = (
        python_info["path"] if python_info["state"] == "available" else sys.executable
    )
    if selected_host in KNOWN_HOSTS:
        hosts = (selected_host,)
        host_selection_source = "explicit"
    elif selected_host == "all":
        hosts = KNOWN_HOSTS
        host_selection_source = "explicit_all"
    else:
        hosts = tuple(required_hosts)
        host_selection_source = "required_hosts"
    host_adapters = {
        host: host_adapter_diagnosis(target, host, python_executable) for host in hosts
    }
    expected_runtime_version = runtime.get("installed_runtime_version")
    if isinstance(expected_runtime_version, bool) or not isinstance(
        expected_runtime_version, int
    ):
        expected_runtime_version = None
    for host, adapter in host_adapters.items():
        diagnosis_surface = (
            host_surface
            if (host == "codex" and host_surface.startswith("codex-"))
            or (host == "claude" and host_surface == "claude-cli")
            else "unknown"
        )
        adapter["execution"] = host_execution_diagnosis(
            target, host, expected_runtime_version, diagnosis_surface
        )
    configured_paths = (
        config.get("paths") if isinstance(config.get("paths"), dict) else {}
    )
    configured_status = str(
        configured_paths.get("project_status") or "reports/PROJECT_STATUS.md"
    )
    status_path = Path(configured_status)
    governance_ready = bool(
        not status_path.is_absolute()
        and ".." not in status_path.parts
        and (target / status_path).is_file()
    )

    if config_state == "missing":
        next_action = "use_wishgraph"
    elif config_state == "invalid":
        next_action = "repair_project_config"
    elif config_state == "off":
        next_action = "enable_wishgraph"
    elif runtime["state"] in {"upgrade_available", "metadata_missing"}:
        next_action = "upgrade_project_runtime"
    elif runtime["state"] == "missing":
        next_action = "install_project_runtime"
    elif runtime["state"] == "bundled_invalid":
        next_action = "repair_skill_installation"
    elif runtime["state"] == "newer_than_bundled":
        next_action = "update_global_wishgraph_skill"
    elif runtime["state"] != "current":
        next_action = "review_runtime_changes"
    elif any(item["state"] != "current" for item in host_adapters.values()):
        next_action = (
            "repair_current_host_adapter"
            if host_selection_source == "explicit" and len(hosts) == 1
            else "repair_required_host_adapters"
        )
    elif any(
        item["execution"]["state"] != "confirmed_recently"
        for item in host_adapters.values()
    ):
        next_action = "host_hooks_not_loaded"
    elif not governance_ready:
        next_action = "bootstrap_project_memory"
    else:
        next_action = "start_discussion"

    installation_healthy = (
        config_state == "active"
        and runtime["state"] == "current"
        and python_info["state"] == "available"
        and all(item["state"] == "current" for item in host_adapters.values())
    )
    host_execution_confirmed = bool(host_adapters) and all(
        item["execution"]["state"] == "confirmed_recently"
        for item in host_adapters.values()
    )
    formal_worker_ready = installation_healthy and host_execution_confirmed
    return {
        "schema_version": 3,
        "kind": "wishgraph_doctor",
        # Keep the established field, but make it mean end-to-end readiness. The
        # old static meaning remains available explicitly as installation_healthy.
        "healthy": formal_worker_ready,
        "installation_healthy": installation_healthy,
        "host_execution_confirmed": host_execution_confirmed,
        "formal_worker_ready": formal_worker_ready,
        "project_root": str(target),
        "activation": {
            "state": config_state,
            "mode": config.get("mode", ""),
            "config_version": config.get("version"),
            "configured_runtime_version": config.get("runtime_version"),
            "path": str(config_path),
            "error": config_error,
            "required_hosts": required_hosts,
            "required_hosts_source": required_hosts_source,
        },
        "runtime": runtime,
        "python": python_info,
        "host_adapters": host_adapters,
        "host_selection_source": host_selection_source,
        "governance_ready": governance_ready,
        "next_action": next_action,
    }


def print_doctor_report(report: dict[str, Any], json_output: bool) -> None:
    if json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    activation = report["activation"]
    execution_labels = {
        "confirmed_recently": "confirmed recently",
        "observed": "confirmed previously; recheck this session",
        "stale": "needs recheck after configuration change",
        "unverified": "not yet confirmed",
        "unavailable": "unavailable",
    }
    print("WishGraph doctor")
    print(f"- Project: {report['project_root']}")
    print(f"- Activation: {activation['state']} ({activation['mode'] or 'N/A'})")
    print(
        "- Required hosts: "
        + ", ".join(activation.get("required_hosts", []))
        + f" ({activation.get('required_hosts_source', 'unknown')})"
    )
    runtime = report["runtime"]
    installed_version = runtime.get("installed_runtime_version") or "unknown"
    bundled_version = runtime.get("bundled_runtime_version") or "unknown"
    print(
        f"- Runtime: {runtime['state']} "
        f"(installed={installed_version}, bundled={bundled_version})"
    )
    print(f"- Python: {report['python']['state']}")
    print(
        "- Installation health: "
        + ("healthy" if report["installation_healthy"] else "needs attention")
    )
    print(
        "- Host execution: "
        + ("confirmed" if report["host_execution_confirmed"] else "not confirmed")
    )
    print(
        "- Formal Worker: "
        + ("ready" if report["formal_worker_ready"] else "not ready")
    )
    if report["host_adapters"]:
        print("- Hosts:")
        for host, value in report["host_adapters"].items():
            execution_state = value["execution"]["state"]
            print(
                f"  - {host}: adapter={value['state']}; execution="
                f"{execution_labels.get(execution_state, execution_state)}"
            )
    else:
        print("- Hosts: not checked")
    if report["next_action"] == "host_hooks_not_loaded":
        pending = [
            host
            for host, value in report["host_adapters"].items()
            if value["execution"]["state"] != "confirmed_recently"
        ]
        print(
            "- Next: fully quit and reopen the affected Agent once, then say "
            "`Start discussion`."
        )
        if pending:
            print("- Host Hooks not confirmed: " + ", ".join(pending))
        troubleshooting = sorted(
            {
                value["execution"].get("troubleshooting", "")
                for value in report["host_adapters"].values()
                if value["execution"].get("troubleshooting")
            }
        )
        if troubleshooting:
            print(f"- Supported host check: {' or '.join(troubleshooting)}")
        fallbacks = {
            (
                value["execution"].get("fallback", {}).get("surface", ""),
                value["execution"].get("fallback", {}).get("command", ""),
                value["execution"].get("fallback", {}).get(
                    "verification_command", ""
                ),
            )
            for value in report["host_adapters"].values()
            if value["execution"].get("fallback")
        }
        for surface, command, verification in sorted(fallbacks):
            if surface and command:
                print(
                    f"- If no receipt appears, continue from {surface.replace('_', ' ')} "
                    f"in this project: `{command}`; then run `{verification}` to review "
                    "and trust the installed Hooks."
                )
        print(
            "- This does not prove the Desktop is unsupported; it means the installed "
            "Hooks were not observed, so WishGraph will not create a Formal Worker here."
        )
    else:
        next_labels = {
            "use_wishgraph": "enable WishGraph in this project",
            "repair_project_config": "repair the WishGraph project configuration",
            "enable_wishgraph": "enable WishGraph in this project",
            "upgrade_project_runtime": "update this project's WishGraph runtime",
            "install_project_runtime": "install the WishGraph project runtime",
            "repair_skill_installation": "repair the global WishGraph Skill",
            "update_global_wishgraph_skill": "update the global WishGraph Skill",
            "review_runtime_changes": "review local WishGraph runtime changes",
            "repair_current_host_adapter": "repair WishGraph Hooks for this host",
            "repair_required_host_adapters": "repair the required host adapters",
            "verify_required_host_sessions": "reopen each required host before its first managed Task",
            "bootstrap_project_memory": "say `Start discussion`",
            "start_discussion": "say `Start discussion`",
        }
        print(
            f"- Next: {next_labels.get(report['next_action'], report['next_action'])}"
        )


def merge_hook_config(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    existing_hooks = merged.setdefault("hooks", {})
    if not isinstance(existing_hooks, dict):
        raise ValueError("Existing top-level hooks value must be a JSON object")
    for event, current in existing_hooks.items():
        if not isinstance(current, list):
            raise ValueError(f"Existing hooks.{event} value must be a JSON array")
        preserved: list[Any] = []
        for group in current:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                preserved.append(group)
                continue
            remaining_handlers = [
                handler
                for handler in group["hooks"]
                if not (
                    isinstance(handler, dict)
                    and ".wishgraph/hooks/memory_sync.py"
                    in str(handler.get("command", "")).replace("\\", "/")
                )
            ]
            if remaining_handlers:
                preserved_group = dict(group)
                preserved_group["hooks"] = remaining_handlers
                preserved.append(preserved_group)
        current[:] = preserved

    incoming_hooks = incoming.get("hooks", {})
    for event, groups in incoming_hooks.items():
        current = existing_hooks.setdefault(event, [])
        if not isinstance(current, list):
            raise ValueError(f"Existing hooks.{event} value must be a JSON array")
        fingerprints = {
            json.dumps(group, sort_keys=True, separators=(",", ":")) for group in current
        }
        for group in groups:
            fingerprint = json.dumps(group, sort_keys=True, separators=(",", ":"))
            if fingerprint not in fingerprints:
                current.append(group)
                fingerprints.add(fingerprint)
    return merged


def migrate_project_config(
    default_config: dict[str, Any],
    existing_config: dict[str, Any],
    *,
    required_hosts: Optional[list[str]] = None,
) -> dict[str, Any]:
    config = deep_merge(default_config, existing_config)
    config["version"] = default_config["version"]
    config["runtime_version"] = default_config["runtime_version"]
    config.pop("required_impact_rows", None)
    if required_hosts is not None:
        config["required_hosts"] = normalize_required_hosts(required_hosts)
    elif "required_hosts" in existing_config:
        config["required_hosts"] = normalize_required_hosts(
            existing_config["required_hosts"]
        )
    elif existing_config:
        raise ValueError("required_hosts is required; reactivate this project")
    else:
        config["required_hosts"] = normalize_required_hosts(
            default_config.get("required_hosts", list(KNOWN_HOSTS))
        )
    validate_config_paths(config)
    return config


def runtime_target_paths(target: Path) -> list[Path]:
    hook_dir = target / ".wishgraph" / "hooks"
    return [
        *(hook_dir / name for name in RUNTIME_FILES),
        hook_dir / RUNTIME_MANIFEST_NAME,
        target / ".wishgraph" / "config.json",
    ]


def write_bundled_runtime(target: Path, *, include_files: bool) -> list[Path]:
    written: list[Path] = []
    hook_dir = target / ".wishgraph" / "hooks"
    if include_files:
        for asset_name in RUNTIME_FILES:
            source = ASSET_ROOT / asset_name
            destination = hook_dir / asset_name
            mode = stat.S_IMODE(source.stat().st_mode)
            if asset_name == "memory_sync.py":
                mode |= stat.S_IXUSR
            write_bytes_atomic(destination, source.read_bytes(), mode)
            written.append(destination)
    manifest_source = ASSET_ROOT / RUNTIME_MANIFEST_NAME
    manifest_target = hook_dir / RUNTIME_MANIFEST_NAME
    write_bytes_atomic(
        manifest_target,
        manifest_source.read_bytes(),
        stat.S_IMODE(manifest_source.stat().st_mode),
    )
    written.append(manifest_target)
    return written


def cleanup_empty_runtime_directories(target: Path) -> None:
    for path in (target / ".wishgraph" / "hooks", target / ".wishgraph"):
        try:
            path.rmdir()
        except OSError:
            pass


def cleanup_empty_activation_directories(target: Path) -> None:
    cleanup_empty_runtime_directories(target)
    for path in (
        target / ".codex" / "agents",
        target / ".codex",
        target / ".claude" / "agents",
        target / ".claude",
    ):
        try:
            path.rmdir()
        except OSError:
            pass


def install_runtime(
    target: Path,
    mode: str,
    force_assets: bool,
    *,
    upgrade: bool = False,
    required_hosts: Optional[list[str]] = None,
) -> list[Path]:
    for path in runtime_target_paths(target):
        ensure_managed_path_within_target(target, path)
    diagnosis = runtime_diagnosis(target)
    state = diagnosis["state"]
    if state == "bundled_invalid":
        raise ValueError(diagnosis.get("error", "Bundled runtime is invalid"))
    if upgrade and state == "missing":
        raise FileNotFoundError(
            "WishGraph is not installed in this project; activate it before upgrading"
        )
    if upgrade and not (target / ".wishgraph" / "config.json").is_file():
        raise FileNotFoundError(
            "WishGraph project config is missing; activate this project before upgrading"
        )
    unsafe_states = {"incomplete", "modified", "newer_than_bundled", "version_conflict"}
    if state in unsafe_states and not force_assets:
        affected = diagnosis.get("missing_files", []) + diagnosis.get(
            "non_bundled_files", []
        )
        detail = f" Affected files: {', '.join(dict.fromkeys(affected))}." if affected else ""
        raise FileExistsError(
            f"Installed WishGraph runtime is {state}; local or unknown files were preserved. "
            f"Review them before using --force-assets.{detail}"
        )

    target_paths = runtime_target_paths(target)
    snapshot = snapshot_files(target_paths)
    installed: list[Path] = []
    config_target = target / ".wishgraph" / "config.json"
    try:
        include_files = state in {"missing", "upgrade_available"} or force_assets
        if include_files or state == "metadata_missing":
            installed.extend(
                write_bundled_runtime(target, include_files=include_files)
            )

        default_config = read_json(ASSET_ROOT / "config.json")
        existing_config = read_json(config_target) if config_target.exists() else {}
        config = migrate_project_config(
            default_config,
            existing_config,
            required_hosts=required_hosts,
        )
        if upgrade and existing_config.get("mode") in {"off", "warn", "enforce"}:
            config["mode"] = existing_config["mode"]
        else:
            config["mode"] = mode
        config["python_executable"] = str(Path(sys.executable).resolve())
        write_json_atomic(config_target, config)
        installed.append(config_target)
    except Exception as exc:
        try:
            restore_snapshot(snapshot)
            cleanup_empty_activation_directories(target)
        except Exception as rollback_exc:
            raise OSError(
                f"WishGraph runtime update failed ({exc}) and rollback failed: {rollback_exc}"
            ) from rollback_exc
        raise
    return installed


def _materialize_python_commands(
    value: Any,
    python_executable: str,
    *,
    claude_powershell: bool = False,
    runtime_path: Optional[Path] = None,
) -> Any:
    if isinstance(value, dict):
        rendered = {
            key: _materialize_python_commands(
                item,
                python_executable,
                claude_powershell=claude_powershell,
                runtime_path=runtime_path,
            )
            for key, item in value.items()
        }
        if claude_powershell and rendered.get("type") == "command":
            command = rendered.get("command")
            if isinstance(command, str) and "memory_sync.py" in command:
                quoted = python_executable.replace("'", "''")
                command = command.replace(
                    shlex.quote(python_executable), f"& '{quoted}'", 1
                )
                rendered["command"] = command
                rendered["shell"] = "powershell"
        return rendered
    if isinstance(value, list):
        return [
            _materialize_python_commands(
                item,
                python_executable,
                claude_powershell=claude_powershell,
                runtime_path=runtime_path,
            )
            for item in value
        ]
    if not isinstance(value, str):
        return value
    command = value
    if runtime_path is not None:
        resolved_runtime = str(runtime_path.resolve(strict=False))
        command = command.replace(
            '"$(git rev-parse --show-toplevel)/.wishgraph/hooks/memory_sync.py"',
            shlex.quote(resolved_runtime),
        )
        command = command.replace(
            '"${CLAUDE_PROJECT_DIR}/.wishgraph/hooks/memory_sync.py"',
            shlex.quote(resolved_runtime),
        )
        powershell_runtime = resolved_runtime.replace("'", "''")
        command = command.replace("$root = git rev-parse --show-toplevel; ", "")
        command = command.replace(
            "(Join-Path $root '.wishgraph/hooks/memory_sync.py')",
            f"'{powershell_runtime}'",
        )
    command = command.replace("python3 ", f"{shlex.quote(python_executable)} ", 1)
    powershell_python = python_executable.replace("'", "''")
    return command.replace("py -3 ", f"& '{powershell_python}' ", 1)


def merged_host_config(
    target: Path, host: str, python_executable: str = sys.executable
) -> tuple[Path, dict[str, Any]]:
    python_executable = str(Path(python_executable).resolve())
    if host == "codex":
        destination = target / ".codex" / "hooks.json"
        source = ASSET_ROOT / "codex-hooks.json"
    else:
        destination = target / ".claude" / "settings.json"
        source = ASSET_ROOT / "claude-settings.json"
    incoming = _materialize_python_commands(
        read_json(source),
        python_executable,
        claude_powershell=host == "claude" and os.name == "nt",
        runtime_path=target / ".wishgraph" / "hooks" / "memory_sync.py",
    )
    merged = merge_hook_config(read_json(destination), incoming)
    if host == "claude":
        worktree = merged.setdefault("worktree", {})
        if not isinstance(worktree, dict):
            raise ValueError("Existing top-level worktree value must be a JSON object")
        worktree.setdefault("baseRef", "head")
        symlinks = worktree.setdefault("symlinkDirectories", [])
        if not isinstance(symlinks, list) or not all(
            isinstance(item, str) for item in symlinks
        ):
            raise ValueError("Existing worktree.symlinkDirectories must be a string array")
        if ".wishgraph" not in symlinks:
            symlinks.append(".wishgraph")
    return destination, merged


def install_host_config(
    target: Path, host: str, python_executable: str = sys.executable
) -> Path:
    ensure_managed_path_within_target(target, host_config_path(target, host))
    destination, merged = merged_host_config(target, host, python_executable)
    write_json_atomic(destination, merged)
    return destination


def install_claude_worker_agent(
    target: Path, python_executable: str = sys.executable
) -> Path:
    destination = target / CLAUDE_AGENT_RELATIVE_PATH
    ensure_managed_path_within_target(target, destination)
    if destination.is_file():
        existing = destination.read_text(encoding="utf-8", errors="replace")
        if CLAUDE_AGENT_MARKER not in existing:
            raise FileExistsError(
                f"Refusing to replace non-WishGraph Claude Agent: {destination}"
            )
    write_bytes_atomic(destination, materialized_claude_worker_agent(python_executable))
    return destination


def install_codex_worker_agent(target: Path) -> Path:
    destination = target / CODEX_AGENT_RELATIVE_PATH
    ensure_managed_path_within_target(target, destination)
    if destination.is_file():
        existing = destination.read_text(encoding="utf-8", errors="replace")
        if CODEX_AGENT_MARKER not in existing:
            raise FileExistsError(
                f"Refusing to replace non-WishGraph Codex Agent: {destination}"
            )
    write_bytes_atomic(destination, CODEX_AGENT_ASSET.read_bytes())
    return destination


def host_worker_agent_path(target: Path, host: str) -> Path:
    return target / (
        CODEX_AGENT_RELATIVE_PATH if host == "codex" else CLAUDE_AGENT_RELATIVE_PATH
    )


def _nearest_existing_parent(path: Path) -> Path:
    candidate = path if path.exists() else path.parent
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def ensure_target_writable(path: Path) -> None:
    candidate = path if path.exists() else _nearest_existing_parent(path)
    if not os.access(candidate, os.W_OK):
        raise PermissionError(f"Install target is not writable: {candidate}")


def ensure_managed_path_within_target(target: Path, path: Path) -> None:
    root = target.resolve()
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"Refusing to write managed project path outside {root}: "
            f"{path} -> {resolved}"
        ) from exc


def preflight_host_install(
    target: Path, hosts: list[str], python_executable: str
) -> dict[str, list[str]]:
    checked: list[str] = []
    preserved: list[str] = []
    for host in hosts:
        destination = host_config_path(target, host)
        agent_path = host_worker_agent_path(target, host)
        ensure_managed_path_within_target(target, destination)
        ensure_managed_path_within_target(target, agent_path)
        ensure_target_writable(destination)
        ensure_target_writable(agent_path)
        destination, _ = merged_host_config(target, host, python_executable)
        diagnosis = (
            codex_worker_agent_diagnosis(target)
            if host == "codex"
            else claude_worker_agent_diagnosis(target, python_executable)
        )
        if diagnosis["state"] == "conflict":
            raise FileExistsError(
                f"Refusing to replace non-WishGraph {host} Agent: {agent_path}"
            )
        checked.extend([str(destination), str(agent_path)])
        if destination.exists():
            preserved.append(str(destination))
        if agent_path.exists() and diagnosis["state"] == "current":
            preserved.append(str(agent_path))
    return {"checked": checked, "preserved": preserved}


def activation_target_paths(
    target: Path, hosts: list[str], *, include_git_hook: bool
) -> list[Path]:
    paths = list(runtime_target_paths(target))
    for host in hosts:
        paths.extend([host_config_path(target, host), host_worker_agent_path(target, host)])
    if include_git_hook:
        root = git_root(target)
        if root is not None:
            git_dir = run_git_path(root, "rev-parse", "--git-dir")
            paths.append(git_dir / "hooks" / "pre-commit")
    return list(dict.fromkeys(paths))


def run_git_path(target: Path, *args: str) -> Path:
    result = subprocess.run(
        ["git", "-C", str(target), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    path = Path(result.stdout.strip())
    return (path if path.is_absolute() else target / path).resolve()


def display_path(path: Path, target: Path) -> str:
    try:
        return str(path.relative_to(target))
    except ValueError:
        return str(path)


def changed_snapshot_paths(
    snapshot: dict[Path, tuple[bool, bytes, int]], target: Path
) -> list[str]:
    changed: list[str] = []
    for path, (existed, data, _) in snapshot.items():
        now_exists = path.is_file()
        if now_exists != existed or (now_exists and path.read_bytes() != data):
            changed.append(display_path(path, target))
    return changed


def activate_project(
    target: Path,
    *,
    mode: str,
    required_hosts: list[str],
    force_assets: bool,
    install_git_fallback: bool,
) -> dict[str, Any]:
    required_hosts = normalize_required_hosts(required_hosts)
    for path in runtime_target_paths(target):
        ensure_managed_path_within_target(target, path)
    for host in required_hosts:
        ensure_managed_path_within_target(target, host_config_path(target, host))
        ensure_managed_path_within_target(target, host_worker_agent_path(target, host))
    paths = activation_target_paths(
        target, required_hosts, include_git_hook=install_git_fallback
    )
    snapshot = snapshot_files(paths)
    preflight: dict[str, list[str]] = {"checked": [], "preserved": []}
    installed: list[Path] = []
    warning: Optional[str] = None
    try:
        preflight = preflight_host_install(target, required_hosts, sys.executable)
        for path in runtime_target_paths(target):
            ensure_target_writable(path)
        installed.extend(
            install_runtime(
                target,
                mode,
                force_assets,
                required_hosts=required_hosts,
            )
        )
        for host in required_hosts:
            installed.append(install_host_config(target, host, sys.executable))
            installed.append(
                install_codex_worker_agent(target)
                if host == "codex"
                else install_claude_worker_agent(target, sys.executable)
            )
        if install_git_fallback:
            hook_path, warning = install_git_hook(target)
            if hook_path:
                installed.append(hook_path)
    except Exception as exc:
        rolled_back = changed_snapshot_paths(snapshot, target)
        try:
            restore_snapshot(snapshot)
            cleanup_empty_activation_directories(target)
        except Exception as rollback_exc:
            raise OSError(
                f"WishGraph activation failed ({exc}) and rollback failed: {rollback_exc}"
            ) from rollback_exc
        return {
            "ok": False,
            "kind": "wishgraph_project_activation",
            "project_root": str(target),
            "required_hosts": required_hosts,
            "mode": mode,
            "installed": [],
            "preserved": [display_path(Path(path), target) for path in preflight["preserved"]],
            "failed": [str(exc)],
            "rolled_back": rolled_back,
        }

    installed_unique = list(dict.fromkeys(installed))
    changed = set(changed_snapshot_paths(snapshot, target))
    installed_paths = [
        display_path(path, target)
        for path in installed_unique
        if display_path(path, target) in changed
    ]
    preserved_paths = sorted(
        {
            display_path(Path(path), target)
            for path in preflight["preserved"]
            if display_path(Path(path), target) not in changed
        }
        | {
            display_path(path, target)
            for path in installed_unique
            if display_path(path, target) not in changed
        }
    )
    return {
        "ok": True,
        "kind": "wishgraph_project_activation",
        "project_root": str(target),
        "required_hosts": required_hosts,
        "mode": mode,
        "installed": installed_paths,
        "preserved": preserved_paths,
        "failed": [],
        "rolled_back": [],
        "warning": warning or "",
    }


def repair_host_adapter(target: Path, host: str) -> dict[str, Any]:
    if host not in {"codex", "claude"}:
        raise ValueError("Choose exactly one current host: codex or claude")
    config_path = target / ".wishgraph" / "config.json"
    ensure_managed_path_within_target(target, config_path)
    ensure_managed_path_within_target(target, host_config_path(target, host))
    ensure_managed_path_within_target(target, host_worker_agent_path(target, host))
    config = read_json(config_path)
    if config.get("mode") not in {"warn", "enforce"}:
        raise ValueError("WishGraph must be active before repairing a host adapter")
    runtime = runtime_diagnosis(target)
    if runtime["state"] != "current":
        raise ValueError(
            f"Project runtime is {runtime['state']}; make it current before repairing hooks"
        )

    python_info = configured_python_diagnosis(config)
    python_executable = (
        python_info["path"]
        if python_info["state"] == "available"
        else str(Path(sys.executable).resolve())
    )
    before = host_adapter_diagnosis(target, host, python_executable)
    adapter_path = host_config_path(target, host)
    tracked = [adapter_path, config_path]
    tracked.append(
        target
        / (
            CLAUDE_AGENT_RELATIVE_PATH
            if host == "claude"
            else CODEX_AGENT_RELATIVE_PATH
        )
    )
    snapshot = snapshot_files(tracked)
    changed: list[Path] = []
    try:
        if python_info["state"] != "available":
            config["python_executable"] = python_executable
            write_json_atomic(config_path, config)
            changed.append(config_path)
        if before["state"] != "current":
            changed.append(install_host_config(target, host, python_executable))
            if host == "claude":
                changed.append(install_claude_worker_agent(target, python_executable))
            else:
                changed.append(install_codex_worker_agent(target))
    except Exception as exc:
        try:
            restore_snapshot(snapshot)
        except Exception as rollback_exc:
            raise OSError(
                f"WishGraph host repair failed ({exc}) and rollback failed: {rollback_exc}"
            ) from rollback_exc
        raise
    after = host_adapter_diagnosis(target, host, python_executable)
    return {
        "ok": after["state"] == "current",
        "kind": "wishgraph_host_repair",
        "host": host,
        "project_root": str(target),
        "before": before,
        "after": after,
        "changed": [str(path.relative_to(target)) for path in changed],
    }


def git_root(target: Path) -> Optional[Path]:
    result = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "--show-toplevel"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return Path(result.stdout.strip()).resolve() if result.returncode == 0 else None


def install_git_hook(target: Path) -> tuple[Optional[Path], Optional[str]]:
    root = git_root(target)
    if root is None:
        return None, "Git pre-commit hook skipped: target is not a Git repository."
    hook_location = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--git-path", "hooks/pre-commit"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout.strip()
    hook_path = Path(hook_location)
    if not hook_path.is_absolute():
        hook_path = (root / hook_path).resolve()
    if hook_path.exists():
        return None, (
            f"Git pre-commit hook skipped because {hook_path} already exists. "
            "Chain `.wishgraph/hooks/memory_sync.py git-pre-commit` manually if desired."
        )
    hook_path.parent.mkdir(parents=True, exist_ok=True)
    python_command = shlex.quote(str(Path(sys.executable).resolve()))
    hook_path.write_text(
        "#!/bin/sh\n"
        "root=$(git rev-parse --show-toplevel) || exit 0\n"
        f"exec {python_command} \"$root/.wishgraph/hooks/memory_sync.py\" git-pre-commit\n",
        encoding="utf-8",
    )
    hook_path.chmod(hook_path.stat().st_mode | stat.S_IXUSR)
    return hook_path, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default=".", help="Target project directory")
    parser.add_argument(
        "--host",
        choices=("codex", "claude", "all"),
        default=None,
        help="Required project hosts; first activation defaults to all",
    )
    parser.add_argument(
        "--current-host",
        choices=("codex", "claude", "unknown"),
        default="unknown",
        help="Host running this command; does not select required_hosts",
    )
    parser.add_argument(
        "--host-surface",
        choices=KNOWN_HOST_SURFACES,
        default="unknown",
        help="Optional diagnostic surface; unknown never advertises surface-only commands",
    )
    parser.add_argument(
        "--mode",
        choices=("off", "warn", "enforce"),
        default="warn",
        help="Initial hook enforcement mode",
    )
    parser.add_argument(
        "--force-assets",
        action="store_true",
        help="Replace an existing generated WishGraph hook runtime",
    )
    parser.add_argument(
        "--git-hook",
        action="store_true",
        help="Also install an opt-in Git pre-commit hook when none exists",
    )
    maintenance = parser.add_mutually_exclusive_group()
    maintenance.add_argument(
        "--doctor",
        action="store_true",
        help="Inspect project activation, runtime, Python, and host adapters without writing",
    )
    maintenance.add_argument(
        "--upgrade",
        action="store_true",
        help="Safely upgrade a recognized project-local WishGraph runtime",
    )
    maintenance.add_argument(
        "--repair-host-adapter",
        action="store_true",
        help="Repair only the selected active Codex or Claude Code adapter",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON for diagnostic or maintenance actions",
    )
    args = parser.parse_args()

    if sys.version_info < (3, 9):
        print(
            "WishGraph hooks require Python 3.9 or newer. "
            "A typical Python install uses about 100-300 MB and takes 2-10 minutes.",
            file=sys.stderr,
        )
        return 3
    git_preflight = git_preflight_diagnosis()
    if git_preflight["state"] == "stale_path":
        print(
            "Git is installed, but this process cannot see it in PATH. Fully quit "
            "Codex (not only the current task), reopen it, then retry. WishGraph did "
            "not change PATH.",
            file=sys.stderr,
        )
        return 3
    if git_preflight["state"] == "missing":
        print(
            "WishGraph hooks require Git. A typical Git install uses about "
            "200-500 MB and takes 2-10 minutes. Install Git, reopen the terminal, "
            "then retry.",
            file=sys.stderr,
        )
        return 3

    target = Path(args.target).expanduser().resolve()
    if not target.is_dir():
        print(f"Target directory does not exist: {target}", file=sys.stderr)
        return 2
    repository_root = git_root(target)
    if repository_root is None:
        print(
            f"WishGraph hooks need a Git repository, but {target} is not inside one.\n"
            "Run `git init` there, or ask your agent to initialize Git, then retry. "
            "Initializing an empty repository normally takes under a second and "
            "uses less than 1 MB.",
            file=sys.stderr,
        )
        return 3
    if repository_root != target:
        message = f"Using detected Git repository root: {repository_root}"
        print(message, file=sys.stderr if args.json_output else sys.stdout)
        target = repository_root

    if args.doctor:
        print_doctor_report(
            doctor_report(target, args.host, args.host_surface), args.json_output
        )
        return 0

    if args.upgrade:
        before = runtime_diagnosis(target)
        try:
            installed = install_runtime(
                target,
                args.mode,
                args.force_assets,
                upgrade=True,
            )
        except (OSError, ValueError, FileExistsError) as exc:
            if args.json_output:
                print(
                    json.dumps(
                        {
                            "ok": False,
                            "kind": "wishgraph_upgrade",
                            "error": str(exc),
                            "before": before,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            else:
                print(f"WishGraph runtime upgrade stopped: {exc}", file=sys.stderr)
            return 4
        after = runtime_diagnosis(target)
        changed = []
        for path in installed:
            try:
                changed.append(str(path.relative_to(target)))
            except ValueError:
                changed.append(str(path))
        result = {
            "ok": after["state"] == "current",
            "kind": "wishgraph_upgrade",
            "project_root": str(target),
            "before": before,
            "after": after,
            "changed": changed,
        }
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(
                "WishGraph project runtime is current "
                f"(v{after.get('bundled_runtime_version', 'unknown')})."
            )
            for path in changed:
                print(f"- {path}")
        return 0 if result["ok"] else 1

    if args.repair_host_adapter:
        if args.host not in {"codex", "claude"}:
            message = "Choose the current host with --host codex or --host claude"
            if args.json_output:
                print(
                    json.dumps(
                        {
                            "ok": False,
                            "kind": "wishgraph_host_repair",
                            "error": message,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            else:
                print(message, file=sys.stderr)
            return 2
        try:
            result = repair_host_adapter(target, args.host)
        except (OSError, ValueError, FileExistsError) as exc:
            if args.json_output:
                print(
                    json.dumps(
                        {
                            "ok": False,
                            "kind": "wishgraph_host_repair",
                            "host": args.host,
                            "error": str(exc),
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            else:
                print(f"WishGraph host repair stopped: {exc}", file=sys.stderr)
            return 4
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(
                f"WishGraph {args.host} adapter is {result['after']['state']}."
            )
            for path in result["changed"]:
                print(f"- {path}")
        return 0 if result["ok"] else 1

    config_path = target / ".wishgraph" / "config.json"
    existing_config: dict[str, Any] = {}
    if config_path.is_file():
        try:
            existing_config = read_json(config_path)
        except ValueError as exc:
            print(f"WishGraph hook installation failed: {exc}", file=sys.stderr)
            return 1
    try:
        if args.host is not None:
            required_hosts = hosts_for_selection(args.host)
        elif "required_hosts" in existing_config:
            required_hosts = normalize_required_hosts(existing_config["required_hosts"])
        elif existing_config:
            raise ValueError("required_hosts is required; reactivate this project")
        else:
            required_hosts = list(KNOWN_HOSTS)
        result = activate_project(
            target,
            mode=args.mode,
            required_hosts=required_hosts,
            force_assets=args.force_assets,
            install_git_fallback=args.git_hook,
        )
    except (OSError, ValueError, FileExistsError) as exc:
        result = {
            "ok": False,
            "kind": "wishgraph_project_activation",
            "project_root": str(target),
            "required_hosts": [],
            "mode": args.mode,
            "installed": [],
            "preserved": [],
            "failed": [str(exc)],
            "rolled_back": [],
        }

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1
    if not result["ok"]:
        print("WishGraph project activation failed.", file=sys.stderr)
        for detail in result["failed"]:
            print(f"- Failed: {detail}", file=sys.stderr)
        for path in result["rolled_back"]:
            print(f"- Rolled back: {path}", file=sys.stderr)
        return 1

    labels = {"codex": "Codex", "claude": "Claude Code"}
    host_labels = ", ".join(labels[host] for host in result["required_hosts"])
    print(
        f"WishGraph project activation complete ({result['mode']}; {host_labels})."
    )
    print(
        "Formal Worker remains unavailable until a host Hook receipt is observed; "
        "warn mode does not bypass authority checks."
    )
    if result.get("warning"):
        print(result["warning"], file=sys.stderr)
    print(
        "Next: fully quit and reopen the current Agent, then say `Start discussion`. "
        "If no host receipt appears, run Doctor and continue from the supported CLI "
        "fallback it reports."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
