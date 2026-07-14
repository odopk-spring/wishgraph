"""Git and repository-state boundary for the WishGraph hook runtime."""

from __future__ import annotations

import fnmatch
import json
import os
import re
import socket
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


DEFAULT_CONFIG: dict[str, Any] = {
    "version": 9,
    "mode": "enforce",
    "paths": {
        "prd": "PRD.md",
        "architecture": "ARCHITECTURE.md",
        "codemap": "CODEMAP.md",
        "conventions": "CONVENTIONS.md",
        "discussion_prompt": "prompts/DISCUSSION_AI.md",
        "execution_prompt": "prompts/EXECUTION_AI.md",
        "integration_prompt": "prompts/INTEGRATION_AI.md",
        "project_status": "reports/PROJECT_STATUS.md",
        "run_report_glob": "reports/runs/*.md",
        "task_glob": "tasks/build/*.md",
        "task_globs": ["tasks/build/*.md", ".tasks/build/*.md"],
    },
    "required_impact_rows": [
        "PRD.md",
        "ARCHITECTURE.md",
        "CODEMAP.md",
        "CONVENTIONS.md",
        "prompts/DISCUSSION_AI.md",
        "prompts/EXECUTION_AI.md",
        "prompts/INTEGRATION_AI.md",
    ],
    "ignore_globs": [
        ".git/**",
        ".wishgraph/**",
        ".codex/hooks.json",
        ".claude/settings.json",
        ".DS_Store",
        "**/.DS_Store",
        "**/__pycache__/**",
        "**/.pytest_cache/**",
    ],
    "allow_noop_with_reason": True,
    "require_discussion_update_for_substantive_changes": True,
    "scan_worker_refs_for_status": True,
    "session_start_context_mode": "safety_only",
    "project_status_max_lines": 160,
    "project_status_max_chars": 12000,
    "discussion_dynamic_max_lines": 30,
    "session_summary_max_chars": 2000,
    "orchestration_gate_enabled": True,
    "read_gate_mode": "host_dependent",
}

LEGACY_PROJECT_STATUS_PATH = "reports/DEV_REPORT.md"
DEFAULT_PROJECT_STATUS_PATH = "reports/PROJECT_STATUS.md"


def run_git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def find_git_root(start: Path) -> Optional[Path]:
    try:
        result = run_git(start, "rev-parse", "--show-toplevel")
    except (OSError, subprocess.CalledProcessError):
        return None
    return Path(result.stdout.decode("utf-8", errors="replace").strip()).resolve()


def git_common_dir(root: Path) -> Path:
    value = run_git(root, "rev-parse", "--git-common-dir").stdout.decode(
        "utf-8", errors="replace"
    ).strip()
    path = Path(value)
    return (path if path.is_absolute() else root / path).resolve()


def current_branch(root: Path) -> str:
    result = run_git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    if result.returncode == 0:
        return result.stdout.decode("utf-8", errors="replace").strip()
    return "DETACHED"


def worktree_is_clean(root: Path) -> bool:
    fields = [
        item.decode("utf-8", errors="surrogateescape")
        for item in run_git(root, "status", "--porcelain", "-z").stdout.split(b"\0")
        if item
    ]
    for field in fields:
        path = field[3:] if len(field) > 3 and field[2] == " " else field
        if (
            path.startswith(".wishgraph/")
            or path in {".codex/hooks.json", ".claude/settings.json"}
            or "__pycache__/" in path
            or path.endswith(".pyc")
        ):
            continue
        return False
    return True


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def claim_root(root: Path) -> Path:
    return git_common_dir(root) / "wishgraph" / "claims"


def _task_claim_dir(root: Path, task_id: str) -> Path:
    return claim_root(root) / task_id


def _read_claim(path: Path, stale_after_seconds: int = 3600) -> Optional[dict[str, Any]]:
    try:
        claim = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(claim, dict):
        return None
    updated_at = parse_timestamp(claim.get("updated_at"))
    stale = updated_at is None or (
        datetime.now(timezone.utc) - updated_at
    ).total_seconds() > stale_after_seconds
    claim["stale"] = stale and claim.get("lease_status") == "active"
    claim["effective_lease_status"] = "stale" if claim["stale"] else claim.get(
        "lease_status", "unknown"
    )
    return claim


def inspect_claims(
    root: Path, task_id: Optional[str] = None, stale_after_seconds: int = 3600
) -> list[dict[str, Any]]:
    base = claim_root(root)
    patterns = [_task_claim_dir(root, task_id)] if task_id else sorted(base.glob("*"))
    claims: list[dict[str, Any]] = []
    for directory in patterns:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            claim = _read_claim(path, stale_after_seconds)
            if claim is not None:
                claims.append(claim)
    return claims


def _claim_mutex(task_dir: Path) -> Path:
    task_dir.mkdir(parents=True, exist_ok=True)
    mutex = task_dir / ".operation.lock"
    try:
        descriptor = os.open(mutex, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        try:
            age = datetime.now(timezone.utc).timestamp() - mutex.stat().st_mtime
        except OSError:
            age = 0
        if age > 30:
            try:
                mutex.unlink()
            except OSError:
                pass
            descriptor = os.open(mutex, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        else:
            raise RuntimeError("claim_operation_in_progress") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(f"{os.getpid()} {utc_now()}\n")
    return mutex


def _atomic_claim_update(path: Path, claim: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(claim, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def acquire_claim(
    root: Path,
    task_id: str,
    attempt: int,
    worker_id: str,
    *,
    execution_mode: str = "exclusive",
    branch: Optional[str] = None,
    worktree: Optional[str] = None,
    host_thread_ref: Optional[str] = None,
    stale_after_seconds: int = 3600,
    require_clean: bool = True,
) -> dict[str, Any]:
    """Atomically acquire a repository-wide Worker Claim for one Task attempt."""
    if execution_mode not in {"exclusive", "competitive"}:
        return {"ok": False, "error": "invalid_execution_mode"}
    if attempt < 1:
        return {"ok": False, "error": "invalid_attempt"}
    if require_clean and not worktree_is_clean(root):
        return {"ok": False, "error": "worktree_not_clean"}
    bound_branch = branch or current_branch(root)
    bound_worktree = str(Path(worktree).resolve()) if worktree else str(root.resolve())
    task_dir = _task_claim_dir(root, task_id)
    try:
        mutex = _claim_mutex(task_dir)
    except (OSError, RuntimeError) as exc:
        return {"ok": False, "error": str(exc)}
    try:
        existing_claims = inspect_claims(root, task_id, stale_after_seconds)
        stale_claims = [claim for claim in existing_claims if claim.get("stale")]
        if stale_claims:
            return {
                "ok": False,
                "error": "stale_claim_requires_explicit_revoke",
                "claims": stale_claims,
            }
        active = [
            claim
            for claim in existing_claims
            if claim.get("effective_lease_status") == "active"
        ]
        if active and (
            execution_mode == "exclusive"
            or any(claim.get("execution_mode") == "exclusive" for claim in active)
        ):
            return {
                "ok": False,
                "error": "active_claim_exists",
                "claims": active,
                "options": [
                    "observe_existing_worker",
                    "continue_original_worker",
                    "stop_and_retry",
                    "explicit_take_over",
                    "competitive_execution",
                ],
            }
        for claim in active:
            if claim.get("worktree") == bound_worktree:
                return {
                    "ok": False,
                    "error": "worktree_already_claimed",
                    "claims": [claim],
                }

        claim_id = uuid.uuid4().hex
        now = utc_now()
        claim = {
            "schema_version": 1,
            "kind": "worker_claim",
            "claim_id": claim_id,
            "task_id": task_id,
            "attempt_id": f"{task_id}-attempt-{attempt}",
            "attempt": attempt,
            "worker_id": worker_id,
            "branch": bound_branch,
            "worktree": bound_worktree,
            "started_at": now,
            "updated_at": now,
            "lease_status": "active",
            "execution_mode": execution_mode,
            "host": socket.gethostname(),
            "host_thread_ref": host_thread_ref,
        }
        path = task_dir / f"{claim_id}.json"
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(claim, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        claim["stale"] = False
        claim["effective_lease_status"] = "active"
        return {"ok": True, "claim": claim}
    finally:
        try:
            mutex.unlink()
        except OSError:
            pass


def update_claim(
    root: Path,
    claim_id: str,
    action: str,
    *,
    branch: Optional[str] = None,
    worktree: Optional[str] = None,
) -> dict[str, Any]:
    """Heartbeat, release, or revoke a Claim while preserving its audit record."""
    if action not in {"heartbeat", "release", "revoke"}:
        return {"ok": False, "error": "invalid_claim_action"}
    matches = list(claim_root(root).glob(f"*/{claim_id}.json"))
    if len(matches) != 1:
        return {"ok": False, "error": "claim_not_found"}
    path = matches[0]
    try:
        mutex = _claim_mutex(path.parent)
    except (OSError, RuntimeError) as exc:
        return {"ok": False, "error": str(exc)}
    try:
        claim = _read_claim(path)
        if claim is None:
            return {"ok": False, "error": "invalid_claim_record"}
        if branch is not None and claim.get("branch") != branch:
            return {"ok": False, "error": "claim_branch_mismatch", "claim": claim}
        if worktree is not None and claim.get("worktree") != str(Path(worktree).resolve()):
            return {"ok": False, "error": "claim_worktree_mismatch", "claim": claim}
        if action == "heartbeat" and claim.get("lease_status") != "active":
            return {"ok": False, "error": "claim_not_active", "claim": claim}
        claim.pop("stale", None)
        claim.pop("effective_lease_status", None)
        claim["updated_at"] = utc_now()
        if action in {"release", "revoke"}:
            claim["lease_status"] = "released" if action == "release" else "revoked"
            claim[f"{claim['lease_status']}_at"] = claim["updated_at"]
        _atomic_claim_update(path, claim)
        return {"ok": True, "claim": _read_claim(path)}
    finally:
        try:
            mutex.unlink()
        except OSError:
            pass


RUNTIME_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def session_runtime_root(root: Path) -> Path:
    return git_common_dir(root) / "wishgraph" / "sessions"


def _session_runtime_path(root: Path, session_id: str) -> Path:
    if not RUNTIME_ID_RE.fullmatch(session_id):
        raise ValueError("invalid_session_id")
    return session_runtime_root(root) / f"{session_id}.json"


def write_session_runtime(
    root: Path, session_id: str, runtime: dict[str, Any]
) -> dict[str, Any]:
    """Atomically persist host/session orchestration state outside the worktree."""
    try:
        path = _session_runtime_path(root, session_id)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    path.parent.mkdir(parents=True, exist_ok=True)
    record = dict(runtime)
    record.update(
        {
            "schema_version": 1,
            "kind": "session_runtime",
            "session_id": session_id,
            "updated_at": utc_now(),
        }
    )
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    except OSError as exc:
        try:
            temporary.unlink()
        except OSError:
            pass
        return {"ok": False, "error": "session_runtime_write_failed", "detail": str(exc)}
    return {"ok": True, "runtime": record}


def read_session_runtime(root: Path, session_id: str) -> Optional[dict[str, Any]]:
    try:
        path = _session_runtime_path(root, session_id)
        value = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def apply_session_runtime_patch(
    root: Path, session_id: str, patch: dict[str, Any]
) -> dict[str, Any]:
    """Deep-merge one reducer state patch into the current session runtime."""
    if not isinstance(patch, dict):
        return {"ok": False, "error": "session_runtime_patch_must_be_object"}
    try:
        runtime_path = _session_runtime_path(root, session_id)
        mutex = _claim_mutex(runtime_path.parent)
    except (ValueError, OSError, RuntimeError) as exc:
        return {"ok": False, "error": str(exc)}
    try:
        current = read_session_runtime(root, session_id) or {}
        return write_session_runtime(root, session_id, deep_merge(current, patch))
    finally:
        try:
            mutex.unlink()
        except OSError:
            pass


def integration_runtime_root(root: Path) -> Path:
    return git_common_dir(root) / "wishgraph" / "integration"


def _integration_lease_path(root: Path) -> Path:
    return integration_runtime_root(root) / "lease.json"


def inspect_integration_lease(
    root: Path, stale_after_seconds: int = 3600
) -> Optional[dict[str, Any]]:
    path = _integration_lease_path(root)
    try:
        lease = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(lease, dict):
        return None
    updated_at = parse_timestamp(lease.get("updated_at"))
    stale = updated_at is None or (
        datetime.now(timezone.utc) - updated_at
    ).total_seconds() > stale_after_seconds
    lease["stale"] = stale and lease.get("lease_status") == "active"
    lease["effective_lease_status"] = (
        "stale" if lease["stale"] else lease.get("lease_status", "unknown")
    )
    return lease


def acquire_integration_lease(
    root: Path,
    *,
    session_id: str,
    integration_id: str,
    task_ids: list[str],
    reports: list[str],
    branch: Optional[str] = None,
    worktree: Optional[str] = None,
    stale_after_seconds: int = 3600,
    require_clean: bool = True,
) -> dict[str, Any]:
    """Atomically acquire the one Discussion-local Integration lease."""
    if not RUNTIME_ID_RE.fullmatch(session_id):
        return {"ok": False, "error": "invalid_session_id"}
    if not integration_id or not task_ids or not reports:
        return {"ok": False, "error": "integration_binding_incomplete"}
    if require_clean and not worktree_is_clean(root):
        return {"ok": False, "error": "worktree_not_clean"}
    runtime_root = integration_runtime_root(root)
    try:
        mutex = _claim_mutex(runtime_root)
    except (OSError, RuntimeError) as exc:
        return {"ok": False, "error": str(exc)}
    try:
        existing = inspect_integration_lease(root, stale_after_seconds)
        if existing and existing.get("effective_lease_status") == "stale":
            return {
                "ok": False,
                "error": "stale_integration_lease_requires_explicit_revoke",
                "lease": existing,
            }
        if existing and existing.get("effective_lease_status") == "active":
            return {
                "ok": False,
                "error": "active_integration_lease_exists",
                "lease": existing,
            }
        now = utc_now()
        lease = {
            "schema_version": 1,
            "kind": "integration_lease",
            "lease_id": uuid.uuid4().hex,
            "session_id": session_id,
            "integration_id": integration_id,
            "base_branch": branch or current_branch(root),
            "worktree": str(Path(worktree).resolve()) if worktree else str(root.resolve()),
            "selected_task_ids": list(task_ids),
            "selected_reports": list(reports),
            "started_at": now,
            "updated_at": now,
            "lease_status": "active",
            "host": socket.gethostname(),
        }
        _atomic_claim_update(_integration_lease_path(root), lease)
        lease["stale"] = False
        lease["effective_lease_status"] = "active"
        return {"ok": True, "lease": lease}
    finally:
        try:
            mutex.unlink()
        except OSError:
            pass


def update_integration_lease(
    root: Path,
    action: str,
    *,
    session_id: str,
    branch: Optional[str] = None,
    worktree: Optional[str] = None,
) -> dict[str, Any]:
    if action not in {"heartbeat", "release", "revoke"}:
        return {"ok": False, "error": "invalid_integration_lease_action"}
    runtime_root = integration_runtime_root(root)
    try:
        mutex = _claim_mutex(runtime_root)
    except (OSError, RuntimeError) as exc:
        return {"ok": False, "error": str(exc)}
    try:
        lease = inspect_integration_lease(root)
        if lease is None:
            return {"ok": False, "error": "integration_lease_not_found"}
        if lease.get("session_id") != session_id:
            return {"ok": False, "error": "integration_session_mismatch", "lease": lease}
        if branch is not None and lease.get("base_branch") != branch:
            return {"ok": False, "error": "integration_branch_mismatch", "lease": lease}
        if worktree is not None and lease.get("worktree") != str(Path(worktree).resolve()):
            return {"ok": False, "error": "integration_worktree_mismatch", "lease": lease}
        if action == "heartbeat" and lease.get("lease_status") != "active":
            return {"ok": False, "error": "integration_lease_not_active", "lease": lease}
        lease.pop("stale", None)
        lease.pop("effective_lease_status", None)
        lease["updated_at"] = utc_now()
        if action in {"release", "revoke"}:
            lease["lease_status"] = "released" if action == "release" else "revoked"
            lease[f"{lease['lease_status']}_at"] = lease["updated_at"]
        _atomic_claim_update(_integration_lease_path(root), lease)
        return {"ok": True, "lease": inspect_integration_lease(root)}
    finally:
        try:
            mutex.unlink()
        except OSError:
            pass


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(root: Path) -> Optional[dict[str, Any]]:
    path = root / ".wishgraph" / "config.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read {path.relative_to(root)}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(".wishgraph/config.json must contain a JSON object")
    if "session_start_context_mode" not in data:
        legacy_injection = data.get("inject_project_summary_on_session_start")
        if isinstance(legacy_injection, bool):
            data = dict(data)
            data["session_start_context_mode"] = (
                "discussion_summary" if legacy_injection else "safety_only"
            )
    configured_paths = data.get("paths")
    if isinstance(configured_paths, dict):
        legacy_path = configured_paths.get("dev_report")
        if legacy_path and not configured_paths.get("project_status"):
            configured_paths = dict(configured_paths)
            configured_paths["project_status"] = legacy_path
            data = dict(data)
            data["paths"] = configured_paths
    config = deep_merge(DEFAULT_CONFIG, data)
    context_mode = config.get("session_start_context_mode")
    if context_mode not in {"safety_only", "discussion_summary", "off"}:
        raise ValueError(
            "session_start_context_mode must be safety_only, discussion_summary, or off"
        )
    return config


def configured_task_globs(config: dict[str, Any]) -> list[str]:
    """Return the visible task path first while retaining legacy compatibility."""
    paths = config["paths"]
    configured = paths.get("task_globs", [])
    if isinstance(configured, str):
        configured = [configured]
    candidates = [paths.get("task_glob", ""), *configured]
    return list(
        dict.fromkeys(
            pattern for pattern in candidates if isinstance(pattern, str) and pattern
        )
    )


def nul_paths(data: bytes) -> set[str]:
    return {
        item.decode("utf-8", errors="surrogateescape")
        for item in data.split(b"\0")
        if item
    }


def changed_paths(root: Path, scope: str) -> set[str]:
    if scope == "staged":
        return nul_paths(run_git(root, "diff", "--cached", "--name-only", "-z").stdout)
    staged = nul_paths(run_git(root, "diff", "--cached", "--name-only", "-z").stdout)
    unstaged = nul_paths(run_git(root, "diff", "--name-only", "-z").stdout)
    untracked = nul_paths(
        run_git(root, "ls-files", "--others", "--exclude-standard", "-z").stdout
    )
    return staged | unstaged | untracked


def changed_path_statuses(root: Path, scope: str) -> list[tuple[str, str, Optional[str]]]:
    """Return Git name-status records, including old/new paths for detected renames."""
    if scope == "staged":
        args = ("diff", "--cached", "--name-status", "--find-renames", "-z", "--")
    else:
        head = run_git(root, "rev-parse", "--verify", "HEAD", check=False)
        if head.returncode != 0:
            # An unborn repository has no committed paths to delete or rename.
            return []
        args = ("diff", "HEAD", "--name-status", "--find-renames", "-z", "--")
    fields = run_git(root, *args).stdout.split(b"\0")
    records: list[tuple[str, str, Optional[str]]] = []
    index = 0
    while index < len(fields) and fields[index]:
        status = fields[index].decode("utf-8", errors="replace")
        index += 1
        if status.startswith(("R", "C")):
            if index + 1 >= len(fields):
                break
            old_path = fields[index].decode("utf-8", errors="surrogateescape")
            new_path = fields[index + 1].decode("utf-8", errors="surrogateescape")
            index += 2
            records.append((status, old_path, new_path))
        else:
            if index >= len(fields):
                break
            path = fields[index].decode("utf-8", errors="surrogateescape")
            index += 1
            records.append((status, path, None))
    return records


def matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def read_version(root: Path, path: str, scope: str) -> Optional[str]:
    if scope == "staged":
        try:
            result = run_git(root, "show", f":{path}")
        except subprocess.CalledProcessError:
            return None
        return result.stdout.decode("utf-8", errors="replace")
    try:
        return (root / path).read_text(encoding="utf-8")
    except OSError:
        return None


def project_status_candidates(config: dict[str, Any]) -> list[str]:
    configured = config["paths"].get("project_status", DEFAULT_PROJECT_STATUS_PATH)
    return list(
        dict.fromkeys(
            [configured, DEFAULT_PROJECT_STATUS_PATH, LEGACY_PROJECT_STATUS_PATH]
        )
    )


def resolve_project_status_path(
    root: Path, config: dict[str, Any], scope: str = "worktree"
) -> str:
    for path in project_status_candidates(config):
        if read_version(root, path, scope) is not None:
            return path
    return config["paths"].get("project_status", DEFAULT_PROJECT_STATUS_PATH)


def standard_project_status_conflict(root: Path, scope: str) -> bool:
    return (
        read_version(root, DEFAULT_PROJECT_STATUS_PATH, scope) is not None
        and read_version(root, LEGACY_PROJECT_STATUS_PATH, scope) is not None
    )


def read_head_version(root: Path, path: str) -> Optional[str]:
    try:
        result = run_git(root, "show", f"HEAD:{path}")
    except subprocess.CalledProcessError:
        return None
    return result.stdout.decode("utf-8", errors="replace")


def report_paths_in_ref(root: Path, ref: str, prefix: str) -> set[str]:
    try:
        result = run_git(root, "ls-tree", "-r", "--name-only", "-z", ref, "--", prefix)
    except subprocess.CalledProcessError:
        return set()
    return nul_paths(result.stdout)


def report_contents_across_refs(
    root: Path, config: dict[str, Any]
) -> dict[str, str]:
    prefix = config["paths"]["run_report_glob"].split("*", 1)[0].rstrip("/")
    contents: dict[str, str] = {}
    for path in root.glob(f"{prefix}/**/*.md"):
        relative = path.relative_to(root).as_posix()
        try:
            contents[relative] = path.read_text(encoding="utf-8")
        except OSError:
            continue
    if not config.get("scan_worker_refs_for_status", True):
        return contents
    try:
        refs_result = run_git(
            root,
            "for-each-ref",
            "--format=%(refname)",
            "refs/heads",
            "refs/remotes",
        )
    except subprocess.CalledProcessError:
        return contents
    refs = refs_result.stdout.decode("utf-8", errors="replace").splitlines()
    for ref in refs:
        if ref.endswith("/HEAD"):
            continue
        for path in report_paths_in_ref(root, ref, prefix):
            if path in contents:
                continue
            try:
                value = run_git(root, "show", f"{ref}:{path}").stdout
            except subprocess.CalledProcessError:
                continue
            contents[path] = value.decode("utf-8", errors="replace")
    return contents
