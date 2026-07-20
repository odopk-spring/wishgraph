"""Git and repository-state boundary for the WishGraph hook runtime."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import socket
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Optional


DEFAULT_CONFIG: dict[str, Any] = {
    "version": 12,
    "runtime_version": 28,
    "mode": "enforce",
    "required_hosts": ["codex", "claude"],
    "paths": {
        "prd": "PRD.md",
        "architecture": "ARCHITECTURE.md",
        "codemap": "CODEMAP.md",
        "conventions": "CONVENTIONS.md",
        "project_status": "reports/PROJECT_STATUS.md",
        "run_report_glob": "reports/runs/*.md",
        "run_report_template": "reports/runs/{work_unit_id}-attempt-{attempt}.md",
        "task_glob": "tasks/*.md",
        "task_globs": ["tasks/*.md"],
        "revision_glob": "tasks/revisions/*.md",
    },
    "required_impact_rows": [
        "PRD.md",
        "ARCHITECTURE.md",
        "CODEMAP.md",
        "CONVENTIONS.md",
    ],
    "ignore_globs": [
        ".git/**",
        ".wishgraph",
        ".wishgraph/**",
        ".codex/hooks.json",
        ".codex/agents/wishgraph-worker.toml",
        ".claude/settings.json",
        ".claude/agents/wishgraph-worker.md",
        ".DS_Store",
        "**/.DS_Store",
        "**/__pycache__/**",
        "**/.pytest_cache/**",
    ],
    "allow_noop_with_reason": True,
    "scan_worker_refs_for_status": True,
    "project_status_max_lines": 160,
    "project_status_max_chars": 12000,
    "session_summary_max_chars": 2000,
    "orchestration_gate_enabled": True,
    "read_gate_mode": "host_dependent",
}

DEFAULT_PROJECT_STATUS_PATH = "reports/PROJECT_STATUS.md"
FORMAL_WORKER_CONTAINER_KINDS = {
    "manual_worker_window",
    "codex_agent_thread",
    "claude_background_session",
}
KNOWN_REQUIRED_HOSTS = ("codex", "claude")
EXECUTION_RUN_PHASES = {
    "dispatching",
    "running",
    "succeeded",
    "failed",
    "decision_required",
    "integrating",
    "integrated",
}


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
            path == ".wishgraph"
            or path.startswith(".wishgraph/")
            or path
            in {
                ".codex/hooks.json",
                ".codex/agents/wishgraph-worker.toml",
                ".claude/settings.json",
                ".claude/agents/wishgraph-worker.md",
            }
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


def authority_runtime_root(root: Path) -> Path:
    """Return the shared mutex root for Claim and Integration authority."""
    return git_common_dir(root) / "wishgraph" / "authority"


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
    agent_platform: str = "unknown",
    revision_id: Optional[str] = None,
    allowed_scope: Optional[list[str]] = None,
    validation_plan: Optional[list[str]] = None,
    execution_ownership: str = "worker_claim",
    discussion_session_id: Optional[str] = None,
    container_kind: str = "manual_worker_window",
    agent_kind: str = "formal_worker",
    stale_after_seconds: int = 3600,
    require_clean: bool = True,
) -> dict[str, Any]:
    """Atomically acquire a repository-wide Worker Claim for one Task attempt."""
    if agent_kind != "formal_worker":
        return {"ok": False, "error": "helper_agent_cannot_acquire_worker_claim"}
    if container_kind not in FORMAL_WORKER_CONTAINER_KINDS:
        return {"ok": False, "error": "formal_worker_container_required"}
    if execution_mode not in {"exclusive", "competitive"}:
        return {"ok": False, "error": "invalid_execution_mode"}
    if attempt < 1:
        return {"ok": False, "error": "invalid_attempt"}
    if require_clean and not worktree_is_clean(root):
        return {"ok": False, "error": "worktree_not_clean"}
    bound_branch = branch or current_branch(root)
    bound_worktree = str(Path(worktree).resolve()) if worktree else str(root.resolve())
    task_dir = _task_claim_dir(root, task_id)
    authority_mutex: Optional[Path] = None
    task_mutex: Optional[Path] = None
    try:
        authority_mutex = _claim_mutex(authority_runtime_root(root))
        task_mutex = _claim_mutex(task_dir)
    except (OSError, RuntimeError) as exc:
        if authority_mutex is not None:
            try:
                authority_mutex.unlink()
            except OSError:
                pass
        return {"ok": False, "error": str(exc)}
    try:
        integration_lease = inspect_integration_lease(root)
        if (
            integration_lease
            and integration_lease.get("effective_lease_status") == "active"
        ):
            return {
                "ok": False,
                "error": "active_integration_lease_exists",
                "lease": integration_lease,
            }
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
        base_commit_result = run_git(root, "rev-parse", "HEAD", check=False)
        base_commit = (
            base_commit_result.stdout.decode("utf-8", errors="replace").strip()
            if base_commit_result.returncode == 0
            else ""
        )
        claim = {
            "schema_version": 1,
            "kind": "worker_claim",
            "claim_id": claim_id,
            "task_id": task_id,
            "revision_id": revision_id,
            "work_unit_id": revision_id or task_id,
            "attempt_id": f"{revision_id or task_id}-attempt-{attempt}",
            "attempt": attempt,
            "worker_id": worker_id,
            "branch": bound_branch,
            "worktree": bound_worktree,
            "base_commit": base_commit,
            "started_at": now,
            "updated_at": now,
            "lease_status": "active",
            "execution_mode": execution_mode,
            "host": socket.gethostname(),
            "agent_platform": agent_platform,
            "host_thread_ref": host_thread_ref,
            "allowed_scope": list(allowed_scope or []),
            "validation_plan": list(validation_plan or []),
            "execution_ownership": execution_ownership,
            "discussion_session_id": discussion_session_id or "",
            "container_kind": container_kind,
            "agent_kind": agent_kind,
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
        for mutex in (task_mutex, authority_mutex):
            if mutex is not None:
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
    authority_mutex: Optional[Path] = None
    claim_mutex: Optional[Path] = None
    try:
        authority_mutex = _claim_mutex(authority_runtime_root(root))
        claim_mutex = _claim_mutex(path.parent)
    except (OSError, RuntimeError) as exc:
        if authority_mutex is not None:
            try:
                authority_mutex.unlink()
            except OSError:
                pass
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
        for mutex in (claim_mutex, authority_mutex):
            if mutex is not None:
                try:
                    mutex.unlink()
                except OSError:
                    pass


def rebind_worker_claim(
    root: Path,
    *,
    session_id: str,
    old_claim_id: str,
    old_task_status: str,
    next_task_id: str,
    attempt: int,
    worker_id: str,
    revision_id: Optional[str] = None,
    branch: Optional[str] = None,
    worktree: Optional[str] = None,
    host_thread_ref: Optional[str] = None,
    agent_platform: str = "unknown",
    allowed_scope: Optional[list[str]] = None,
    validation_plan: Optional[list[str]] = None,
    execution_ownership: str = "worker_claim",
    container_kind: str = "manual_worker_window",
    agent_kind: str = "formal_worker",
    require_clean: bool = True,
) -> dict[str, Any]:
    """Release a terminal binding, then acquire and persist one fresh binding.

    Failure after release leaves the reusable Worker idle; it never restores stale
    scope or authority from the previous Task.
    """
    if old_task_status not in {
        "completed",
        "blocked",
        "incomplete",
        "stopped",
        "abandoned",
        "integrated",
        "reviewed",
    }:
        return {"ok": False, "error": "old_task_not_terminal"}
    if not allowed_scope or not validation_plan:
        return {"ok": False, "error": "new_binding_scope_or_validation_missing"}

    old_matches = [
        claim for claim in inspect_claims(root) if claim.get("claim_id") == old_claim_id
    ]
    if len(old_matches) != 1:
        return {"ok": False, "error": "old_claim_not_found"}
    old_claim = old_matches[0]
    if old_claim.get("effective_lease_status") == "active":
        released = update_claim(
            root,
            old_claim_id,
            "release",
            branch=old_claim.get("branch"),
            worktree=old_claim.get("worktree"),
        )
        if not released.get("ok"):
            return released
    elif old_claim.get("lease_status") == "released":
        released = {"ok": True, "claim": old_claim}
    else:
        return {"ok": False, "error": "old_claim_not_released", "claim": old_claim}

    acquired = acquire_claim(
        root,
        next_task_id,
        attempt,
        worker_id,
        branch=branch,
        worktree=worktree,
        host_thread_ref=host_thread_ref,
        agent_platform=agent_platform,
        revision_id=revision_id,
        allowed_scope=allowed_scope,
        validation_plan=validation_plan,
        execution_ownership=execution_ownership,
        discussion_session_id=str(old_claim.get("discussion_session_id") or ""),
        container_kind=container_kind,
        agent_kind=agent_kind,
        require_clean=require_clean,
    )
    if not acquired.get("ok"):
        apply_session_runtime_patch(
            root,
            session_id,
            {
                "worker_runtime": {
                    "claim_id": "",
                    "previous_task_id": old_claim.get("task_id", ""),
                    "previous_claim_id": old_claim_id,
                    "active_task_id": "",
                    "active_revision_id": "",
                    "binding_status": "unbound",
                    "worker_availability": "idle",
                    "allowed_scope": [],
                    "validation_plan": [],
                    "execution_ownership": "",
                }
            },
        )
        return {
            **acquired,
            "old_claim_released": True,
            "old_claim": released.get("claim"),
        }

    new_claim = acquired["claim"]
    runtime_result = apply_session_runtime_patch(
        root,
        session_id,
        {
            "worker_runtime": {
                "claim_id": new_claim["claim_id"],
                "previous_task_id": old_claim.get("task_id", ""),
                "previous_claim_id": old_claim_id,
                "active_task_id": next_task_id,
                "active_revision_id": revision_id or "",
                "branch": new_claim["branch"],
                "worktree": new_claim["worktree"],
                "host_window_or_thread_id": host_thread_ref or "",
                "worker_session_id": session_id,
                "discussion_session_id": str(
                    new_claim.get("discussion_session_id") or ""
                ),
                "worker_availability": "busy",
                "binding_status": "active",
                "allowed_scope": list(allowed_scope),
                "validation_plan": list(validation_plan),
                "execution_ownership": execution_ownership,
                "worker_handle": {
                    "host": agent_platform,
                    "container_kind": container_kind,
                    "thread_or_session_id": host_thread_ref or session_id,
                    "parent_discussion_id": str(
                        new_claim.get("discussion_session_id") or ""
                    ),
                    "task_id": next_task_id,
                    "claim_id": new_claim["claim_id"],
                    "branch": new_claim["branch"],
                    "worktree": new_claim["worktree"],
                    "inspectable": True,
                    "controllable": True,
                    "terminal_state": "running",
                    "last_observed_at": new_claim["updated_at"],
                },
            }
        },
    )
    if not runtime_result.get("ok"):
        update_claim(root, new_claim["claim_id"], "release")
        return {
            "ok": False,
            "error": "new_claim_acquired_but_runtime_persistence_failed",
            "old_claim_released": True,
            "new_claim_released": True,
        }
    return {
        "ok": True,
        "old_claim_released": True,
        "old_claim": released.get("claim"),
        "claim": new_claim,
        "runtime": runtime_result.get("runtime"),
    }


RUNTIME_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
HOST_OBSERVATION_EVENTS = ("session-start", "user-prompt-submit")


def canonical_runtime_id(value: Any) -> str:
    """Normalize the one known host path wrapper, then require a stable ID."""
    candidate = str(value or "").strip()
    if candidate.startswith("/root/") and candidate.count("/") == 2:
        candidate = candidate.removeprefix("/root/")
    return candidate if RUNTIME_ID_RE.fullmatch(candidate) else ""


def host_observation_root(root: Path) -> Path:
    """Keep host liveness evidence outside the worktree and project history."""
    return git_common_dir(root) / "wishgraph" / "host-observations"


def _host_observation_path(root: Path, host: str, event: str) -> Path:
    if host not in {"codex", "claude"}:
        raise ValueError("invalid_host_observation_host")
    if event not in HOST_OBSERVATION_EVENTS:
        raise ValueError("invalid_host_observation_event")
    return host_observation_root(root) / host / f"{event}.json"


def record_host_observation(
    root: Path, host: str, event: str, runtime_version: Any
) -> dict[str, Any]:
    """Record one low-frequency proof that the selected host invoked WishGraph."""
    try:
        path = _host_observation_path(root, host, event)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    if isinstance(runtime_version, bool) or not isinstance(runtime_version, int):
        return {"ok": False, "error": "invalid_host_observation_runtime_version"}
    record = {
        "schema_version": 1,
        "kind": "host_observation",
        "host": host,
        "event": event,
        "runtime_version": runtime_version,
        "observed_at": utc_now(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
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
        return {"ok": False, "error": "host_observation_write_failed", "detail": str(exc)}
    return {"ok": True, "observation": record}


def read_host_observations(root: Path, host: str) -> list[dict[str, Any]]:
    """Read only the two bounded host-observation files used by Doctor."""
    observations: list[dict[str, Any]] = []
    for event in HOST_OBSERVATION_EVENTS:
        try:
            path = _host_observation_path(root, host, event)
            value = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError, json.JSONDecodeError):
            continue
        if (
            isinstance(value, dict)
            and value.get("kind") == "host_observation"
            and value.get("host") == host
            and value.get("event") == event
        ):
            observations.append(value)
    return observations


def session_runtime_root(root: Path) -> Path:
    return git_common_dir(root) / "wishgraph" / "sessions"


def _session_runtime_path(root: Path, session_id: str) -> Path:
    session_id = canonical_runtime_id(session_id)
    if not session_id:
        raise ValueError("invalid_session_id")
    return session_runtime_root(root) / f"{session_id}.json"


def write_session_runtime(
    root: Path, session_id: str, runtime: dict[str, Any]
) -> dict[str, Any]:
    """Atomically persist host/session orchestration state outside the worktree."""
    session_id = canonical_runtime_id(session_id)
    if not session_id:
        return {"ok": False, "error": "invalid_session_id"}
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
    session_id = canonical_runtime_id(session_id)
    if not session_id:
        return None
    try:
        path = _session_runtime_path(root, session_id)
        value = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def apply_session_runtime_patch(
    root: Path,
    session_id: str,
    patch: dict[str, Any],
    *,
    replace_keys: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Atomically merge a patch, optionally replacing complete identity objects."""
    if not isinstance(patch, dict):
        return {"ok": False, "error": "session_runtime_patch_must_be_object"}
    if any(not isinstance(key, str) or not key for key in replace_keys):
        return {"ok": False, "error": "session_runtime_replace_keys_must_be_strings"}
    try:
        runtime_path = _session_runtime_path(root, session_id)
        mutex = _claim_mutex(runtime_path.parent)
    except (ValueError, OSError, RuntimeError) as exc:
        return {"ok": False, "error": str(exc)}
    try:
        current = read_session_runtime(root, session_id) or {}
        merged = deep_merge(current, patch)
        for key in replace_keys:
            if key in patch:
                merged[key] = patch[key]
        return write_session_runtime(root, session_id, merged)
    finally:
        try:
            mutex.unlink()
        except OSError:
            pass


def execution_run_root(root: Path) -> Path:
    """Return the one shared runtime directory for canonical execution facts."""
    return git_common_dir(root) / "wishgraph" / "runs"


def execution_run_id(task_id: str, attempt: int, revision_id: str = "") -> str:
    work_unit_id = revision_id or task_id
    if not re.fullmatch(r"\d{3,}[a-z]*(?:-r[1-9]\d*)?", work_unit_id):
        raise ValueError("invalid_execution_run_work_unit_id")
    if attempt < 1:
        raise ValueError("invalid_execution_run_attempt")
    return f"{work_unit_id}-attempt-{attempt}"


def _execution_run_path(root: Path, run_id: str) -> Path:
    if not re.fullmatch(r"\d{3,}[a-z]*(?:-r[1-9]\d*)?-attempt-[1-9]\d*", run_id):
        raise ValueError("invalid_execution_run_id")
    return execution_run_root(root) / f"{run_id}.json"


def content_fingerprint(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def read_execution_run(root: Path, run_id: str) -> Optional[dict[str, Any]]:
    """Read one canonical Run; session/runtime projections are never consulted."""
    try:
        value = json.loads(_execution_run_path(root, run_id).read_text(encoding="utf-8"))
    except (ValueError, OSError, json.JSONDecodeError):
        return None
    if (
        not isinstance(value, dict)
        or value.get("kind") != "execution_run"
        or value.get("run_id") != run_id
    ):
        return None
    return value


def inspect_execution_runs(
    root: Path, task_id: Optional[str] = None
) -> list[dict[str, Any]]:
    """Read the bounded Run ledger without scanning Tasks, reports, or source."""
    directory = execution_run_root(root)
    try:
        paths = sorted(directory.glob("*.json"))
    except OSError:
        return []
    runs: list[dict[str, Any]] = []
    for path in paths:
        run = read_execution_run(root, path.stem)
        if run is None or (task_id and run.get("task_id") != task_id):
            continue
        runs.append(run)
    return runs


def latest_execution_run(
    root: Path, task_id: str, *, attempt: Optional[int] = None
) -> Optional[dict[str, Any]]:
    candidates = [
        run
        for run in inspect_execution_runs(root, task_id)
        if attempt is None or run.get("attempt") == attempt
    ]
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (int(item.get("attempt") or 0), str(item.get("updated_at") or "")),
        reverse=True,
    )
    return candidates[0]


def update_execution_run(
    root: Path,
    *,
    task_id: str,
    attempt: int,
    patch: dict[str, Any],
    revision_id: str = "",
    create: bool = False,
) -> dict[str, Any]:
    """Atomically create or advance the single canonical Run record.

    The Run owns authorization, Worker binding, terminal evidence, and Integration
    outcome. Session state, notifications, and status output are projections only.
    """
    if not isinstance(patch, dict):
        return {"ok": False, "error": "execution_run_patch_must_be_object"}
    try:
        run_id = execution_run_id(task_id, attempt, revision_id)
        path = _execution_run_path(root, run_id)
        mutex = _claim_mutex(execution_run_root(root))
    except (ValueError, OSError, RuntimeError) as exc:
        return {"ok": False, "error": str(exc)}
    try:
        current = read_execution_run(root, run_id)
        if current is None and not create:
            return {"ok": False, "error": "execution_run_not_found"}
        if current is None:
            current = {
                "schema_version": 1,
                "kind": "execution_run",
                "run_id": run_id,
                "task_id": task_id,
                "revision_id": revision_id or None,
                "attempt": attempt,
                "phase": "dispatching",
                "authorization": {},
                "worker": {},
                "claim_id": "",
                "result": {},
                "created_at": utc_now(),
            }
        immutable = {
            "run_id": run_id,
            "task_id": task_id,
            "revision_id": revision_id or None,
            "attempt": attempt,
        }
        merged = deep_merge(current, patch)
        # These are complete canonical snapshots, not partial reducer patches.
        # Replacement prevents old Worker IDs, launch errors, and results from
        # leaking into a retry when the new snapshot is intentionally empty.
        for snapshot_key in (
            "authorization",
            "worker",
            "result",
            "last_error",
            "integration",
        ):
            if snapshot_key in patch:
                merged[snapshot_key] = patch[snapshot_key]
        if any(merged.get(key) != value for key, value in immutable.items()):
            return {"ok": False, "error": "execution_run_identity_is_immutable"}
        phase = str(merged.get("phase") or "")
        if phase not in EXECUTION_RUN_PHASES:
            return {"ok": False, "error": "invalid_execution_run_phase"}
        merged.update(immutable)
        merged["schema_version"] = 1
        merged["kind"] = "execution_run"
        merged["updated_at"] = utc_now()
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_claim_update(path, merged)
        return {"ok": True, "run": read_execution_run(root, run_id)}
    finally:
        try:
            mutex.unlink()
        except OSError:
            pass


def read_ref_version(root: Path, ref: str, path: str) -> Optional[str]:
    """Read one exact path from one exact commit/ref without scanning refs."""
    if not ref or not path or path.startswith("/") or ".." in Path(path).parts:
        return None
    result = run_git(root, "show", f"{ref}:{path}", check=False)
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", errors="replace")


WORKER_NOTIFICATION_EVENTS = {"completed", "failed", "decision_required"}
RECENT_READ_NOTIFICATION_LIMIT = 32


def worker_notification_root(root: Path) -> Path:
    """Store the cross-host inbox beside Claims, never in project history."""
    return git_common_dir(root) / "wishgraph" / "notifications"


def _worker_notification_path(root: Path) -> Path:
    return worker_notification_root(root) / "inbox.json"


def _read_worker_notification_state(root: Path) -> dict[str, Any]:
    try:
        value = json.loads(_worker_notification_path(root).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        value = {}
    notifications = value.get("notifications") if isinstance(value, dict) else None
    seen_ids = value.get("seen_notification_ids") if isinstance(value, dict) else None
    return {
        "schema_version": 1,
        "kind": "worker_notification_inbox",
        "notifications": (
            [item for item in notifications if isinstance(item, dict)]
            if isinstance(notifications, list)
            else []
        ),
        "seen_notification_ids": (
            [item for item in seen_ids if isinstance(item, str) and item]
            if isinstance(seen_ids, list)
            else []
        ),
    }


def _write_worker_notification_state(root: Path, state: dict[str, Any]) -> None:
    path = _worker_notification_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_claim_update(path, state)


def inspect_worker_notifications(
    root: Path, status: Optional[str] = None
) -> list[dict[str, Any]]:
    """Read the single inbox file; never enumerate the project or source tree."""
    notifications = _read_worker_notification_state(root)["notifications"]
    if status is not None:
        notifications = [item for item in notifications if item.get("status") == status]
    return [dict(item) for item in notifications]


def enqueue_worker_notification(
    root: Path,
    *,
    task_id: str,
    work_unit_id: str,
    attempt: int,
    terminal_event: str,
    task_lifecycle: str,
    run_report: str,
    claim_id: str,
    worker_session_id: str = "",
    discussion_session_id: str = "",
    agent_platform: str = "unknown",
    next_action: str = "",
    reason: str = "",
    run_id: str = "",
) -> dict[str, Any]:
    """Idempotently append one durable Worker terminal notification."""
    if terminal_event not in WORKER_NOTIFICATION_EVENTS:
        return {"ok": False, "error": "invalid_worker_notification_event"}
    if not task_id or not work_unit_id or attempt < 1 or not run_report or not claim_id:
        return {"ok": False, "error": "worker_notification_binding_incomplete"}
    worker_session_id = canonical_runtime_id(worker_session_id) if worker_session_id else ""
    discussion_session_id = (
        canonical_runtime_id(discussion_session_id) if discussion_session_id else ""
    )
    for runtime_id in (worker_session_id, discussion_session_id):
        if runtime_id and not RUNTIME_ID_RE.fullmatch(runtime_id):
            return {"ok": False, "error": "invalid_notification_session_id"}

    event_key = "|".join(
        (
            claim_id,
            work_unit_id,
            str(attempt),
            terminal_event,
            task_lifecycle,
            run_report,
        )
    )
    notification_id = uuid.uuid5(uuid.NAMESPACE_URL, f"wishgraph:{event_key}").hex
    inbox_root = worker_notification_root(root)
    try:
        mutex = _claim_mutex(inbox_root)
    except (OSError, RuntimeError) as exc:
        return {"ok": False, "error": str(exc)}
    try:
        state = _read_worker_notification_state(root)
        for existing in state["notifications"]:
            if existing.get("notification_id") == notification_id:
                return {
                    "ok": True,
                    "created": False,
                    "notification": dict(existing),
                }
        if notification_id in state["seen_notification_ids"]:
            return {
                "ok": True,
                "created": False,
                "notification": {
                    "notification_id": notification_id,
                    "status": "read",
                },
            }
        now = utc_now()
        notification = {
            "schema_version": 1,
            "kind": "worker_terminal_notification",
            "notification_id": notification_id,
            "task_id": task_id,
            "work_unit_id": work_unit_id,
            "attempt": attempt,
            "terminal_event": terminal_event,
            "task_lifecycle": task_lifecycle,
            "run_report": run_report,
            "claim_id": claim_id,
            "worker_session_id": worker_session_id,
            "discussion_session_id": discussion_session_id,
            "agent_platform": agent_platform,
            "next_action": next_action,
            "reason": reason,
            "run_id": run_id,
            "status": "pending",
            "created_at": now,
            "read_at": "",
            "read_by_session_id": "",
        }
        state["notifications"].append(notification)
        state["seen_notification_ids"].append(notification_id)
        state["updated_at"] = now
        _write_worker_notification_state(root, state)
        return {"ok": True, "created": True, "notification": notification}
    except OSError as exc:
        return {
            "ok": False,
            "error": "worker_notification_write_failed",
            "detail": str(exc),
        }
    finally:
        try:
            mutex.unlink()
        except OSError:
            pass


def consume_worker_notifications(
    root: Path,
    discussion_session_id: str,
    *,
    adopt_project_pending: bool = False,
    limit: int = 10,
) -> dict[str, Any]:
    """Atomically mark a bounded batch read when Discussion is activated."""
    discussion_session_id = canonical_runtime_id(discussion_session_id)
    if not discussion_session_id:
        return {"ok": False, "error": "invalid_discussion_session_id"}
    if limit < 1 or limit > 20:
        return {"ok": False, "error": "invalid_notification_consume_limit"}
    inbox_path = _worker_notification_path(root)
    if not inbox_path.is_file():
        return {"ok": True, "notifications": [], "remaining_pending": 0}
    preview = _read_worker_notification_state(root)
    preview_pending = [
        item for item in preview["notifications"] if item.get("status") == "pending"
    ]
    eligible = any(
        str(item.get("discussion_session_id") or "")
        in {"", discussion_session_id}
        or adopt_project_pending
        for item in preview_pending
    )
    if not eligible:
        return {
            "ok": True,
            "notifications": [],
            "remaining_pending": len(preview_pending),
        }
    inbox_root = worker_notification_root(root)
    try:
        mutex = _claim_mutex(inbox_root)
    except (OSError, RuntimeError) as exc:
        return {"ok": False, "error": str(exc)}
    try:
        state = _read_worker_notification_state(root)
        selected: list[dict[str, Any]] = []
        for notification in state["notifications"]:
            if notification.get("status") != "pending":
                continue
            target = str(notification.get("discussion_session_id") or "")
            if not (
                target == discussion_session_id
                or not target
                or adopt_project_pending
            ):
                continue
            if len(selected) >= limit:
                break
            selected.append(notification)
        if not selected:
            return {"ok": True, "notifications": [], "remaining_pending": sum(
                item.get("status") == "pending" for item in state["notifications"]
            )}
        now = utc_now()
        for notification in selected:
            notification["status"] = "read"
            notification["read_at"] = now
            notification["read_by_session_id"] = discussion_session_id

        read_records = [
            item for item in state["notifications"] if item.get("status") == "read"
        ]
        keep_read_ids = {
            str(item.get("notification_id") or "")
            for item in read_records[-RECENT_READ_NOTIFICATION_LIMIT:]
        }
        state["notifications"] = [
            item
            for item in state["notifications"]
            if item.get("status") == "pending"
            or str(item.get("notification_id") or "") in keep_read_ids
        ]
        state["updated_at"] = now
        _write_worker_notification_state(root, state)
        return {
            "ok": True,
            "notifications": [dict(item) for item in selected],
            "remaining_pending": sum(
                item.get("status") == "pending" for item in state["notifications"]
            ),
        }
    except OSError as exc:
        return {
            "ok": False,
            "error": "worker_notification_consume_failed",
            "detail": str(exc),
        }
    finally:
        try:
            mutex.unlink()
        except OSError:
            pass


def integration_runtime_root(root: Path) -> Path:
    return git_common_dir(root) / "wishgraph" / "integration"


def _integration_lease_path(root: Path) -> Path:
    return integration_runtime_root(root) / "lease.json"


def _integration_grant_path(root: Path, grant_id: str) -> Path:
    if not RUNTIME_ID_RE.fullmatch(grant_id):
        raise ValueError("invalid_integration_grant_id")
    return integration_runtime_root(root) / "grants" / f"{grant_id}.json"


def inspect_integration_grant(
    root: Path, grant_id: str
) -> Optional[dict[str, Any]]:
    try:
        value = json.loads(
            _integration_grant_path(root, grant_id).read_text(encoding="utf-8")
        )
    except (ValueError, OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def create_integration_transition_grant(
    root: Path,
    *,
    session_id: str,
    integration_id: str,
    task_ids: list[str],
    reports: list[str],
    outcome: str,
    branch: Optional[str] = None,
    worktree: Optional[str] = None,
) -> dict[str, Any]:
    """Persist one short-lived reducer receipt for an exact Integration selection."""
    if not RUNTIME_ID_RE.fullmatch(session_id):
        return {"ok": False, "error": "invalid_session_id"}
    if outcome not in {"safe", "decision_confirmed"}:
        return {"ok": False, "error": "invalid_integration_grant_outcome"}
    if not integration_id or not task_ids or len(task_ids) != len(reports):
        return {"ok": False, "error": "integration_binding_incomplete"}
    runtime = read_session_runtime(root, session_id) or {}
    session = runtime.get("session") if isinstance(runtime.get("session"), dict) else {}
    provenance = (
        runtime.get("session_provenance")
        if isinstance(runtime.get("session_provenance"), dict)
        else {}
    )
    if (
        session.get("role") != "discussion"
        or session.get("phase") != "integrating"
        or provenance.get("initial_role") != "neutral"
        or provenance.get("discussion_authorized") is not True
    ):
        return {"ok": False, "error": "verified_discussion_transition_required"}
    bound_branch = branch or current_branch(root)
    bound_worktree = str(Path(worktree).resolve()) if worktree else str(root.resolve())
    if bound_branch != current_branch(root):
        return {"ok": False, "error": "integration_branch_mismatch"}
    if bound_worktree != str(root.resolve()):
        return {"ok": False, "error": "integration_worktree_mismatch"}

    authority_mutex: Optional[Path] = None
    integration_mutex: Optional[Path] = None
    try:
        authority_mutex = _claim_mutex(authority_runtime_root(root))
        integration_mutex = _claim_mutex(integration_runtime_root(root))
    except (OSError, RuntimeError) as exc:
        if authority_mutex is not None:
            try:
                authority_mutex.unlink()
            except OSError:
                pass
        return {"ok": False, "error": str(exc)}
    try:
        existing = inspect_integration_lease(root)
        if existing and existing.get("effective_lease_status") == "active":
            return {
                "ok": False,
                "error": "active_integration_lease_exists",
                "lease": existing,
            }
        grant_id = uuid.uuid4().hex
        now = utc_now()
        grant = {
            "schema_version": 1,
            "kind": "integration_transition_grant",
            "grant_id": grant_id,
            "discussion_session_id": session_id,
            "integration_id": integration_id,
            "selected_task_ids": list(task_ids),
            "selected_reports": list(reports),
            "outcome": outcome,
            "base_branch": bound_branch,
            "worktree": bound_worktree,
            "created_at": now,
            "consumed_at": "",
        }
        path = _integration_grant_path(root, grant_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_claim_update(path, grant)
        return {"ok": True, "grant": grant}
    finally:
        for mutex in (integration_mutex, authority_mutex):
            if mutex is not None:
                try:
                    mutex.unlink()
                except OSError:
                    pass


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
    grant_id: str,
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
    if not grant_id or not integration_id or not task_ids or not reports:
        return {"ok": False, "error": "integration_binding_incomplete"}
    if require_clean and not worktree_is_clean(root):
        return {"ok": False, "error": "worktree_not_clean"}
    runtime_root = integration_runtime_root(root)
    authority_mutex: Optional[Path] = None
    integration_mutex: Optional[Path] = None
    try:
        authority_mutex = _claim_mutex(authority_runtime_root(root))
        integration_mutex = _claim_mutex(runtime_root)
    except (OSError, RuntimeError) as exc:
        if authority_mutex is not None:
            try:
                authority_mutex.unlink()
            except OSError:
                pass
        return {"ok": False, "error": str(exc)}
    try:
        grant = inspect_integration_grant(root, grant_id)
        if grant is None:
            return {"ok": False, "error": "integration_transition_grant_not_found"}
        bound_branch = branch or current_branch(root)
        bound_worktree = (
            str(Path(worktree).resolve()) if worktree else str(root.resolve())
        )
        expected_binding = {
            "discussion_session_id": session_id,
            "integration_id": integration_id,
            "selected_task_ids": list(task_ids),
            "selected_reports": list(reports),
            "base_branch": bound_branch,
            "worktree": bound_worktree,
        }
        for field, expected in expected_binding.items():
            if grant.get(field) != expected:
                return {
                    "ok": False,
                    "error": "integration_transition_grant_mismatch",
                    "field": field,
                }
        if grant.get("consumed_at"):
            return {"ok": False, "error": "integration_transition_grant_consumed"}
        if grant.get("outcome") not in {"safe", "decision_confirmed"}:
            return {"ok": False, "error": "integration_transition_grant_invalid"}
        active_claims = [
            claim
            for task_id in task_ids
            for claim in inspect_claims(root, task_id, stale_after_seconds)
            if claim.get("effective_lease_status") == "active"
        ]
        if active_claims:
            return {
                "ok": False,
                "error": "active_worker_claim_exists",
                "claims": active_claims,
            }
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
        grant["consumed_at"] = now
        _atomic_claim_update(_integration_grant_path(root, grant_id), grant)
        lease = {
            "schema_version": 1,
            "kind": "integration_lease",
            "lease_id": uuid.uuid4().hex,
            "transition_grant_id": grant_id,
            "session_id": session_id,
            "integration_id": integration_id,
            "base_branch": bound_branch,
            "worktree": bound_worktree,
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
        for mutex in (integration_mutex, authority_mutex):
            if mutex is not None:
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
    authority_mutex: Optional[Path] = None
    integration_mutex: Optional[Path] = None
    try:
        authority_mutex = _claim_mutex(authority_runtime_root(root))
        integration_mutex = _claim_mutex(runtime_root)
    except (OSError, RuntimeError) as exc:
        if authority_mutex is not None:
            try:
                authority_mutex.unlink()
            except OSError:
                pass
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
        for mutex in (integration_mutex, authority_mutex):
            if mutex is not None:
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


def normalize_required_hosts(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("required_hosts must be a non-empty array")
    if not value:
        raise ValueError("required_hosts must not be empty; use mode off instead")
    if not all(isinstance(item, str) for item in value):
        raise ValueError("required_hosts entries must be strings")
    unknown = sorted(set(value) - set(KNOWN_REQUIRED_HOSTS))
    if unknown:
        raise ValueError(
            "required_hosts contains unknown hosts: " + ", ".join(unknown)
        )
    selected = set(value)
    return [host for host in KNOWN_REQUIRED_HOSTS if host in selected]


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
    if "required_hosts" not in data:
        raise ValueError("required_hosts is required; reactivate this project")
    config = deep_merge(DEFAULT_CONFIG, data)
    config["required_hosts"] = normalize_required_hosts(config.get("required_hosts"))
    config["required_hosts_source"] = "configured"
    try:
        allocate_run_report_path(config, "001", 1)
    except ValueError as exc:
        raise ValueError(f"invalid run report path configuration: {exc}") from exc
    return config


def canonical_repo_path(value: Any) -> str:
    """Return one portable repository-relative path or fail closed."""
    raw = str(value or "").strip().replace("\\", "/")
    if (
        not raw
        or raw.startswith(("/", "//"))
        or re.match(r"^[A-Za-z]:", raw)
        or "\x00" in raw
    ):
        raise ValueError("path must be repository-relative")
    if any(part in {"", ".", ".."} for part in raw.split("/")):
        raise ValueError("path must not contain empty, dot, or parent segments")
    path = PurePosixPath(raw)
    if path.parts and path.parts[0].lower() == ".git":
        raise ValueError("path must not target .git")
    return path.as_posix()


def allocate_run_report_path(
    config: dict[str, Any], work_unit_id: str, attempt: int
) -> str:
    """Allocate a Run Report once from project configuration."""
    template = config.get("paths", {}).get(
        "run_report_template", "reports/runs/{work_unit_id}-attempt-{attempt}.md"
    )
    if not isinstance(template, str) or not template:
        raise ValueError("paths.run_report_template must be a non-empty string")
    try:
        value = template.format(work_unit_id=work_unit_id, attempt=int(attempt))
    except (KeyError, ValueError) as exc:
        raise ValueError(
            "paths.run_report_template supports only {work_unit_id} and {attempt}"
        ) from exc
    path = canonical_repo_path(value)
    report_glob = str(
        config.get("paths", {}).get("run_report_glob") or "reports/runs/*.md"
    )
    if not fnmatch.fnmatch(path, report_glob):
        raise ValueError("allocated path must match paths.run_report_glob")
    return path


def configured_task_globs(config: dict[str, Any]) -> list[str]:
    """Return the configured visible Task paths without hidden legacy fallbacks."""
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


def configured_revision_glob(config: dict[str, Any]) -> str:
    value = config.get("paths", {}).get("revision_glob")
    return value if isinstance(value, str) and value else "tasks/revisions/*.md"


def matches_repo_glob(path: str, pattern: str) -> bool:
    """Match one repository path without letting `*` cross directory boundaries."""
    return PurePosixPath(path).match(pattern)


def task_paths_for_id(
    root: Path, config: dict[str, Any], task_id: str
) -> list[Path]:
    """List filename-bounded candidates without reading unrelated Task bodies."""
    matches: list[Path] = []
    seen: set[Path] = set()
    for task_glob in configured_task_globs(config):
        for path in root.glob(task_glob):
            if path in seen or path.name.startswith(("EXAMPLE-", "NNN-")):
                continue
            seen.add(path)
            if path.stem == task_id or path.stem.startswith(f"{task_id}-"):
                matches.append(path)
    return sorted(matches)


def revision_paths_for_parent(
    root: Path, config: dict[str, Any], parent_task_id: str
) -> list[Path]:
    """List only one parent's Revision candidates from their canonical filenames."""
    prefix = f"{parent_task_id}-r"
    return sorted(
        path
        for path in root.glob(configured_revision_glob(config))
        if path.stem.startswith(prefix)
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
    return list(dict.fromkeys([configured, DEFAULT_PROJECT_STATUS_PATH]))


def resolve_project_status_path(
    root: Path, config: dict[str, Any], scope: str = "worktree"
) -> str:
    for path in project_status_candidates(config):
        if read_version(root, path, scope) is not None:
            return path
    return config["paths"].get("project_status", DEFAULT_PROJECT_STATUS_PATH)


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


def report_contents_for_paths_across_refs(
    root: Path, config: dict[str, Any], paths: set[str]
) -> dict[str, str]:
    """Read only known report paths, avoiding recursive history-tree scans."""
    wanted = {path for path in paths if path}
    contents: dict[str, str] = {}
    for path in sorted(wanted):
        try:
            contents[path] = (root / path).read_text(encoding="utf-8")
        except OSError:
            continue
    if not wanted or not config.get("scan_worker_refs_for_status", True):
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
    for ref in refs_result.stdout.decode("utf-8", errors="replace").splitlines():
        if ref.endswith("/HEAD"):
            continue
        for path in sorted(wanted - contents.keys()):
            result = run_git(root, "show", f"{ref}:{path}", check=False)
            if result.returncode == 0:
                contents[path] = result.stdout.decode("utf-8", errors="replace")
    return contents
