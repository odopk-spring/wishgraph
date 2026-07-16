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
from pathlib import Path
from typing import Any, Optional


SKILL_ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = SKILL_ROOT / "assets" / "hooks"
RUNTIME_FILES = (
    "memory_sync.py",
    "git_state.py",
    "workflow_state.py",
    "policy.py",
    "host_adapter.py",
)
RUNTIME_MANIFEST_NAME = "runtime-manifest.json"
HOST_OBSERVATION_EVENTS = ("session-start", "user-prompt-submit")
RECENT_HOST_OBSERVATION_SECONDS = 120


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
            not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
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
    elif installed_count != len(RUNTIME_FILES):
        state = "incomplete"
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


def host_config_path(target: Path, host: str) -> Path:
    if host == "codex":
        return target / ".codex" / "hooks.json"
    return target / ".claude" / "settings.json"


def host_asset_path(host: str) -> Path:
    return ASSET_ROOT / ("codex-hooks.json" if host == "codex" else "claude-settings.json")


def expected_host_groups(host: str, python_executable: str) -> dict[str, set[str]]:
    incoming = _materialize_python_commands(
        read_json(host_asset_path(host)),
        python_executable,
        claude_powershell=host == "claude" and os.name == "nt",
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
    if not path.is_file():
        return {"host": host, "path": str(path), "state": "missing"}
    try:
        existing = read_json(path)
    except ValueError as exc:
        return {
            "host": host,
            "path": str(path),
            "state": "invalid",
            "detail": str(exc),
        }
    if not contains_wishgraph_handler(existing):
        return {"host": host, "path": str(path), "state": "missing"}
    expected = expected_host_groups(host, python_executable)
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
    return {
        "host": host,
        "path": str(path),
        "state": "current" if not outdated_events else "outdated",
        "missing_or_outdated_events": outdated_events,
    }


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
    target: Path, host: str, expected_runtime_version: Optional[int]
) -> dict[str, Any]:
    common_dir = project_git_common_dir(target)
    if common_dir is None:
        return {"state": "unavailable", "events": []}
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
            "troubleshooting": "/hooks" if host == "codex" else "claude doctor",
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
        diagnosis["troubleshooting"] = (
            "/hooks" if host == "codex" else "claude doctor"
        )
    return diagnosis


def doctor_report(target: Path, selected_host: str) -> dict[str, Any]:
    config_path = target / ".wishgraph" / "config.json"
    config: dict[str, Any] = {}
    config_state = "missing"
    config_error = ""
    if config_path.is_file():
        try:
            config = read_json(config_path)
            config_state = "active" if config.get("mode") in {"warn", "enforce"} else "off"
        except ValueError as exc:
            config_state = "invalid"
            config_error = str(exc)

    runtime = runtime_diagnosis(target)
    python_info = configured_python_diagnosis(config)
    python_executable = (
        python_info["path"] if python_info["state"] == "available" else sys.executable
    )
    hosts = ("codex", "claude") if selected_host == "all" else (selected_host,)
    host_adapters = {
        host: host_adapter_diagnosis(target, host, python_executable) for host in hosts
    }
    expected_runtime_version = runtime.get("installed_runtime_version")
    if isinstance(expected_runtime_version, bool) or not isinstance(
        expected_runtime_version, int
    ):
        expected_runtime_version = None
    for host, adapter in host_adapters.items():
        adapter["execution"] = host_execution_diagnosis(
            target, host, expected_runtime_version
        )
    governance_ready = (
        (target / "reports" / "PROJECT_STATUS.md").is_file()
        or (target / "reports" / "DEV_REPORT.md").is_file()
    ) and (target / "prompts" / "DISCUSSION_AI.md").is_file()

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
        next_action = "repair_current_host_adapter"
    elif any(
        item["execution"]["state"] != "confirmed_recently"
        for item in host_adapters.values()
    ):
        next_action = "restart_agent_session"
    elif not governance_ready:
        next_action = "bootstrap_project_memory"
    else:
        next_action = "start_discussion"

    healthy = (
        config_state == "active"
        and runtime["state"] == "current"
        and python_info["state"] == "available"
        and all(item["state"] == "current" for item in host_adapters.values())
    )
    host_execution_confirmed = bool(host_adapters) and all(
        item["execution"]["state"] == "confirmed_recently"
        for item in host_adapters.values()
    )
    return {
        "schema_version": 2,
        "kind": "wishgraph_doctor",
        "healthy": healthy,
        "host_execution_confirmed": host_execution_confirmed,
        "project_root": str(target),
        "activation": {
            "state": config_state,
            "mode": config.get("mode", ""),
            "config_version": config.get("version"),
            "configured_runtime_version": config.get("runtime_version"),
            "path": str(config_path),
            "error": config_error,
        },
        "runtime": runtime,
        "python": python_info,
        "host_adapters": host_adapters,
        "governance_ready": governance_ready,
        "next_action": next_action,
    }


def print_doctor_report(report: dict[str, Any], json_output: bool) -> None:
    if json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    activation = report["activation"]
    host_summary = ", ".join(
        f"{host}={value['state']}" for host, value in report["host_adapters"].items()
    )
    execution_labels = {
        "confirmed_recently": "confirmed recently",
        "observed": "confirmed previously; recheck this session",
        "stale": "needs recheck after configuration change",
        "unverified": "not yet confirmed",
        "unavailable": "unavailable",
    }
    execution_summary = ", ".join(
        f"{host}={execution_labels.get(value['execution']['state'], value['execution']['state'])}"
        for host, value in report["host_adapters"].items()
    )
    print("WishGraph doctor")
    print(f"- Project: {report['project_root']}")
    print(f"- Activation: {activation['state']} ({activation['mode'] or 'N/A'})")
    runtime = report["runtime"]
    installed_version = runtime.get("installed_runtime_version") or "unknown"
    bundled_version = runtime.get("bundled_runtime_version") or "unknown"
    print(
        f"- Runtime: {runtime['state']} "
        f"(installed={installed_version}, bundled={bundled_version})"
    )
    print(f"- Python: {report['python']['state']}")
    print(f"- Host adapters: {host_summary or 'not checked'}")
    print(f"- Host execution: {execution_summary or 'not observed'}")
    if report["next_action"] == "restart_agent_session":
        print("- Next: reopen the current Agent session, then say `Start discussion`.")
        troubleshooting = sorted(
            {
                value["execution"].get("troubleshooting", "")
                for value in report["host_adapters"].values()
                if value["execution"].get("troubleshooting")
            }
        )
        if troubleshooting:
            print(f"- If it still does not respond: {' or '.join(troubleshooting)}")
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
    default_config: dict[str, Any], existing_config: dict[str, Any]
) -> dict[str, Any]:
    if "session_start_context_mode" not in existing_config:
        legacy_injection = existing_config.get("inject_project_summary_on_session_start")
        if isinstance(legacy_injection, bool):
            existing_config = dict(existing_config)
            existing_config["session_start_context_mode"] = (
                "discussion_summary" if legacy_injection else "safety_only"
            )
    existing_paths = existing_config.get("paths")
    if isinstance(existing_paths, dict) and "dev_report" in existing_paths:
        migrated_paths = dict(existing_paths)
        if "project_status" not in migrated_paths:
            migrated_paths["project_status"] = migrated_paths["dev_report"]
        del migrated_paths["dev_report"]
        existing_config = dict(existing_config)
        existing_config["paths"] = migrated_paths
    config = deep_merge(default_config, existing_config)
    config["version"] = default_config["version"]
    config["runtime_version"] = default_config["runtime_version"]
    config["required_impact_rows"] = list(
        dict.fromkeys(
            list(default_config.get("required_impact_rows", []))
            + list(existing_config.get("required_impact_rows", []))
        )
    )
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


def install_runtime(
    target: Path,
    mode: str,
    force_assets: bool,
    *,
    upgrade: bool = False,
) -> list[Path]:
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
        config = migrate_project_config(default_config, existing_config)
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
            cleanup_empty_runtime_directories(target)
        except Exception as rollback_exc:
            raise OSError(
                f"WishGraph runtime update failed ({exc}) and rollback failed: {rollback_exc}"
            ) from rollback_exc
        raise
    return installed


def _materialize_python_commands(
    value: Any, python_executable: str, *, claude_powershell: bool = False
) -> Any:
    if isinstance(value, dict):
        rendered = {
            key: _materialize_python_commands(
                item, python_executable, claude_powershell=claude_powershell
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
                item, python_executable, claude_powershell=claude_powershell
            )
            for item in value
        ]
    if not isinstance(value, str):
        return value
    command = value.replace("python3 ", f"{shlex.quote(python_executable)} ", 1)
    powershell_python = python_executable.replace("'", "''")
    return command.replace("py -3 ", f"& '{powershell_python}' ", 1)


def install_host_config(
    target: Path, host: str, python_executable: str = sys.executable
) -> Path:
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
    )
    merged = merge_hook_config(read_json(destination), incoming)
    write_json_atomic(destination, merged)
    return destination


def repair_host_adapter(target: Path, host: str) -> dict[str, Any]:
    if host not in {"codex", "claude"}:
        raise ValueError("Choose exactly one current host: codex or claude")
    config_path = target / ".wishgraph" / "config.json"
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
    snapshot = snapshot_files(tracked)
    changed: list[Path] = []
    try:
        if python_info["state"] != "available":
            config["python_executable"] = python_executable
            write_json_atomic(config_path, config)
            changed.append(config_path)
        if before["state"] != "current":
            changed.append(install_host_config(target, host, python_executable))
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
        default="all",
        help="Project-level agent configuration to merge",
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
    if shutil.which("git") is None:
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
        print_doctor_report(doctor_report(target, args.host), args.json_output)
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
        if args.host == "all":
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

    try:
        installed = install_runtime(target, args.mode, args.force_assets)
        hosts = ("codex", "claude") if args.host == "all" else (args.host,)
        installed.extend(
            install_host_config(target, host, sys.executable) for host in hosts
        )
        warning = None
        if args.git_hook:
            hook_path, warning = install_git_hook(target)
            if hook_path:
                installed.append(hook_path)
    except (OSError, ValueError, FileExistsError) as exc:
        print(f"WishGraph hook installation failed: {exc}", file=sys.stderr)
        return 1

    print("WishGraph hook runtime installed or merged:")
    for path in installed:
        try:
            display = path.relative_to(target)
        except ValueError:
            display = path
        print(f"- {display}")
    if warning:
        print(warning, file=sys.stderr)
    print(f"Mode: {args.mode}")
    print(
        "Next: reopen the current Agent session, then say `开始讨论` "
        "(or `Start discussion`)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
