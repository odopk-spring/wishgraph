"""Private Claude Code Worker provider behind host_adapter.py."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from git_state import (
    apply_session_runtime_patch,
    canonical_runtime_id,
    current_branch,
    find_git_root,
    inspect_claims,
    latest_execution_run,
    read_ref_version,
    read_session_runtime,
    update_execution_run,
)
from workflow_state import canonical_task_id


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

CLAUDE_BACKGROUND_SESSION = "background_session"

CLAUDE_FORKED_SUBAGENT = "forked_subagent"

CLAUDE_MANUAL_COMMAND_ONLY = "manual_command_only"

CLAUDE_WORKER_AGENT_MARKER = "<!-- wishgraph-managed: wishgraph-worker -->"

CLAUDE_BACKGROUND_ID_RE = re.compile(
    r"backgrounded\s*[·:]\s*(?P<session_id>[A-Za-z0-9._-]+)", re.IGNORECASE
)

CLAUDE_RUNNING_STATES = {"running", "working", "starting"}

CLAUDE_BLOCKED_STATES = {"blocked", "waiting"}

CLAUDE_COMPLETED_STATES = {
    "completed",
    "done",
    "finished",
    "ready",
    "succeeded",
    "success",
}

CLAUDE_FAILED_STATES = {"failed", "error", "stopped", "killed"}

CLAUDE_BACKGROUND_CONTAINER = "claude_background_session"


@dataclass(frozen=True)
class ClaudeWorkerCapability:
    tier: str
    claude_executable: str = ""
    agent_definition: str = ""
    supports_background: bool = False
    supports_agents_json: bool = False
    supports_worktree: bool = False
    supports_settings: bool = False
    supports_fork: bool = False
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "claude_executable": self.claude_executable,
            "agent_definition": self.agent_definition,
            "supports_background": self.supports_background,
            "supports_agents_json": self.supports_agents_json,
            "supports_worktree": self.supports_worktree,
            "supports_settings": self.supports_settings,
            "supports_fork": self.supports_fork,
            "reason": self.reason,
        }

def _claude_worker_agent_paths(root: Path) -> list[Path]:
    config_home = Path(
        os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude"
    ).expanduser()
    return [
        root / ".claude" / "agents" / "wishgraph-worker.md",
        config_home / "agents" / "wishgraph-worker.md",
    ]

def _managed_claude_worker_agent(root: Path) -> Optional[Path]:
    for path in _claude_worker_agent_paths(root):
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if CLAUDE_WORKER_AGENT_MARKER in content:
            return path.resolve()
    return None

def _claude_worker_settings_json() -> str:
    """Inject only the per-launch worktree contract; never rewrite user settings."""
    return json.dumps(
        {
            "worktree": {
                "baseRef": "head",
                "symlinkDirectories": [".wishgraph"],
            }
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )

def _claude_worker_worktree_name(task_id: str) -> str:
    return f"wishgraph-{task_id}-{uuid.uuid4().hex[:8]}"

def _run_process(
    command: list[str], root: Path, *, timeout: int = 15
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )

def detect_claude_worker_capability(
    root: Path, claude_executable: str = "claude"
) -> ClaudeWorkerCapability:
    """Detect launch mechanics only; never grant Worker authority here."""
    executable = shutil.which(claude_executable)
    if not executable:
        return ClaudeWorkerCapability(
            tier=CLAUDE_MANUAL_COMMAND_ONLY,
            reason="claude_cli_missing",
        )
    try:
        help_result = _run_process([executable, "--help"], root, timeout=5)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ClaudeWorkerCapability(
            tier=CLAUDE_MANUAL_COMMAND_ONLY,
            claude_executable=executable,
            reason="background_flag_unsupported",
        )
    help_text = help_result.stdout + "\n" + help_result.stderr
    supports_background = help_result.returncode == 0 and "--bg" in help_text
    supports_fork = help_result.returncode == 0 and "--fork-session" in help_text
    supports_worktree = help_result.returncode == 0 and "--worktree" in help_text
    supports_settings = help_result.returncode == 0 and "--settings" in help_text
    supports_agents_json = False
    if supports_background and "agents" in help_text:
        try:
            agents_help = _run_process(
                [executable, "agents", "--help"], root, timeout=5
            )
        except (OSError, subprocess.TimeoutExpired):
            agents_help = None
        if agents_help is not None and agents_help.returncode == 0:
            supports_agents_json = "--json" in (
                agents_help.stdout + "\n" + agents_help.stderr
            )
    disabled = str(os.environ.get("CLAUDE_CODE_DISABLE_AGENT_VIEW") or "").lower()
    background_disabled = disabled not in {"", "0", "false", "no", "off"}
    agent_definition = _managed_claude_worker_agent(root)
    project_enabled = (root / ".wishgraph" / "config.json").is_file()
    if (
        supports_background
        and supports_agents_json
        and supports_worktree
        and supports_settings
        and not background_disabled
        and agent_definition is not None
        and project_enabled
    ):
        return ClaudeWorkerCapability(
            tier=CLAUDE_BACKGROUND_SESSION,
            claude_executable=executable,
            agent_definition=str(agent_definition),
            supports_background=True,
            supports_agents_json=True,
            supports_worktree=True,
            supports_settings=True,
            supports_fork=supports_fork,
            reason="native_background_session_available",
        )
    if supports_fork:
        if not supports_background:
            reason = "background_flag_unsupported"
        elif not supports_agents_json:
            reason = "agents_json_unsupported"
        elif background_disabled:
            reason = "agent_view_disabled"
        elif agent_definition is None:
            reason = "managed_worker_agent_missing"
        elif not supports_worktree or not supports_settings:
            reason = "worktree_runtime_unavailable"
        elif not project_enabled:
            reason = "wishgraph_not_enabled"
        else:
            reason = "background_launch_unavailable"
        return ClaudeWorkerCapability(
            tier=CLAUDE_FORKED_SUBAGENT,
            claude_executable=executable,
            agent_definition=str(agent_definition or ""),
            supports_background=supports_background,
            supports_agents_json=supports_agents_json,
            supports_worktree=supports_worktree,
            supports_settings=supports_settings,
            supports_fork=True,
            reason=reason,
        )
    return ClaudeWorkerCapability(
        tier=CLAUDE_MANUAL_COMMAND_ONLY,
        claude_executable=executable,
        agent_definition=str(agent_definition or ""),
        supports_background=supports_background,
        supports_agents_json=supports_agents_json,
        supports_fork=False,
        supports_worktree=supports_worktree,
        supports_settings=supports_settings,
        reason=(
            "background_flag_unsupported"
            if not supports_background
            else "agents_json_unsupported"
            if not supports_agents_json
            else "agent_view_disabled"
            if background_disabled
            else "managed_worker_agent_missing"
            if agent_definition is None
            else "worktree_runtime_unavailable"
            if not supports_worktree or not supports_settings
            else "wishgraph_not_enabled"
            if not project_enabled
            else "background_launch_unavailable"
        ),
    )

def _query_claude_agents(root: Path, executable: str) -> dict[str, Any]:
    command = [executable, "agents", "--json", "--all", "--cwd", str(root)]
    try:
        result = _run_process(command, root, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False,
            "error": "claude_agents_query_failed",
            "detail": type(exc).__name__,
            "command": command,
        }
    if result.returncode != 0:
        return {
            "ok": False,
            "error": "claude_agents_query_failed",
            "exit_code": result.returncode,
            "command": command,
        }
    try:
        sessions = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return {
            "ok": False,
            "error": "invalid_claude_agents_json",
            "command": command,
        }
    if not isinstance(sessions, list) or not all(
        isinstance(item, dict) for item in sessions
    ):
        return {
            "ok": False,
            "error": "invalid_claude_agents_payload",
            "command": command,
        }
    return {"ok": True, "sessions": sessions, "command": command}

def _find_claude_session(
    sessions: list[dict[str, Any]], session_id: str, short_id: str = ""
) -> Optional[dict[str, Any]]:
    candidates = {value for value in (session_id, short_id) if value}
    for session in sessions:
        values = {
            str(session.get("id") or ""),
            str(session.get("sessionId") or ""),
        }
        if candidates & values:
            return session
        if short_id and any(value.startswith(short_id) for value in values if value):
            return session
    return None

def launch_claude_worker(
    root: Path,
    config: dict[str, Any],
    task_id: str,
    discussion_session_id: str,
    *,
    claude_executable: str = "claude",
    execution_profile: Optional[dict[str, Any]] = None,
    authorize_launch: Callable[..., dict[str, Any]],
    manual_fallback: Callable[..., dict[str, Any]],
    resolve_profile: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """Launch one authorized Claude background Worker or return a strict fallback."""
    canonical = canonical_task_id(task_id)
    if not canonical:
        return {"ok": False, "error": "invalid_task_id"}
    authorized = authorize_launch(
        root,
        config,
        discussion_session_id,
        canonical,
        current_host="claude",
    )
    if not authorized.get("ok"):
        return authorized
    capability = detect_claude_worker_capability(root, claude_executable)
    if capability.tier != CLAUDE_BACKGROUND_SESSION:
        return manual_fallback(
            root,
            discussion_session_id,
            canonical,
            capability,
            capability.reason,
            execution_profile=execution_profile,
        )

    executable = capability.claude_executable
    profile_resolution = resolve_profile(execution_profile, config)
    resolved_profile = profile_resolution["resolved"]
    worktree_name = _claude_worker_worktree_name(canonical)
    launch_settings = _claude_worker_settings_json()
    command = [
        executable,
        "--bg",
        "--agent",
        "wishgraph-worker",
        *(
            ["--model", str(resolved_profile["model"])]
            if resolved_profile.get("model")
            else []
        ),
        *(
            ["--effort", str(resolved_profile["reasoning_effort"])]
            if resolved_profile.get("reasoning_effort")
            else []
        ),
        "--worktree",
        worktree_name,
        "--settings",
        launch_settings,
        f"执行 {canonical} 任务",
    ]
    starting = apply_session_runtime_patch(
        root,
        discussion_session_id,
        {
            "worker_runtime": {
                "agent_platform": "claude",
                "host_capability": capability.tier,
                "active_task_id": canonical,
                "launch_status": "starting",
                "launch_command": command,
                "launch_worktree_name": worktree_name,
                "launch_settings_source": "inline_ephemeral",
                "execution_profile": profile_resolution,
                "launch_branch": current_branch(root),
                "launch_worktree": str(root.resolve()),
                "claim_id": "",
                "binding_status": "awaiting_claim",
                "worker_availability": "starting",
                "sync_status": "launching",
            }
        },
    )
    if not starting.get("ok"):
        return manual_fallback(
            root,
            discussion_session_id,
            canonical,
            capability,
            "launch_runtime_persistence_failed",
        )
    try:
        launched = _run_process(command, root, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return manual_fallback(
            root,
            discussion_session_id,
            canonical,
            capability,
            f"claude_background_launch_failed:{type(exc).__name__}",
        )
    combined_output = launched.stdout + "\n" + launched.stderr
    id_match = CLAUDE_BACKGROUND_ID_RE.search(combined_output)
    short_id = id_match.group("session_id") if id_match else ""
    if "no agent named 'wishgraph-worker'" in combined_output.lower():
        return manual_fallback(
            root,
            discussion_session_id,
            canonical,
            capability,
            "managed_worker_agent_not_loaded",
            orphan_session_id=short_id,
        )
    if launched.returncode != 0:
        return manual_fallback(
            root,
            discussion_session_id,
            canonical,
            capability,
            f"claude_background_launch_exit_{launched.returncode}",
        )

    after = _query_claude_agents(root, executable)
    sessions = after.get("sessions", []) if after.get("ok") else []
    session = _find_claude_session(sessions, "", short_id)
    full_session_id = str((session or {}).get("sessionId") or "")
    short_id = short_id or str((session or {}).get("id") or "")
    claude_session_id = full_session_id
    if not claude_session_id:
        return manual_fallback(
            root,
            discussion_session_id,
            canonical,
            capability,
            "claude_stable_session_id_missing",
            orphan_session_id=short_id,
        )

    session_worktree = str(
        (session or {}).get("cwd")
        or (session or {}).get("worktree")
        or (session or {}).get("worktreePath")
        or ""
    )
    try:
        launch_worktree = str(Path(session_worktree).expanduser().resolve())
    except (OSError, RuntimeError):
        launch_worktree = ""
    if not launch_worktree or launch_worktree == str(root.resolve()):
        return manual_fallback(
            root,
            discussion_session_id,
            canonical,
            capability,
            "worktree_runtime_unavailable",
            orphan_session_id=claude_session_id,
        )

    worker_root = find_git_root(Path(launch_worktree))
    if worker_root is None or str(worker_root.resolve()) != launch_worktree:
        return manual_fallback(
            root,
            discussion_session_id,
            canonical,
            capability,
            "claude_worker_git_worktree_unavailable",
            orphan_session_id=claude_session_id,
        )
    launch_branch = current_branch(worker_root)
    if not launch_branch:
        return manual_fallback(
            root,
            discussion_session_id,
            canonical,
            capability,
            "claude_worker_branch_unavailable",
            orphan_session_id=claude_session_id,
        )

    if full_session_id:
        worker_handle = {
            "host": "claude",
            "container_kind": CLAUDE_BACKGROUND_CONTAINER,
            "thread_or_session_id": claude_session_id,
            "parent_discussion_id": discussion_session_id,
            "task_id": canonical,
            "claim_id": "",
            "branch": launch_branch,
            "worktree": launch_worktree,
            "inspectable": True,
            "controllable": True,
            "terminal_state": "starting",
            "last_observed_at": _utc_now(),
        }
        worker_runtime = apply_session_runtime_patch(
            root,
            full_session_id,
            {
                "session": {
                    "session_id": full_session_id,
                    "role": "neutral",
                    "host": "claude",
                    "phase": "planning",
                    "expected_transition": None,
                },
                "session_provenance": {
                    "initial_role": "neutral",
                    "host": "claude",
                    "discussion_authorized": False,
                    "created_at": _utc_now(),
                },
                "launch_context": {
                    "discussion_session_id": discussion_session_id,
                    "task_id": canonical,
                    "host_capability": capability.tier,
                    "agent_kind": "formal_worker",
                    "container_kind": CLAUDE_BACKGROUND_CONTAINER,
                    "thread_or_session_id": claude_session_id,
                    "branch": launch_branch,
                    "worktree": launch_worktree,
                    "inspectable": True,
                    "controllable": True,
                    "independent_context": True,
                    "isolated_worktree": True,
                    "execution_profile": profile_resolution,
                },
                "worker_runtime": {"worker_handle": worker_handle},
            },
        )
        if not worker_runtime.get("ok"):
            return manual_fallback(
                root,
                discussion_session_id,
                canonical,
                capability,
                "worker_session_runtime_persistence_failed",
                orphan_session_id=claude_session_id,
            )

    persisted = apply_session_runtime_patch(
        root,
        discussion_session_id,
        {
            "session": {
                "phase": "waiting_for_worker",
                "expected_transition": {
                    "kind": "wait_for_worker",
                    "task_id": canonical,
                },
            },
            "worker_runtime": {
                "agent_platform": "claude",
                "host_capability": capability.tier,
                "active_task_id": canonical,
                "claude_session_id": claude_session_id,
                "claude_full_session_id": full_session_id,
                "claude_short_id": short_id,
                "host_window_or_thread_id": claude_session_id,
                "launch_status": "launched",
                "launch_command": command,
                "launch_branch": launch_branch,
                "launch_worktree": launch_worktree,
                "launch_worktree_name": worktree_name,
                "launch_settings_source": "inline_ephemeral",
                "execution_profile": profile_resolution,
                "claim_id": "",
                "binding_status": "awaiting_claim",
                "worker_availability": "starting",
                "sync_status": "waiting_for_claim",
                "last_observed_at": _utc_now(),
                "worker_handle": {
                    "host": "claude",
                    "container_kind": CLAUDE_BACKGROUND_CONTAINER,
                    "thread_or_session_id": claude_session_id,
                    "parent_discussion_id": discussion_session_id,
                    "task_id": canonical,
                    "claim_id": "",
                    "branch": launch_branch,
                    "worktree": launch_worktree,
                    "inspectable": True,
                    "controllable": True,
                    "terminal_state": "starting",
                    "last_observed_at": _utc_now(),
                },
            },
        },
    )
    if not persisted.get("ok"):
        return manual_fallback(
            root,
            discussion_session_id,
            canonical,
            capability,
            "discussion_runtime_persistence_failed",
            orphan_session_id=claude_session_id,
        )
    execution_run = latest_execution_run(
        root, canonical, attempt=int(authorized["task"].get("attempt") or 1)
    )
    if isinstance(execution_run, dict):
        run_bound = update_execution_run(
            root,
            task_id=canonical,
            attempt=int(authorized["task"].get("attempt") or 1),
            patch={
                "phase": "dispatching",
                "worker": {
                    "host": "claude",
                    "container_kind": CLAUDE_BACKGROUND_CONTAINER,
                    "thread_or_session_id": claude_session_id,
                    "branch": launch_branch,
                    "worktree": launch_worktree,
                    "registered_at": _utc_now(),
                },
                "last_error": {},
            },
        )
        if not run_bound.get("ok"):
            return manual_fallback(
                root,
                discussion_session_id,
                canonical,
                capability,
                "claude_execution_run_binding_failed",
                orphan_session_id=claude_session_id,
            )
    return {
        "ok": True,
        "launched": True,
        "fallback": False,
        "capability": capability.as_dict(),
        "task_id": canonical,
        "claude_session_id": claude_session_id,
        "claude_full_session_id": full_session_id,
        "claude_short_id": short_id,
        "actual_command": shlex.join(command),
        "claim_status": "worker_must_acquire_on_start",
        "execution_profile": profile_resolution,
        "stop_after_action": True,
    }

def _matching_claude_claims(
    root: Path, task_id: str, session_ids: set[str]
) -> list[dict[str, Any]]:
    return [
        claim
        for claim in inspect_claims(root, task_id)
        if claim.get("agent_platform") == "claude"
        and (
            str(claim.get("worker_id") or "") in session_ids
            or str(claim.get("host_thread_ref") or "") in session_ids
        )
    ]

def refresh_claude_worker(
    root: Path,
    config: dict[str, Any],
    discussion_session_id: str,
    *,
    claude_executable: str = "claude",
    include_logs: bool = False,
    manual_fallback: Callable[..., dict[str, Any]],
    resolve_task_record: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """Refresh from structured Claude state plus durable Claim/report evidence."""
    runtime = read_session_runtime(root, discussion_session_id)
    if runtime is None:
        return {"ok": False, "error": "discussion_session_runtime_not_found"}
    session_runtime = (
        runtime.get("session") if isinstance(runtime.get("session"), dict) else {}
    )
    if session_runtime.get("role") != "discussion":
        return {"ok": False, "error": "discussion_session_required"}
    worker_runtime = (
        runtime.get("worker_runtime")
        if isinstance(runtime.get("worker_runtime"), dict)
        else {}
    )
    current_task_runtime = (
        runtime.get("task") if isinstance(runtime.get("task"), dict) else {}
    )
    task_id = canonical_task_id(worker_runtime.get("active_task_id"))
    if not task_id:
        return {"ok": False, "error": "active_claude_worker_not_found"}

    capability = detect_claude_worker_capability(root, claude_executable)
    executable = capability.claude_executable or shutil.which(claude_executable) or ""
    if not executable:
        return manual_fallback(
            root,
            discussion_session_id,
            task_id,
            capability,
            "claude_cli_not_found_during_refresh",
        )
    observed = _query_claude_agents(root, executable)
    full_id = str(worker_runtime.get("claude_full_session_id") or "")
    saved_id = str(worker_runtime.get("claude_session_id") or "")
    short_id = str(worker_runtime.get("claude_short_id") or "")
    session = (
        _find_claude_session(observed.get("sessions", []), full_id or saved_id, short_id)
        if observed.get("ok")
        else None
    )
    if session is not None:
        full_id = str(session.get("sessionId") or full_id)
        short_id = str(session.get("id") or short_id)
        saved_id = full_id or short_id or saved_id
    structured_state = str((session or {}).get("state") or "missing").casefold()
    structured_status = str((session or {}).get("status") or "")
    waiting_for = str((session or {}).get("waitingFor") or "")

    session_ids = {value for value in (full_id, saved_id, short_id) if value}
    claims = _matching_claude_claims(root, task_id, session_ids)
    claims.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    claim = claims[0] if claims else None
    resolved = resolve_task_record(root, config, task_id)
    task = resolved.get("task", {}) if resolved.get("ok") else {}
    execution_run = latest_execution_run(
        root, task_id, attempt=int(task.get("attempt") or 1)
    )
    result = (
        execution_run.get("result")
        if isinstance(execution_run, dict)
        and isinstance(execution_run.get("result"), dict)
        else {}
    )
    task_status = str(result.get("terminal_state") or task.get("status") or "")
    report_path_value = str(result.get("report") or task.get("run_report") or "")
    result_commit = str(result.get("commit") or "")
    report_exists = bool(
        report_path_value
        and (
            (result_commit and read_ref_version(root, result_commit, report_path_value))
            or (root / report_path_value).is_file()
        )
    )
    claim_released = bool(claim and claim.get("lease_status") == "released")
    durable_terminal = (
        task_status in {"completed", "blocked", "incomplete"}
        and report_exists
        and claim_released
        and isinstance(execution_run, dict)
        and execution_run.get("phase")
        in {"succeeded", "failed", "decision_required", "integrating", "integrated"}
    )

    if durable_terminal:
        phase = "integration_pending"
        expected_transition: Optional[dict[str, Any]] = {
            "kind": "auto_integrate",
            "task_id": task_id,
        }
        sync_status = "integration_pending"
        worker_availability = "terminal"
        recovery_reason = ""
    elif structured_state in CLAUDE_RUNNING_STATES:
        phase = "waiting_for_worker"
        expected_transition = {"kind": "wait_for_worker", "task_id": task_id}
        sync_status = "waiting_for_worker" if claim else "waiting_for_claim"
        worker_availability = "busy" if claim else "starting"
        recovery_reason = ""
    elif structured_state in CLAUDE_BLOCKED_STATES:
        phase = "waiting_for_worker"
        expected_transition = {"kind": "wait_for_worker", "task_id": task_id}
        sync_status = "manual_intervention_required"
        worker_availability = "blocked"
        recovery_reason = "claude_session_blocked"
    elif structured_state in CLAUDE_COMPLETED_STATES:
        phase = "waiting_for_worker"
        expected_transition = {"kind": "wait_for_worker", "task_id": task_id}
        sync_status = "manual_intervention_required"
        worker_availability = "terminal"
        recovery_reason = "terminal_evidence_incomplete"
    elif structured_state in CLAUDE_FAILED_STATES:
        phase = "waiting_for_worker"
        expected_transition = {"kind": "wait_for_worker", "task_id": task_id}
        sync_status = "manual_intervention_required"
        worker_availability = "failed"
        recovery_reason = "claude_session_failed"
    else:
        phase = "waiting_for_worker"
        expected_transition = {"kind": "wait_for_worker", "task_id": task_id}
        sync_status = "manual_intervention_required"
        worker_availability = "missing" if session is None else "unknown"
        recovery_reason = (
            "claude_agents_query_failed"
            if not observed.get("ok")
            else "claude_session_missing_or_unknown"
        )

    binding_status = str(worker_runtime.get("binding_status") or "unbound")
    if claim is not None:
        binding_status = (
            "active"
            if claim.get("effective_lease_status") == "active"
            else str(claim.get("lease_status") or binding_status)
        )
    patch: dict[str, Any] = {
        "session": {
            "phase": phase,
            "expected_transition": expected_transition,
        },
        "worker_runtime": {
            "agent_platform": "claude",
            "host_capability": capability.tier,
            "active_task_id": task_id,
            "claude_session_id": saved_id,
            "claude_full_session_id": full_id,
            "claude_short_id": short_id,
            "claude_state": structured_state,
            "claude_status": structured_status,
            "claude_waiting_for": waiting_for,
            "claim_id": str((claim or {}).get("claim_id") or ""),
            "branch": str((claim or {}).get("branch") or ""),
            "worktree": str((claim or {}).get("worktree") or ""),
            "host_window_or_thread_id": saved_id,
            "binding_status": binding_status,
            "worker_availability": worker_availability,
            "sync_status": sync_status,
            "recovery_reason": recovery_reason,
            "last_observed_at": _utc_now(),
            "worker_handle": {
                "host": "claude",
                "container_kind": CLAUDE_BACKGROUND_CONTAINER,
                "thread_or_session_id": saved_id,
                "parent_discussion_id": discussion_session_id,
                "task_id": task_id,
                "claim_id": str((claim or {}).get("claim_id") or ""),
                "branch": str((claim or {}).get("branch") or ""),
                "worktree": str((claim or {}).get("worktree") or ""),
                "inspectable": True,
                "controllable": True,
                "terminal_state": structured_state,
                "last_observed_at": _utc_now(),
            },
        },
    }
    if task_status:
        patch["task"] = {
            "task_id": task_id,
            "lifecycle": task_status,
            "worker_authorized": bool(
                task_status != "draft" or current_task_runtime.get("worker_authorized")
            ),
            "run_report": report_path_value,
        }
    persisted = apply_session_runtime_patch(root, discussion_session_id, patch)
    if not persisted.get("ok"):
        return {
            "ok": False,
            "error": "claude_worker_refresh_persistence_failed",
            "detail": persisted,
        }

    logs = ""
    if include_logs and short_id:
        try:
            log_result = _run_process([executable, "logs", short_id], root, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            log_result = None
        if log_result is not None:
            logs = log_result.stdout
    return {
        "ok": True,
        "task_id": task_id,
        "capability": capability.as_dict(),
        "structured_claude_state": structured_state,
        "sync_status": sync_status,
        "durable_terminal_evidence": durable_terminal,
        "task_lifecycle": task_status,
        "report_exists": report_exists,
        "claim": claim,
        "management_commands": {
            "list": shlex.join(
                [executable, "agents", "--json", "--all", "--cwd", str(root)]
            ),
            "logs": shlex.join([executable, "logs", short_id]) if short_id else "",
            "attach": (
                shlex.join([executable, "attach", short_id]) if short_id else ""
            ),
        },
        "logs": logs,
    }
