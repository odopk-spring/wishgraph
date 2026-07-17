"""Host-hook, CLI, and user-facing output boundary for WishGraph."""

from __future__ import annotations

import argparse
import difflib
import fnmatch
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from git_state import (
    HOST_OBSERVATION_EVENTS,
    LEGACY_PROJECT_STATUS_PATH,
    RUNTIME_ID_RE,
    apply_session_runtime_patch,
    acquire_claim,
    acquire_integration_lease,
    configured_revision_glob,
    configured_task_globs,
    current_branch,
    consume_worker_notifications,
    create_integration_transition_grant,
    enqueue_worker_notification,
    find_git_root,
    load_config,
    inspect_claims,
    inspect_integration_grant,
    inspect_integration_lease,
    read_version,
    read_session_runtime,
    read_host_observations,
    record_host_observation,
    rebind_worker_claim,
    resolve_project_status_path,
    run_git,
    standard_project_status_conflict,
    update_claim,
    update_integration_lease,
    write_session_runtime,
)
from policy import (
    CheckResult,
    check_sync,
    execution_preflight as evaluate_execution_preflight,
    integration_state,
    report_state,
    reduce_orchestration,
)
from workflow_state import (
    EXPECTED_TRANSITIONS,
    FLOW_PHASES,
    SESSION_ROLES,
    FlowPlan,
    HostCapability,
    UserEvent,
    canonical_task_id,
    canonical_revision_id,
    competitive_candidate_ids,
    dynamic_state_block,
    is_contextual_approval,
    markdown_section,
    parse_task_command,
    parse_task_state,
    parse_revision_state,
    flow_plan_to_dict,
    orchestration_state_from_dict,
    parse_user_prompt,
    revision_id_parts,
    task_id_parts,
)


@dataclass(frozen=True)
class HostAction:
    action: str
    state_patch: dict[str, Any] = field(default_factory=dict)
    user_message: str = ""
    stop_after_action: bool = False
    creates_inspectable_thread: bool = False
    target_worker_id: str = ""
    work_payload: dict[str, Any] = field(default_factory=dict)


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
CODEX_AGENT_THREAD = "codex_agent_thread"
CLAUDE_BACKGROUND_CONTAINER = "claude_background_session"
MANUAL_WORKER_WINDOW = "manual_worker_window"
HELPER_SUBAGENT = "helper_subagent"
HIDDEN_INTERNAL_AGENT = "hidden_internal_agent"
FORMAL_WORKER_CONTAINERS = {
    CODEX_AGENT_THREAD,
    CLAUDE_BACKGROUND_CONTAINER,
    MANUAL_WORKER_WINDOW,
}
NON_WORKER_CONTAINERS = {HELPER_SUBAGENT, HIDDEN_INTERNAL_AGENT}
CODEX_RUNNING_STATES = {"starting", "running", "working", "waiting"}
CODEX_TERMINAL_STATES = {"completed", "failed", "stopped", "cancelled"}
HOST_RECEIPT_RECENT_SECONDS = 120
HOST_ADAPTER_EVENTS = {
    "codex": {"SessionStart", "UserPromptSubmit", "PreToolUse", "Stop"},
    "claude": {
        "SessionStart",
        "UserPromptSubmit",
        "PreToolUse",
        "Stop",
        "TaskCompleted",
    },
}
HOST_AGENT_PATHS = {
    "codex": Path(".codex/agents/wishgraph-worker.toml"),
    "claude": Path(".claude/agents/wishgraph-worker.md"),
}
HOST_AGENT_MARKERS = {
    "codex": "# wishgraph-managed: wishgraph-worker",
    "claude": "<!-- wishgraph-managed: wishgraph-worker -->",
}


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


def host_capability_for(host: str) -> HostCapability:
    """Describe the portable host boundary without granting Task authority."""
    common = {
        "can_gate_writes": True,
        "can_gate_builds": True,
        "can_gate_reads": False,
        "can_deliver_result_to_discussion": True,
    }
    if host == "codex":
        return HostCapability(
            host=host,
            can_spawn_execution_thread=True,
            can_inspect_execution_thread=True,
            can_bind_thread_id=True,
            can_stop_or_steer_thread=True,
            can_isolate_worktree=False,
            can_observe_terminal_result=True,
            **common,
        )
    if host == "claude":
        return HostCapability(
            host=host,
            can_spawn_execution_thread=True,
            can_inspect_execution_thread=True,
            can_bind_thread_id=True,
            can_stop_or_steer_thread=True,
            can_isolate_worktree=True,
            can_observe_terminal_result=True,
            **common,
        )
    return HostCapability(host=host)


def _value_contains_wishgraph_handler(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_value_contains_wishgraph_handler(item) for item in value.values())
    if isinstance(value, list):
        return any(_value_contains_wishgraph_handler(item) for item in value)
    if not isinstance(value, str):
        return False
    normalized = value.replace("\\", "/")
    return (
        ".wishgraph/hooks/memory_sync.py" in normalized
        or "skills/wishgraph/scripts/global_host_hook.py" in normalized
    )


def current_host_adapter_state(root: Path, host: str) -> dict[str, Any]:
    if host not in {"codex", "claude"}:
        return {"state": "missing", "error": "current_host_unknown"}
    config_home = (
        Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        if host == "codex"
        else Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    ).expanduser()
    project_config = root / (
        ".codex/hooks.json" if host == "codex" else ".claude/settings.json"
    )
    global_config = config_home / ("hooks.json" if host == "codex" else "settings.json")
    config_candidates = [project_config, global_config]
    selected_config: Optional[Path] = None
    selected_missing: list[str] = []
    for candidate in config_candidates:
        try:
            value = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        hooks = value.get("hooks") if isinstance(value, dict) else None
        if not isinstance(hooks, dict):
            continue
        missing = [
            event
            for event in sorted(HOST_ADAPTER_EVENTS[host])
            if not _value_contains_wishgraph_handler(hooks.get(event, []))
        ]
        if selected_config is None or len(missing) < len(selected_missing):
            selected_config = candidate
            selected_missing = missing
        if not missing:
            break

    project_agent = root / HOST_AGENT_PATHS[host]
    global_agent = config_home / "agents" / HOST_AGENT_PATHS[host].name
    agent_candidates = [project_agent, global_agent]
    agent_path: Optional[Path] = None
    for candidate in agent_candidates:
        try:
            agent_text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if HOST_AGENT_MARKERS[host] in agent_text:
            agent_path = candidate
            break
    missing_events = list(selected_missing)
    if selected_config is None:
        missing_events.extend(sorted(HOST_ADAPTER_EVENTS[host]))
    if agent_path is None:
        missing_events.append("wishgraph-worker")
    missing_events = sorted(set(missing_events))
    state = "current" if not missing_events else (
        "missing" if selected_config is None else "outdated"
    )
    mtimes: list[float] = []
    for path in (selected_config, agent_path):
        if path is None:
            continue
        try:
            mtimes.append(path.stat().st_mtime)
        except OSError:
            pass
    return {
        "state": state,
        "path": str(selected_config or project_config),
        "scope": "global" if selected_config == global_config else "project",
        "agent_path": str(agent_path or project_agent),
        "missing_or_outdated": missing_events,
        "updated_at_epoch": max(mtimes) if mtimes else 0.0,
    }


def current_host_execution_guard(
    root: Path, config: dict[str, Any], host: str
) -> dict[str, Any]:
    required_hosts = config.get("required_hosts", [])
    if host not in {"codex", "claude"}:
        return {
            "ok": False,
            "error": "current_host_unknown",
            "message": "无法确认当前宿主，不能开始正式 WishGraph Task。",
        }
    if host not in required_hosts:
        return {
            "ok": False,
            "error": "current_host_not_required",
            "message": (
                "当前宿主不在 required_hosts 中。请先显式为该项目启用当前宿主，"
                "安装对应 Adapter，并重开当前 Agent 会话。"
            ),
        }
    adapter = current_host_adapter_state(root, host)
    if adapter["state"] != "current":
        return {
            "ok": False,
            "error": "current_host_adapter_not_current",
            "adapter": adapter,
            "message": (
                "当前宿主的 WishGraph Adapter 未安装或不是当前版本。"
                "请先修复该宿主 Adapter，并重开当前 Agent 会话。"
            ),
        }
    observations = read_host_observations(root, host)
    valid: list[tuple[datetime, dict[str, Any]]] = []
    for observation in observations:
        observed_at = observation.get("observed_at")
        if not isinstance(observed_at, str):
            continue
        try:
            parsed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        if observation.get("runtime_version") == config.get("runtime_version"):
            valid.append((parsed, observation))
    latest = max(valid, key=lambda item: item[0], default=None)
    if latest is not None:
        age = max(0.0, (datetime.now(timezone.utc) - latest[0]).total_seconds())
        adapter_updated_at = float(adapter.get("updated_at_epoch") or 0.0)
        observed_epoch = latest[0].timestamp()
        if age <= HOST_RECEIPT_RECENT_SECONDS and observed_epoch + 1 >= adapter_updated_at:
            return {
                "ok": True,
                "host": host,
                "adapter": adapter,
                "receipt": latest[1],
                "age_seconds": int(age),
            }
    return {
        "ok": False,
        "error": "current_host_receipt_not_recent",
        "adapter": adapter,
        "message": (
            "当前宿主的 WishGraph Hook 尚未在本会话中确认加载。"
            "请重开当前 Agent 会话后重试。"
        ),
    }


def map_flow_plan_to_host(
    plan: FlowPlan, capability: HostCapability
) -> HostAction:
    """Map one authorized semantic plan to a host action without changing authority."""
    if plan.next_action == "launch_worker":
        if not capability.supports_formal_worker_thread:
            task_id = plan.task_id
            return HostAction(
                action="show_manual_worker_command",
                state_patch={
                    **plan.state_patch,
                    "session": {
                        "phase": "waiting_for_user_launch",
                        "expected_transition": {
                            "kind": "launch_worker_manually",
                            "task_id": task_id,
                        },
                    },
                },
                user_message=f"执行 {task_id} 任务",
                stop_after_action=True,
            )
        if capability.host == "claude":
            return HostAction(
                action="launch_claude_background_worker",
                state_patch=plan.state_patch,
                stop_after_action=True,
                creates_inspectable_thread=True,
                work_payload={
                    "task_id": plan.task_id,
                    "capability_detection_required": True,
                },
            )
        if capability.host == "codex":
            return HostAction(
                action="launch_codex_agent_worker",
                state_patch=plan.state_patch,
                stop_after_action=True,
                creates_inspectable_thread=True,
                work_payload={
                    "task_id": plan.task_id,
                    "agent_name": "wishgraph-worker",
                    "requires_real_thread_id": True,
                },
            )
        return HostAction(
            action="spawn_execution_thread",
            state_patch=plan.state_patch,
            stop_after_action=True,
            creates_inspectable_thread=True,
            work_payload={"task_id": plan.task_id},
        )
    if plan.next_action == "enter_discussion_local_integration":
        return HostAction(
            action="enter_discussion_local_integration",
            state_patch=plan.state_patch,
            stop_after_action=False,
            creates_inspectable_thread=False,
        )
    if plan.next_action in {"route_to_active_worker", "route_to_previous_worker"}:
        if capability.can_route_worker_thread and plan.target_worker_id:
            return HostAction(
                action="send_to_existing_worker",
                state_patch=plan.state_patch,
                stop_after_action=True,
                target_worker_id=plan.target_worker_id,
                work_payload=plan.work_payload,
            )
        revision_id = plan.revision_id
        task_id = plan.task_id
        message = (
            f"在任务 {task_id} 的执行窗口执行修订 {revision_id}"
            if revision_id
            else f"在任务 {task_id} 的执行窗口处理当前反馈"
        )
        return HostAction(
            action="show_manual_worker_command",
            state_patch=plan.state_patch,
            user_message=message,
            stop_after_action=True,
            work_payload=plan.work_payload,
        )
    if plan.next_action == "create_lightweight_revision":
        if capability.supports_formal_worker_thread:
            return HostAction(
                action=(
                    "launch_codex_revision_worker"
                    if capability.host == "codex"
                    else "launch_claude_revision_worker"
                ),
                state_patch=plan.state_patch,
                stop_after_action=True,
                creates_inspectable_thread=True,
                work_payload=plan.work_payload,
            )
        return HostAction(
            action="show_manual_worker_command",
            state_patch=plan.state_patch,
            user_message=(
                f"在任务 {plan.task_id} 的执行窗口执行修订 {plan.revision_id}"
            ),
            stop_after_action=True,
            work_payload=plan.work_payload,
        )
    if plan.next_action == "fallback_manual_worker_command":
        return HostAction(
            action="show_manual_worker_command",
            state_patch=plan.state_patch,
            user_message=plan.user_message,
            stop_after_action=True,
            work_payload=plan.work_payload,
        )
    if plan.next_action == "rebind_worker":
        if capability.can_reuse_worker_thread and plan.target_worker_id:
            return HostAction(
                action="rebind_existing_worker",
                state_patch=plan.state_patch,
                target_worker_id=plan.target_worker_id,
                work_payload=plan.work_payload,
            )
        return HostAction(
            action="show_manual_worker_command",
            state_patch=plan.state_patch,
            user_message=(
                f"在任务 {plan.task_id} 的执行窗口执行修订 {plan.revision_id}"
                if plan.revision_id
                else f"执行 {plan.task_id} 任务"
            ),
            stop_after_action=True,
            work_payload=plan.work_payload,
        )
    return HostAction(
        action=plan.next_action,
        state_patch=plan.state_patch,
        user_message=plan.user_message,
        stop_after_action=plan.stop_after_action,
        creates_inspectable_thread=False,
        target_worker_id=plan.target_worker_id,
        work_payload=plan.work_payload,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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


def _manual_worker_fallback(
    root: Path,
    discussion_session_id: str,
    task_id: str,
    capability: ClaudeWorkerCapability,
    reason: str,
    *,
    orphan_session_id: str = "",
) -> dict[str, Any]:
    message = f"执行 {task_id} 任务"
    orphaned = bool(orphan_session_id)
    recovery_command = (
        shlex.join(
            [
                capability.claude_executable or "claude",
                "agents",
                "--cwd",
                str(root),
            ]
        )
        if orphaned
        else ""
    )
    persisted = apply_session_runtime_patch(
        root,
        discussion_session_id,
        {
            "session": {
                "phase": "waiting_for_user_launch",
                "expected_transition": {
                    "kind": "launch_worker_manually",
                    "task_id": task_id,
                },
            },
            "worker_runtime": {
                "agent_platform": "claude",
                "host_capability": capability.tier,
                "active_task_id": task_id,
                "launch_status": "manual_required",
                "launch_error": reason,
                "orphaned_background_session_id": orphan_session_id,
                "recovery_command": recovery_command,
                "claim_id": "",
                "binding_status": "unbound",
                "worker_availability": (
                    "manual_intervention_required" if orphaned else "manual_required"
                ),
                "sync_status": (
                    "manual_intervention_required"
                    if orphaned
                    else "waiting_for_user_launch"
                ),
                "last_observed_at": _utc_now(),
                "worker_handle": {
                    "host": "claude",
                    "container_kind": (
                        CLAUDE_BACKGROUND_CONTAINER if orphaned else ""
                    ),
                    "thread_or_session_id": orphan_session_id,
                    "parent_discussion_id": discussion_session_id,
                    "task_id": task_id,
                    "claim_id": "",
                    "branch": "",
                    "worktree": "",
                    "inspectable": orphaned,
                    "controllable": orphaned,
                    "terminal_state": (
                        "manual_intervention_required" if orphaned else "not_created"
                    ),
                    "last_observed_at": _utc_now(),
                },
            },
        },
    )
    return {
        "ok": bool(persisted.get("ok")),
        "launched": False,
        "fallback": True,
        "capability": capability.as_dict(),
        "user_message": message,
        "stop_after_action": True,
        "runtime_persisted": bool(persisted.get("ok")),
        "orphaned_background_session_id": orphan_session_id,
        "recovery_command": recovery_command,
    }


def _authorized_execution_thread_launch(
    root: Path,
    config: dict[str, Any],
    discussion_session_id: str,
    task_id: str,
    *,
    current_host: str,
) -> dict[str, Any]:
    runtime = read_session_runtime(root, discussion_session_id)
    if runtime is None:
        return {"ok": False, "error": "discussion_session_runtime_not_found"}
    session = runtime.get("session") if isinstance(runtime.get("session"), dict) else {}
    task_runtime = runtime.get("task") if isinstance(runtime.get("task"), dict) else {}
    if session.get("role") != "discussion":
        return {"ok": False, "error": "discussion_session_required"}
    if session.get("phase") not in {"routing_worker", "waiting_for_user_launch"}:
        return {"ok": False, "error": "worker_routing_phase_required"}
    if task_runtime.get("task_id") != task_id:
        return {"ok": False, "error": "authorized_task_mismatch"}
    if (
        task_runtime.get("lifecycle") != "approved"
        or task_runtime.get("worker_authorized") is not True
    ):
        return {"ok": False, "error": "worker_launch_not_authorized"}
    host_guard = current_host_execution_guard(root, config, current_host)
    if not host_guard.get("ok"):
        return host_guard
    preflight = execution_preflight(root, config, task_id, "execute")
    if not preflight.get("ok"):
        return {
            "ok": False,
            "error": "execution_preflight_failed",
            "detail": preflight,
        }
    task_path = str(preflight["task"].get("task_path") or "")
    current_task = read_version(root, task_path, "worktree") if task_path else None
    committed = run_git(root, "show", f"HEAD:{task_path}", check=False)
    committed_task = (
        committed.stdout.decode("utf-8", errors="replace")
        if committed.returncode == 0
        else None
    )
    if not current_task or committed_task != current_task:
        return {
            "ok": False,
            "error": "authorized_task_must_match_current_head_for_execution_thread",
            "task_path": task_path,
        }
    return {"ok": True, "runtime": runtime, "task": preflight["task"]}


def _authorize_codex_execution_thread_launch(
    root: Path, config: dict[str, Any], discussion_session_id: str, task_id: str
) -> dict[str, Any]:
    return _authorized_execution_thread_launch(
        root,
        config,
        discussion_session_id,
        task_id,
        current_host="codex",
    )


def _codex_worker_provider():
    # Keep ordinary Hook startup independent of the larger native Codex provider.
    import codex_worker_provider

    return codex_worker_provider


def _manual_codex_worker_fallback(
    root: Path,
    discussion_session_id: str,
    task_id: str,
    reason: str,
) -> dict[str, Any]:
    return _codex_worker_provider()._manual_codex_worker_fallback(
        root, discussion_session_id, task_id, reason
    )


def prepare_codex_worker(
    root: Path,
    config: dict[str, Any],
    task_id: str,
    discussion_session_id: str,
) -> dict[str, Any]:
    return _codex_worker_provider().prepare_codex_worker(
        root,
        config,
        task_id,
        discussion_session_id,
        authorize_launch=_authorize_codex_execution_thread_launch,
    )


def register_codex_worker(
    root: Path,
    config: dict[str, Any],
    task_id: str,
    discussion_session_id: str,
    thread_id: str,
    *,
    branch: str = "",
    worktree: str = "",
    inspectable: bool = False,
    controllable: bool = False,
    independent_context: bool = False,
    isolated_worktree: bool = False,
) -> dict[str, Any]:
    return _codex_worker_provider().register_codex_worker(
        root,
        config,
        task_id,
        discussion_session_id,
        thread_id,
        branch=branch,
        worktree=worktree,
        inspectable=inspectable,
        controllable=controllable,
        independent_context=independent_context,
        isolated_worktree=isolated_worktree,
        authorize_launch=_authorize_codex_execution_thread_launch,
    )


def observe_codex_worker(
    root: Path,
    config: dict[str, Any],
    discussion_session_id: str,
    thread_id: str,
    observed_state: str,
) -> dict[str, Any]:
    return _codex_worker_provider().observe_codex_worker(
        root,
        config,
        discussion_session_id,
        thread_id,
        observed_state,
        resolve_task_record=resolve_task,
    )


def launch_claude_worker(
    root: Path,
    config: dict[str, Any],
    task_id: str,
    discussion_session_id: str,
    *,
    claude_executable: str = "claude",
) -> dict[str, Any]:
    """Launch one authorized Claude background Worker or return one-line fallback."""
    canonical = canonical_task_id(task_id)
    if not canonical:
        return {"ok": False, "error": "invalid_task_id"}
    authorized = _authorized_execution_thread_launch(
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
        return _manual_worker_fallback(
            root,
            discussion_session_id,
            canonical,
            capability,
            capability.reason,
        )

    executable = capability.claude_executable
    worktree_name = _claude_worker_worktree_name(canonical)
    launch_settings = _claude_worker_settings_json()
    command = [
        executable,
        "--bg",
        "--agent",
        "wishgraph-worker",
        "--worktree",
        worktree_name,
        "--settings",
        launch_settings,
        f"执行 {canonical} 任务",
    ]
    before = _query_claude_agents(root, executable)
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
        return _manual_worker_fallback(
            root,
            discussion_session_id,
            canonical,
            capability,
            "launch_runtime_persistence_failed",
        )
    try:
        launched = _run_process(command, root, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _manual_worker_fallback(
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
        return _manual_worker_fallback(
            root,
            discussion_session_id,
            canonical,
            capability,
            "managed_worker_agent_not_loaded",
            orphan_session_id=short_id,
        )
    if launched.returncode != 0:
        return _manual_worker_fallback(
            root,
            discussion_session_id,
            canonical,
            capability,
            f"claude_background_launch_exit_{launched.returncode}",
        )

    after = _query_claude_agents(root, executable)
    sessions = after.get("sessions", []) if after.get("ok") else []
    session = _find_claude_session(sessions, "", short_id)
    if session is None and before.get("ok") and after.get("ok"):
        previous_ids = {
            str(item.get("sessionId") or item.get("id") or "")
            for item in before.get("sessions", [])
        }
        new_sessions = [
            item
            for item in sessions
            if str(item.get("sessionId") or item.get("id") or "") not in previous_ids
        ]
        if len(new_sessions) == 1:
            session = new_sessions[0]
    full_session_id = str((session or {}).get("sessionId") or "")
    short_id = short_id or str((session or {}).get("id") or "")
    claude_session_id = full_session_id
    if not claude_session_id:
        return _manual_worker_fallback(
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
        return _manual_worker_fallback(
            root,
            discussion_session_id,
            canonical,
            capability,
            "worktree_runtime_unavailable",
            orphan_session_id=claude_session_id,
        )

    worker_root = find_git_root(Path(launch_worktree))
    if worker_root is None or str(worker_root.resolve()) != launch_worktree:
        return _manual_worker_fallback(
            root,
            discussion_session_id,
            canonical,
            capability,
            "claude_worker_git_worktree_unavailable",
            orphan_session_id=claude_session_id,
        )
    launch_branch = current_branch(worker_root)
    if not launch_branch:
        return _manual_worker_fallback(
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
                },
                "worker_runtime": {"worker_handle": worker_handle},
            },
        )
        if not worker_runtime.get("ok"):
            return _manual_worker_fallback(
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
        return _manual_worker_fallback(
            root,
            discussion_session_id,
            canonical,
            capability,
            "discussion_runtime_persistence_failed",
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
        return _manual_worker_fallback(
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
    resolved = resolve_task(root, config, task_id)
    task = resolved.get("task", {}) if resolved.get("ok") else {}
    task_status = str(task.get("status") or "")
    report_path_value = str(task.get("run_report") or "")
    report_path = root / report_path_value if report_path_value else None
    report_exists = bool(report_path and report_path.is_file())
    claim_released = bool(claim and claim.get("lease_status") == "released")
    durable_terminal = (
        task_status in {"completed", "blocked", "incomplete"}
        and report_exists
        and claim_released
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


def project_session_context(root: Path, config: dict[str, Any]) -> Optional[str]:
    if config.get("session_start_context_mode", "safety_only") != "discussion_summary":
        return None
    paths = config["paths"]
    status_path = resolve_project_status_path(root, config)
    overview = read_version(root, status_path, "worktree")
    discussion = read_version(root, paths["discussion_prompt"], "worktree")
    current_integration = markdown_section(
        overview, "Current Integration"
    ) or markdown_section(overview, "当前集成")
    current_status = markdown_section(
        overview, "Current Project Status"
    ) or markdown_section(overview, "当前项目状态")
    results = "\n\n".join(
        part for part in (current_integration, current_status) if part
    )
    state = dynamic_state_block(discussion)
    sections: list[str] = []
    integration = integration_state(root, config, view="active").as_dict()
    if status_path == LEGACY_PROJECT_STATUS_PATH:
        sections.append(
            "Migration reminder: reports/DEV_REPORT.md uses the retired status-file name. "
            "Read it as the current snapshot, then use git mv to rename it to "
            "reports/PROJECT_STATUS.md and update project references. Do not maintain both files."
        )
    if standard_project_status_conflict(root, "worktree"):
        sections.append(
            "Status-source conflict: both reports/PROJECT_STATUS.md and "
            "reports/DEV_REPORT.md exist. Confirm the authoritative current facts and keep "
            "only reports/PROJECT_STATUS.md before integration."
        )
    if (
        integration["pending_integration"]
        or integration["waiting_reports"]
        or integration["blocked_reports"]
    ):
        sections.append(
            "Integration status (machine-readable; Hooks do not start agents):\n"
            + json.dumps(integration, ensure_ascii=False, separators=(",", ":"))
        )
    if results:
        sections.append(f"Current integrated project status ({status_path}):\n{results}")
    if state:
        sections.append(f"Current discussion handoff:\n{state}")
    if not sections:
        return None
    text = "WishGraph project update (read-only context):\n\n" + "\n\n".join(sections)
    limit = int(config.get("session_summary_max_chars", 2000))
    if len(text) > limit:
        text = text[: max(0, limit - 18)].rstrip() + "\n... summary clipped"
    return text


def format_failure(result: CheckResult, scope: str) -> str:
    lines = [f"WishGraph external-memory sync failed ({scope}).", ""]
    lines.extend(f"- {error}" for error in result.errors)
    if result.trigger_paths:
        lines.extend(["", "Changed work that triggered closeout:"])
        lines.extend(f"- {path}" for path in result.trigger_paths[:12])
        if len(result.trigger_paths) > 12:
            lines.append(f"- ... and {len(result.trigger_paths) - 12} more")
    lines.extend(
        [
            "",
            "Task lifecycle: draft task specs do not authorize Workers; after an explicit",
            "creation command record approved + worker_creation_authorized=true, then",
            "Worker records running and completed/blocked/incomplete.",
            "Worker: create one new immutable reports/runs/<work-unit-id>.md,",
            "record work type, readiness, safety fields, validation, and Integrate or N/A,",
            "and do not edit shared state or start other agents.",
            "Integration: merge with --no-commit, rewrite reports/PROJECT_STATUS.md and",
            "prompts/DISCUSSION_AI.md, record integration kind and authorization, then",
            "record Updated or N/A for shared memory. Parallel/high-risk work needs user confirmation.",
            "Legacy ad-hoc reports remain readable; new work requires a Task or Revision.",
        ]
    )
    return "\n".join(lines)


def format_warnings(result: CheckResult) -> str:
    return "WishGraph status warnings:\n" + "\n".join(
        f"- {warning}" for warning in result.warnings
    )


NO_MATERIAL_DECISION_VALUES = {"no", "none", "false", "无", "否"}


def enqueue_terminal_notification_from_claim(
    root: Path,
    config: dict[str, Any],
    claim: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Translate durable Worker evidence into one host-neutral inbox record."""
    if not dry_run and claim.get("lease_status") != "released":
        return {"ok": False, "error": "released_worker_claim_required"}
    if dry_run and claim.get("lease_status") not in {"active", "released"}:
        return {"ok": False, "error": "active_worker_claim_required"}
    task_id = canonical_task_id(claim.get("task_id"))
    if not task_id:
        return {"ok": False, "error": "terminal_claim_task_id_invalid"}
    revision_id = canonical_revision_id(claim.get("revision_id"))
    if claim.get("revision_id") and not revision_id:
        return {"ok": False, "error": "terminal_claim_revision_id_invalid"}

    if revision_id:
        resolved = resolve_revision(root, config, revision_id)
        if not resolved.get("ok"):
            return {"ok": False, "error": "terminal_revision_unavailable"}
        work = resolved["revision"]
        work_type = "sequential"
        execution_mode = "exclusive"
        integration_policy = "inherited_task_approval"
    else:
        resolved = resolve_task(root, config, task_id)
        if not resolved.get("ok"):
            return {"ok": False, "error": "terminal_task_unavailable"}
        work = resolved["task"]
        task_path = str(work.get("task_path") or "")
        task_content = read_version(root, task_path, "worktree") or ""
        task_state = parse_task_state(task_path, task_content)
        work_type = task_state.work_type
        execution_mode = task_state.execution_mode
        integration_policy = task_state.integration_policy
    lifecycle = str(work.get("status") or "")
    run_report = str(work.get("run_report") or "")
    if lifecycle not in {"completed", "blocked", "incomplete"} or not run_report:
        return {"ok": False, "error": "terminal_evidence_incomplete"}
    report_content = read_version(root, run_report, "worktree")
    if report_content is None:
        return {"ok": False, "error": "terminal_run_report_missing"}
    report = report_state(run_report, report_content)

    material_decision = (
        report.new_decision not in NO_MATERIAL_DECISION_VALUES
        or report.selection_requires_judgment
        or (report.risk_flags_known and not report.risk_flags_clear)
        or work_type == "high_risk"
        or execution_mode == "competitive"
        or integration_policy == "requires_explicit_user_confirmation"
    )
    decision_only_errors = {
        "a new product, architecture, or data decision requires review"
    }
    mechanical_errors = [
        error for error in report.safety_errors if error not in decision_only_errors
    ]
    if lifecycle in {"blocked", "incomplete"} or report.status not in {
        "completed",
        "done",
    }:
        terminal_event = "failed"
        next_action = "resolve_worker_failure"
        reason = f"worker_{lifecycle}"
    elif mechanical_errors:
        terminal_event = "failed"
        next_action = "resolve_worker_failure"
        reason = "terminal_report_failed_safety_validation"
    elif material_decision:
        terminal_event = "decision_required"
        next_action = "resolve_conflict"
        reason = "material_integration_decision_required"
    else:
        terminal_event = "completed"
        next_action = "auto_integrate"
        reason = "safe_terminal_result_ready"

    notification_values = {
        "task_id": task_id,
        "work_unit_id": revision_id or task_id,
        "attempt": int(claim.get("attempt") or 1),
        "terminal_event": terminal_event,
        "task_lifecycle": lifecycle,
        "run_report": run_report,
        "claim_id": str(claim.get("claim_id") or ""),
        "worker_session_id": str(
            claim.get("host_thread_ref") or claim.get("worker_id") or ""
        ),
        "discussion_session_id": str(claim.get("discussion_session_id") or ""),
        "agent_platform": str(claim.get("agent_platform") or "unknown"),
        "next_action": next_action,
        "reason": reason,
    }
    if dry_run:
        return {"ok": True, "notification_plan": notification_values}
    return enqueue_worker_notification(root, **notification_values)


def ensure_terminal_notification_for_session(
    root: Path, config: dict[str, Any], session_id: str
) -> dict[str, Any]:
    """Retry notification creation from a terminal Hook without guessing prose."""
    if not session_id:
        return {"ok": True, "not_applicable": True}
    runtime = read_session_runtime(root, session_id) or {}
    previous_claim_id = str(
        ((runtime.get("worker_runtime") or {}).get("previous_claim_id") or "")
        if isinstance(runtime.get("worker_runtime"), dict)
        else ""
    )
    matching_claims = [
        claim
        for claim in inspect_claims(root)
        if (
            str(claim.get("claim_id") or "") == previous_claim_id
            or str(claim.get("worker_id") or "") == session_id
            or str(claim.get("host_thread_ref") or "") == session_id
        )
    ]
    active_claims = [
        claim
        for claim in matching_claims
        if claim.get("effective_lease_status") == "active"
    ]
    if active_claims:
        return {"ok": False, "error": "active_worker_claim_not_closed_out"}
    claims = [
        claim for claim in matching_claims if claim.get("lease_status") == "released"
    ]
    if not claims:
        return {"ok": True, "not_applicable": True}
    claims.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return enqueue_terminal_notification_from_claim(root, config, claims[0])


def format_worker_notifications(notifications: list[dict[str, Any]]) -> str:
    """Keep activation context compact and machine-readable."""
    if not notifications:
        return ""
    compact = [
        {
            "notification_id": item.get("notification_id"),
            "task_id": item.get("task_id"),
            "work_unit_id": item.get("work_unit_id"),
            "event": item.get("terminal_event"),
            "lifecycle": item.get("task_lifecycle"),
            "run_report": item.get("run_report"),
            "next_action": item.get("next_action"),
            "reason": item.get("reason"),
        }
        for item in notifications
    ]
    return (
        "WishGraph Worker notifications (consumed and marked read; evaluate in "
        "Discussion, never implement as fallback):\n"
        + json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
    )


def consume_discussion_notification_context(
    root: Path, session_id: str, *, adopt_project_pending: bool = False
) -> str:
    if not session_id:
        return ""
    consumed = consume_worker_notifications(
        root,
        session_id,
        adopt_project_pending=adopt_project_pending,
    )
    if not consumed.get("ok"):
        return (
            "WishGraph Worker notification inbox could not be consumed: "
            + str(consumed.get("error") or "unknown_error")
        )
    return format_worker_notifications(consumed.get("notifications", []))


def join_context(*parts: Optional[str]) -> str:
    return "\n\n".join(part for part in parts if part)


def format_session_safety(result: CheckResult) -> str:
    """Return concise safety-only SessionStart context without role activation."""
    issues = [*result.errors, *result.warnings]
    if not issues:
        return ""
    lines = ["WishGraph safety check found project-state issues:"]
    lines.extend(f"- {issue}" for issue in issues[:8])
    if len(issues) > 8:
        lines.append(f"- ... and {len(issues) - 8} more")
    lines.append(
        "Resolve these issues before claiming completion. Say '开始讨论' or "
        "'Start discussion' when you want WishGraph to load discussion context."
    )
    return "\n".join(lines)


def read_hook_input() -> dict[str, Any]:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return {}
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def emit(value: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(value, ensure_ascii=False))
    sys.stdout.write("\n")


def is_git_commit_command(command: str) -> bool:
    return bool(re.search(r"(?is)(?:^|[;&|]\s*)git\b[^\n;&|]*\bcommit\b", command))


def commit_uses_implicit_staging(command: str) -> bool:
    match = re.search(r"(?is)(?:^|[;&|]\s*)git\b[^\n;&|]*\bcommit\b([^\n;&|]*)", command)
    if not match:
        return False
    tail = match.group(1)
    return bool(
        re.search(
            r"(?:^|\s)(?:--all|--include|--only|-[A-Za-z]*[aio][A-Za-z]*)(?:\s|=|$)",
            tail,
        )
    )


BUILD_COMMAND_RE = re.compile(
    r"(?is)(?:^|[;&|]\s*)(?:python\d*\s+-m\s+(?:pytest|unittest)|pytest|"
    r"(?:uv|poetry)\s+run\s+pytest|tox|"
    r"xcodebuild|cargo\s+(?:test|build|check)|go\s+test|"
    r"swift\s+(?:test|build)|dotnet\s+(?:test|build)|cmake\s+--build|"
    r"ninja|bazel\s+(?:test|build)|meson\s+(?:compile|test)|"
    r"bun\s+(?:test|run\s+build)|"
    r"(?:npm|pnpm|yarn)\s+(?:test|run\s+build|build)|"
    r"(?:gradle|gradlew|mvn|make)\b)"
)
DEPENDENCY_COMMAND_RE = re.compile(
    r"(?is)(?:^|[;&|]\s*)(?:python\d*\s+-m\s+pip\s+install|pip\d*\s+install|"
    r"(?:npm|pnpm|yarn)\s+(?:install|add)|brew\s+install|"
    r"(?:apt|apt-get|dnf|yum)\s+install)\b"
)
WORKTREE_WRITE_COMMAND_RE = re.compile(
    r"(?is)(?:^|[;&|]\s*)(?:sed\s+[^\n;&|]*\s-i\b|perl\s+[^\n;&|]*\s-pi\b|"
    r"(?:tee|cp|mv|rm|touch)\b)|(?:^|[^<])>{1,2}(?!=)"
)
MERGE_COMMAND_RE = re.compile(
    r"(?is)(?:^|[;&|]\s*)git\s+(?:merge|cherry-pick|rebase)\b"
)


def hook_session_id(payload: dict[str, Any]) -> str:
    for key in ("session_id", "conversation_id", "thread_id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _tool_paths(tool_input: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for key in (
        "file_path",
        "filePath",
        "path",
        "target_path",
        "targetPath",
        "old_path",
        "new_path",
    ):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            paths.append(value.strip().replace("\\", "/"))
    patch = (
        tool_input.get("patch")
        or tool_input.get("input")
        or tool_input.get("command")
    )
    if isinstance(patch, str):
        paths.extend(
            match.replace("\\", "/")
            for match in re.findall(
                r"(?m)^\*\*\* (?:Add|Update|Delete) File:\s*(.+?)\s*$", patch
            )
        )
    return paths


def _relative_tool_path(root: Path, value: str) -> str:
    path = Path(value)
    candidate = path.resolve() if path.is_absolute() else (root / path).resolve()
    try:
        return candidate.relative_to(root.resolve()).as_posix()
    except ValueError:
        return candidate.as_posix()


def _path_operation(
    root: Path, config: dict[str, Any], paths: list[str]
) -> tuple[str, str]:
    if not paths:
        return "business_write", ""
    relative_paths = [_relative_tool_path(root, path) for path in paths]
    managed_shared = {
        config["paths"]["prd"],
        config["paths"]["architecture"],
        config["paths"]["codemap"],
        config["paths"]["conventions"],
        config["paths"]["discussion_prompt"],
        config["paths"]["execution_prompt"],
        config["paths"]["integration_prompt"],
        config["paths"]["project_status"],
    }
    if all(path in managed_shared for path in relative_paths):
        return "shared_state_write", ""
    task_globs = configured_task_globs(config)
    if all(any(fnmatch.fnmatch(path, glob) for glob in task_globs) for path in relative_paths):
        return "governance_write", "task_paths:" + "\n".join(relative_paths)
    revision_glob = configured_revision_glob(config)
    if all(fnmatch.fnmatch(path, revision_glob) for path in relative_paths):
        return "governance_write", "revision_paths:" + "\n".join(relative_paths)
    return "business_write", "business_paths:" + "\n".join(relative_paths)


def _shell_write_paths(command: str) -> list[str]:
    paths: list[str] = []
    for segment in re.split(r"\s*(?:&&|\|\||[;|])\s*", command):
        try:
            tokens = shlex.split(segment)
        except ValueError:
            continue
        if not tokens:
            continue
        executable = Path(tokens[0]).name.lower()
        arguments = [token for token in tokens[1:] if not token.startswith("-")]
        if executable in {"touch", "rm", "tee", "cp", "mv"}:
            paths.extend(arguments)
        elif executable in {"sed", "perl"} and arguments:
            paths.append(arguments[-1])
    paths.extend(
        match.group(1).strip("\"'")
        for match in re.finditer(r"(?<!<)>{1,2}\s*([^\s;&|]+)", command)
    )
    return paths


def classify_tool_operation(
    root: Path, config: dict[str, Any], payload: dict[str, Any]
) -> Optional[tuple[str, str]]:
    tool_name = str(payload.get("tool_name") or "").lower()
    tool_input = payload.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    if tool_name in {"bash", "shell", "exec_command"}:
        command = str(tool_input.get("command") or "")
        if DEPENDENCY_COMMAND_RE.search(command):
            return "install_dependency", ""
        if BUILD_COMMAND_RE.search(command):
            return "build_test", ""
        if MERGE_COMMAND_RE.search(command):
            return "business_write", "merge_resolution"
        if is_git_commit_command(command):
            return "commit", ""
        if WORKTREE_WRITE_COMMAND_RE.search(command):
            return _path_operation(root, config, _shell_write_paths(command))
        return None
    if tool_name in {"write", "edit", "multiedit", "notebookedit", "apply_patch"}:
        return _path_operation(root, config, _tool_paths(tool_input))
    if tool_name.startswith("mcp__") and re.search(
        r"(?:write|edit|patch|create|delete|move|rename|update)", tool_name
    ):
        return _path_operation(root, config, _tool_paths(tool_input))
    return None


def _wishgraph_control_command(command: str) -> Optional[dict[str, Any]]:
    """Parse one bounded memory_sync control command without evaluating the shell."""
    if "memory_sync.py" not in command.replace("\\", "/"):
        return None
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return {"mixed": True, "error": "wishgraph_control_command_unparseable"}
    script_indexes = [
        index
        for index, token in enumerate(tokens)
        if token.replace("\\", "/").endswith("/memory_sync.py")
        or token == "memory_sync.py"
    ]
    if len(script_indexes) != 1 or any(token in {";", "&&", "&", "|", "||"} for token in tokens):
        return {"mixed": True, "error": "mixed_wishgraph_control_actions"}
    index = script_indexes[0]
    if index + 1 >= len(tokens):
        return {"mixed": True, "error": "wishgraph_control_action_missing"}
    command_name = tokens[index + 1]
    if command_name not in {"session", "integration-lease", "claim"}:
        return None
    arguments = tokens[index + 2 :]
    action = arguments[0] if arguments else ""

    def option(name: str) -> str:
        try:
            return arguments[arguments.index(name) + 1]
        except (ValueError, IndexError):
            return ""

    target_session_id = ""
    if command_name == "session" and len(arguments) >= 2:
        target_session_id = arguments[1]
    elif command_name == "integration-lease":
        target_session_id = option("--session-id")
    elif command_name == "claim" and action in {"acquire", "rebind"}:
        target_session_id = option("--session-id")
    elif command_name == "claim" and action in {"heartbeat", "release", "revoke"}:
        target_session_id = option("--session-id")
    return {
        "mixed": False,
        "command": command_name,
        "action": action,
        "target_session_id": target_session_id,
        "arguments": arguments,
        "agent_kind": option("--agent-kind"),
        "container_kind": option("--container-kind"),
        "authorized_by_user": "--authorized-by-user" in arguments,
    }


def wishgraph_control_gate_plan(
    root: Path, payload: dict[str, Any]
) -> Optional[FlowPlan]:
    tool_input = payload.get("tool_input")
    command_text = (
        str(tool_input.get("command") or "") if isinstance(tool_input, dict) else ""
    )
    control = _wishgraph_control_command(command_text)
    if control is None:
        return None
    if control.get("mixed"):
        return FlowPlan(
            accepted=False,
            next_action="deny_wishgraph_control_command",
            denial_reason=str(control.get("error") or "mixed_wishgraph_control_actions"),
        )
    session_id = hook_session_id(payload)
    runtime = read_session_runtime(root, session_id) if session_id else None
    session = runtime.get("session") if isinstance(runtime, dict) and isinstance(runtime.get("session"), dict) else {}
    launch_context = (
        runtime.get("launch_context")
        if isinstance(runtime, dict) and isinstance(runtime.get("launch_context"), dict)
        else {}
    )
    role = str(session.get("role") or "neutral")
    agent_kind = str(launch_context.get("agent_kind") or "")
    command_name = str(control.get("command") or "")
    action = str(control.get("action") or "")
    target_session_id = str(control.get("target_session_id") or "")

    if command_name == "session" and action == "get":
        return FlowPlan(accepted=True, next_action="allow_control_read")
    if command_name == "claim" and action == "inspect":
        return FlowPlan(accepted=True, next_action="allow_control_read")
    if command_name == "integration-lease" and action == "inspect":
        return FlowPlan(accepted=True, next_action="allow_control_read")
    if agent_kind in {"helper", "hidden_internal"}:
        return FlowPlan(
            accepted=False,
            next_action="deny_helper_authority",
            denial_reason="helper_or_hidden_agent_cannot_modify_claim_or_integration_authority",
        )
    if command_name == "session":
        allowed = (
            action == "transition"
            and role == "discussion"
            and target_session_id == session_id
        )
        return FlowPlan(
            accepted=allowed,
            next_action="allow_session_transition" if allowed else "deny_session_authority_write",
            denial_reason="session authority fields require an own-session Discussion transition" if not allowed else "",
        )
    if command_name == "integration-lease":
        allowed = (
            role == "discussion"
            and target_session_id == session_id
            and action in {"acquire", "heartbeat", "release", "revoke"}
        )
        return FlowPlan(
            accepted=allowed,
            next_action="allow_integration_control" if allowed else "deny_integration_authority",
            denial_reason="only the bound Discussion session may control its Integration lease" if not allowed else "",
        )
    if command_name == "claim":
        requested_agent_kind = str(control.get("agent_kind") or "formal_worker")
        if requested_agent_kind != "formal_worker":
            return FlowPlan(
                accepted=False,
                next_action="deny_helper_authority",
                denial_reason="only a Formal Worker may acquire or rebind a Worker Claim",
            )
        if action == "revoke":
            allowed = bool(control.get("authorized_by_user")) and role == "discussion"
        elif action in {"acquire", "rebind", "heartbeat", "release"}:
            allowed = role in {"neutral", "worker"} and target_session_id == session_id
        else:
            allowed = False
        return FlowPlan(
            accepted=allowed,
            next_action="allow_worker_claim_control" if allowed else "deny_worker_claim_control",
            denial_reason="Claim control must stay in its bound Formal Worker session" if not allowed else "",
        )
    return FlowPlan(
        accepted=False,
        next_action="deny_wishgraph_control_command",
        denial_reason="unrecognized_wishgraph_control_action",
    )


def worker_policy_mutation_plan(
    root: Path, payload: dict[str, Any]
) -> Optional[FlowPlan]:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    serialized = json.dumps(tool_input, ensure_ascii=False)
    if not re.search(r"integration_(?:policy|route)", serialized, re.IGNORECASE):
        return None
    session_id = hook_session_id(payload)
    runtime = read_session_runtime(root, session_id) if session_id else None
    if not isinstance(runtime, dict):
        return None
    session = runtime.get("session") if isinstance(runtime.get("session"), dict) else {}
    task = runtime.get("task") if isinstance(runtime.get("task"), dict) else {}
    if session.get("role") != "worker" or task.get("lifecycle") == "draft":
        return None
    paths = _tool_paths(tool_input)
    if not paths:
        command = str(tool_input.get("command") or "")
        paths = _shell_write_paths(command)
    normalized_paths = {_relative_tool_path(root, value) for value in paths}
    task_paths = {
        item["task_path"]
        for item in task_specs(root, load_config(root) or {})
        if item.get("task_id") == task.get("task_id")
    }
    if normalized_paths & task_paths:
        return FlowPlan(
            accepted=False,
            next_action="deny_task_policy_mutation",
            task_id=str(task.get("task_id") or ""),
            denial_reason="approved Task integration route is immutable and cannot be edited by a Worker",
        )
    return None


def orchestration_gate_plan(
    root: Path,
    config: dict[str, Any],
    payload: dict[str, Any],
    *,
    current_host: str = "unknown",
) -> Optional[FlowPlan]:
    classified = classify_tool_operation(root, config, payload)
    if classified is None or not config.get("orchestration_gate_enabled", True):
        return None
    operation, operation_scope = classified
    session_id = hook_session_id(payload)
    runtime = read_session_runtime(root, session_id) if session_id else None
    if runtime is None:
        runtime = {
            "session": {
                "session_id": session_id,
                "role": "neutral",
                "host": "unknown",
                "phase": "planning",
                "expected_transition": None,
            }
        }
    runtime = dict(runtime)
    session_value = runtime.get("session")
    session_value = dict(session_value) if isinstance(session_value, dict) else {}
    role = str(session_value.get("role") or "neutral")
    session_host = str(session_value.get("host") or "unknown")
    if role == "worker" and current_host in {"codex", "claude"}:
        host_guard = current_host_execution_guard(root, config, current_host)
        if not host_guard.get("ok"):
            return FlowPlan(
                accepted=False,
                next_action="deny_current_host_execution",
                denial_reason=str(host_guard.get("message") or host_guard.get("error")),
            )
    task_value = runtime.get("task") if isinstance(runtime.get("task"), dict) else {}
    task_id = str(task_value.get("task_id") or "")
    runtime["worker_runtime"] = {}
    runtime["integration_runtime"] = {}
    if role == "worker" and task_id:
        active_claims = [
            claim
            for claim in inspect_claims(root, task_id)
            if claim.get("effective_lease_status") == "active"
            and claim.get("branch") == current_branch(root)
            and claim.get("worktree") == str(root.resolve())
            and claim.get("agent_platform", "unknown") in {"", "unknown", session_host}
            and (
                claim.get("worker_id") == session_id
                or claim.get("host_thread_ref") == session_id
            )
        ]
        if len(active_claims) == 1:
            runtime["worker_runtime"] = {
                "claim_id": active_claims[0].get("claim_id"),
                "branch": active_claims[0].get("branch"),
                "worktree": active_claims[0].get("worktree"),
                "host_window_or_thread_id": active_claims[0].get("host_thread_ref"),
                "active_task_id": active_claims[0].get("task_id"),
                "active_revision_id": active_claims[0].get("revision_id") or "",
                "worker_session_id": active_claims[0].get("worker_id"),
                "worker_availability": "busy",
                "binding_status": "active",
                "allowed_scope": active_claims[0].get("allowed_scope", []),
                "validation_plan": active_claims[0].get("validation_plan", []),
                "execution_ownership": active_claims[0].get(
                    "execution_ownership", "worker_claim"
                ),
            }
    if role == "discussion" and session_value.get("phase") == "integrating":
        lease = inspect_integration_lease(root)
        if (
            lease
            and lease.get("effective_lease_status") == "active"
            and lease.get("session_id") == session_id
            and lease.get("base_branch") == current_branch(root)
            and lease.get("worktree") == str(root.resolve())
        ):
            runtime["integration_runtime"] = {
                "lease_id": lease.get("lease_id"),
                "integration_id": lease.get("integration_id"),
                "base_branch": lease.get("base_branch"),
                "worktree": lease.get("worktree"),
                "selected_task_ids": lease.get("selected_task_ids", []),
                "selected_reports": lease.get("selected_reports", []),
            }
    if operation == "governance_write" and operation_scope.startswith("task_paths:"):
        requested_paths = operation_scope.removeprefix("task_paths:").splitlines()
        states = []
        for path in requested_paths:
            content = read_version(root, path, "worktree")
            if content is None:
                continue
            states.append(parse_task_state(path, content))
        operation_scope = (
            "own_task_state"
            if states
            and len(states) == len(requested_paths)
            and task_id
            and all(state.task_id == task_id for state in states)
            else "other_task_state"
        )
    elif operation == "governance_write" and operation_scope.startswith(
        "revision_paths:"
    ):
        requested_paths = operation_scope.removeprefix("revision_paths:").splitlines()
        states = []
        for path in requested_paths:
            content = read_version(root, path, "worktree")
            if content is None:
                continue
            states.append(parse_revision_state(path, content))
        active_revision_id = str(
            runtime.get("worker_runtime", {}).get("active_revision_id") or ""
        )
        operation_scope = (
            "own_revision_state"
            if states
            and len(states) == len(requested_paths)
            and task_id
            and all(state.parent_task_id == task_id for state in states)
            and (
                not active_revision_id
                or all(state.revision_id == active_revision_id for state in states)
            )
            else "other_revision_state"
        )
    state = orchestration_state_from_dict(runtime)
    capability = host_capability_for(state.session.host)
    if config.get("read_gate_mode") == "enforce":
        capability = HostCapability(
            **{
                **capability.__dict__,
                "can_gate_reads": True,
            }
        )
    requested_paths = (
        operation_scope.removeprefix("business_paths:").splitlines()
        if operation_scope.startswith("business_paths:")
        else []
    )
    return reduce_orchestration(
        state,
        UserEvent(
            kind="operation_requested",
            data={
                "operation": operation,
                "operation_scope": operation_scope,
                "task_authorized": bool(task_value.get("worker_authorized")),
                "requested_paths": requested_paths,
            },
        ),
        capability,
    )


def emit_orchestration_gate(plan: FlowPlan, mode: str) -> None:
    reason = "WishGraph orchestration gate blocked this operation. " + plan.denial_reason
    if mode == "warn" and plan.next_action != "deny_current_host_execution":
        emit(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": reason,
                }
            }
        )
    else:
        emit(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )


def hook_prompt_text(payload: dict[str, Any]) -> str:
    for key in ("prompt", "user_prompt", "message", "text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def governance_ready(root: Path, config: dict[str, Any]) -> bool:
    paths = config["paths"]
    status_path = resolve_project_status_path(root, config)
    return (root / status_path).is_file() and (root / paths["discussion_prompt"]).is_file()


def formal_worker_launch_context(
    host_action: str,
    task_id: str,
    discussion_session_id: str,
    host_adapter_command: str,
    task_path: str = "",
) -> str:
    """Give the current Discussion one unambiguous, non-delegable launch action."""
    if host_action != "launch_claude_background_worker":
        return ""
    record = task_path or "the exact resolved Task record"
    return (
        "WishGraph Formal Worker launch contract (mandatory):\n"
        f"1. Persist the authorization for {task_id} in {record}, then create the "
        "bounded authorization commit. The working-tree Task record must exactly "
        "match HEAD before launch.\n"
        "2. In this current Discussion session, directly run this exact Host Adapter "
        f"command: {host_adapter_command}\n"
        "3. Do not use Task, Agent, /fork, a helper, or any ordinary background "
        "subagent to run or replace that command. Only the Host Adapter may create "
        "the managed wishgraph-worker.\n"
        "4. Stop after the Host Adapter result. Never implement business code in "
        f"Discussion. The originating Discussion session ID is {discussion_session_id}."
    )


def user_prompt_submit_main(
    root: Path, config: dict[str, Any], payload: dict[str, Any], host: str
) -> int:
    """Route explicit workflow commands without loading unrelated project files."""
    text = hook_prompt_text(payload)
    command = parse_user_prompt(text)
    session_id = hook_session_id(payload)
    runtime = read_session_runtime(root, session_id) if session_id else None
    command_action = str((command or {}).get("action") or "")
    runtime_role = str(((runtime or {}).get("session") or {}).get("role") or "neutral")
    runtime_agent_kind = str(
        ((runtime or {}).get("launch_context") or {}).get("agent_kind") or ""
    )
    notification_context = ""
    if runtime_role == "discussion" and command_action not in {
        "start_discussion",
        "refresh_project_status",
    }:
        notification_context = consume_discussion_notification_context(
            root, session_id
        )
    capability = host_capability_for(host)

    if command is None and runtime is not None and is_contextual_approval(text):
        plan = reduce_orchestration(
            orchestration_state_from_dict(runtime),
            UserEvent(kind="user_message", data={"text": text}),
            capability,
        )
        action = map_flow_plan_to_host(plan, capability)
        if plan.accepted and session_id and action.state_patch:
            apply_session_runtime_patch(root, session_id, action.state_patch)
        host_adapter_command = (
            "python3 .wishgraph/hooks/memory_sync.py "
            f"claude-worker launch {plan.task_id} "
            f"--discussion-session-id {session_id}"
            if action.action == "launch_claude_background_worker"
            else (
                "python3 .wishgraph/hooks/memory_sync.py "
                f"codex-worker prepare {plan.task_id} "
                f"--discussion-session-id {session_id}"
                if action.action == "launch_codex_agent_worker"
                else ""
            )
        )
        emit(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": join_context(
                        notification_context,
                        formal_worker_launch_context(
                            action.action,
                            plan.task_id,
                            session_id,
                            host_adapter_command,
                        ),
                        "WishGraph contextual route:\n"
                        + json.dumps(
                            {
                                "accepted": plan.accepted,
                                "next_action": action.action,
                                "task_id": plan.task_id,
                                "discussion_session_id": session_id,
                                "host_adapter_command": host_adapter_command,
                                "launch_must_run_in_current_discussion": (
                                    action.action == "launch_claude_background_worker"
                                ),
                                "delegation_forbidden": (
                                    action.action == "launch_claude_background_worker"
                                ),
                                "user_message": action.user_message,
                                "stop_after_action": action.stop_after_action,
                                "denial_reason": plan.denial_reason,
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    ),
                }
            }
        )
        return 0
    if command is None:
        if notification_context:
            emit(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": notification_context,
                    }
                }
            )
        else:
            emit({})
        return 0

    action = command["action"]
    if action == "start_discussion":
        if runtime_role == "worker" or runtime_agent_kind in {
            "formal_worker",
            "helper",
            "hidden_internal",
        }:
            emit(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": (
                            "WishGraph role boundary: a Worker session cannot become "
                            "Discussion. Return to the original Discussion or open a "
                            "neutral session and say '开始讨论'."
                        ),
                    }
                }
            )
            return 0
        if session_id:
            patch = {
                "session": {
                    "session_id": session_id,
                    "role": "discussion",
                    "host": host,
                    "phase": "planning",
                    "expected_transition": None,
                },
                "session_provenance": _discussion_provenance_patch(host),
            }
            if runtime is None:
                write_session_runtime(root, session_id, patch)
            else:
                apply_session_runtime_patch(root, session_id, patch)
        explicit_config = dict(config)
        explicit_config["session_start_context_mode"] = "discussion_summary"
        context = project_session_context(root, explicit_config)
        notification_context = consume_discussion_notification_context(
            root, session_id, adopt_project_pending=True
        )
        if context is None:
            context = (
                "WishGraph discussion role is active. Project memory is not initialized; "
                "bootstrap the minimum WishGraph state before planning implementation."
            )
        emit(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": join_context(
                        notification_context, context
                    ),
                }
            }
        )
        return 0

    if action == "refresh_project_status":
        explicit_config = dict(config)
        explicit_config["session_start_context_mode"] = "discussion_summary"
        context = project_session_context(root, explicit_config) or (
            "WishGraph project memory is not initialized. Run the project bootstrap first."
        )
        notification_context = consume_discussion_notification_context(
            root, session_id, adopt_project_pending=True
        )
        if (
            host == "claude"
            and session_id
            and isinstance((runtime or {}).get("worker_runtime"), dict)
            and (runtime or {}).get("worker_runtime", {}).get("claude_session_id")
        ):
            context += (
                "\n\nClaude Worker refresh (read-only host observation; do not infer "
                "completion from prose):\n"
                "python3 .wishgraph/hooks/memory_sync.py claude-worker refresh "
                f"--discussion-session-id {session_id}"
            )
        emit(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": join_context(
                        notification_context, context
                    ),
                }
            }
        )
        return 0

    task_id = str(command.get("task_id") or "")
    if action in {"inspect", "observe", "family"}:
        state = integration_state(root, config, view="active", task_id=task_id)
        emit(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": join_context(
                        notification_context,
                        json.dumps(
                            state.as_dict(),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    ),
                }
            }
        )
        return 0

    resolved = resolve_task(root, config, task_id)
    if not resolved.get("ok"):
        route = resolved
    else:
        role = str(((runtime or {}).get("session") or {}).get("role") or "neutral")
        if role == "worker":
            host_action = "continue_or_rebind_current_worker"
            accepted = True
            plan_payload: dict[str, Any] = {}
        else:
            task_record = resolved["task"]
            transition_runtime = dict(runtime or {})
            transition_runtime["session"] = {
                **(
                    transition_runtime.get("session")
                    if isinstance(transition_runtime.get("session"), dict)
                    else {}
                ),
                "session_id": session_id,
                "role": role,
                "host": host,
                "phase": str(
                    ((runtime or {}).get("session") or {}).get("phase") or "planning"
                ),
            }
            transition_runtime["task"] = {
                "task_id": task_id,
                "lifecycle": str(task_record.get("status") or "draft"),
                "attempt": int(task_record.get("attempt") or 1),
                "worker_authorized": task_record.get("worker_creation_authorized") is True,
                "run_report": str(task_record.get("run_report") or ""),
            }
            plan = reduce_orchestration(
                orchestration_state_from_dict(transition_runtime),
                UserEvent(kind="user_message", data={"text": text}),
                capability,
            )
            mapped = map_flow_plan_to_host(plan, capability)
            accepted = plan.accepted
            host_action = (
                "enter_current_window_as_worker"
                if mapped.action == "enter_worker"
                else mapped.action
            )
            plan_payload = flow_plan_to_dict(plan)
            if accepted and session_id and mapped.state_patch:
                if runtime is None:
                    transition_runtime["session_provenance"] = {
                        "initial_role": "neutral",
                        "host": host,
                        "discussion_authorized": False,
                        "created_at": _utc_now(),
                    }
                    created = write_session_runtime(
                        root, session_id, transition_runtime
                    )
                    persisted = (
                        apply_session_runtime_patch(
                            root, session_id, mapped.state_patch
                        )
                        if created.get("ok")
                        else created
                    )
                else:
                    persisted = apply_session_runtime_patch(
                        root, session_id, mapped.state_patch
                    )
                if not persisted.get("ok"):
                    accepted = False
                    host_action = "no_action"
                    plan_payload["denial_reason"] = "authorization_runtime_persistence_failed"
        host_adapter_command = (
            "python3 .wishgraph/hooks/memory_sync.py "
            f"claude-worker launch {task_id} "
            f"--discussion-session-id {session_id}"
            if host_action == "launch_claude_background_worker"
            else (
                "python3 .wishgraph/hooks/memory_sync.py "
                f"codex-worker prepare {task_id} "
                f"--discussion-session-id {session_id}"
                if host_action == "launch_codex_agent_worker"
                else ""
            )
        )
        route = {
            "ok": accepted,
            "command": command,
            "task": resolved["task"],
            "plan": plan_payload,
            "host_action": host_action,
            "worker_session_id": session_id,
            "discussion_session_id": session_id if role == "discussion" else "",
            "host_adapter_command": host_adapter_command,
            "manual_command": (
                f"执行 {task_id} 任务"
                if host_action == "show_manual_worker_command"
                else ""
            ),
            "stop_after_action": role == "discussion",
            "authorization_patch_required": role == "discussion",
            "authorization_commit_required": bool(
                role == "discussion"
                and host_action == "launch_claude_background_worker"
            ),
            "launch_must_run_in_current_discussion": bool(
                role == "discussion"
                and host_action == "launch_claude_background_worker"
            ),
            "delegation_forbidden": bool(
                role == "discussion"
                and host_action == "launch_claude_background_worker"
            ),
            "required_before_business_work": "execution_preflight_and_worker_claim",
            "read_boundary": "exact_task_scope_and_explicit_context_only",
        }
    emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": join_context(
                    notification_context,
                    formal_worker_launch_context(
                        host_action,
                        task_id,
                        session_id,
                        host_adapter_command,
                        str(resolved["task"].get("task_path") or ""),
                    ),
                    "WishGraph explicit route:\n"
                    + json.dumps(route, ensure_ascii=False, separators=(",", ":")),
                ),
            }
        }
    )
    return 0


def hook_main(event: str, host: str = "unknown") -> int:
    payload = read_hook_input()
    root = find_git_root(Path(payload.get("cwd") or os.getcwd()))
    if root is None:
        emit({})
        return 0

    try:
        config = load_config(root)
    except ValueError as exc:
        emit({"systemMessage": f"WishGraph hook configuration error: {exc}"})
        return 0
    if config is None or config.get("mode") == "off":
        emit({})
        return 0

    if event in HOST_OBSERVATION_EVENTS and host in {"codex", "claude"}:
        # This is runtime liveness evidence, not semantic project memory. Keep it
        # outside the worktree and never add this write to high-frequency tool gates.
        record_host_observation(root, host, event, config.get("runtime_version"))

    if event == "session-start":
        session_id = hook_session_id(payload)
        session_runtime = read_session_runtime(root, session_id) if session_id else None
        if session_id and session_runtime is None:
            write_session_runtime(
                root,
                session_id,
                {
                    "session": {
                        "session_id": session_id,
                        "role": "neutral",
                        "host": host,
                        "phase": "planning",
                        "expected_transition": None,
                    },
                    "session_provenance": {
                        "initial_role": "neutral",
                        "host": host,
                        "discussion_authorized": False,
                        "created_at": _utc_now(),
                    },
                },
            )
            session_runtime = read_session_runtime(root, session_id)
        session_notification_context = ""
        if (
            session_id
            and isinstance(session_runtime, dict)
            and str((session_runtime.get("session") or {}).get("role") or "")
            == "discussion"
        ):
            session_notification_context = consume_discussion_notification_context(
                root, session_id
            )
    else:
        session_notification_context = ""

    if event == "user-prompt-submit":
        return user_prompt_submit_main(root, config, payload, host)

    if event == "session-start" and not governance_ready(root, config):
        emit(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": join_context(
                        session_notification_context,
                        "WishGraph hooks are active in "
                        f"{config.get('mode', 'warn')} mode, but project memory is not "
                        "initialized. Say '开始讨论' or 'Start discussion' to bootstrap "
                        "the minimum project state.",
                    ),
                }
            }
        )
        return 0

    if event == "pre-tool-use":
        tool_input = payload.get("tool_input")
        command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
        for authority_plan in (
            wishgraph_control_gate_plan(root, payload),
            worker_policy_mutation_plan(root, payload),
        ):
            if authority_plan is not None and not authority_plan.accepted:
                emit(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": (
                                "WishGraph authority gate blocked this operation. "
                                + authority_plan.denial_reason
                            ),
                        }
                    }
                )
                return 0
        commit_command = payload.get("tool_name") == "Bash" and is_git_commit_command(
            str(command)
        )
        if commit_command and commit_uses_implicit_staging(str(command)):
            reason = (
                "WishGraph blocks git commit options that stage implicitly (-a/--all, "
                "-i/--include, -o/--only). Stage the bounded code and external-memory "
                "files explicitly, run the staged memory check, then commit."
            )
            if config.get("mode") == "warn":
                emit(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "additionalContext": reason,
                        }
                    }
                )
            else:
                emit(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": reason,
                        }
                    }
                )
            return 0
        result = check_sync(root, config, "staged") if commit_command else None
        if result is not None and not result.ok:
            reason = format_failure(result, "staged")
            if config.get("mode") == "warn":
                emit(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "additionalContext": reason,
                        }
                    }
                )
            else:
                emit(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": reason,
                        }
                    }
                )
            return 0
        gate_plan = orchestration_gate_plan(
            root, config, payload, current_host=host
        )
        if gate_plan is not None and not gate_plan.accepted:
            emit_orchestration_gate(gate_plan, str(config.get("mode")))
            return 0
        if result is not None and result.warnings:
            emit(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "additionalContext": format_warnings(result),
                    }
                }
            )
        else:
            emit({})
        return 0

    result = check_sync(root, config, "worktree")
    session_context = (
        join_context(
            session_notification_context,
            project_session_context(root, config),
        )
        if event == "session-start"
        else None
    )
    if result.ok and event in {"stop", "task-completed"}:
        terminal_notification = ensure_terminal_notification_for_session(
            root, config, hook_session_id(payload)
        )
        if not terminal_notification.get("ok"):
            notification_error = str(
                terminal_notification.get("error") or "unknown_error"
            )
            reason = (
                "WishGraph Worker cannot stop with an active Claim. Write the "
                "terminal Task/Revision state and Run Report, then release the Claim "
                "so its Discussion notification is durable."
                if notification_error == "active_worker_claim_not_closed_out"
                else "WishGraph could not persist the Worker terminal notification: "
                + notification_error
            )
            if event == "task-completed":
                print(reason, file=sys.stderr)
                return 2
            emit({"decision": "block", "reason": reason})
            return 0
    if result.ok:
        warning_text = format_warnings(result) if result.warnings else None
        if event == "session-start" and (session_context or warning_text):
            session_warning = format_session_safety(result) if result.warnings else None
            emit(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": "\n\n".join(
                            part for part in (session_context, session_warning) if part
                        ),
                    }
                }
            )
        elif warning_text and event == "task-completed":
            print(warning_text, file=sys.stderr)
            emit({})
        elif warning_text:
            emit({"systemMessage": warning_text})
        else:
            emit({})
        return 0
    reason = format_failure(result, "worktree")

    if event == "session-start":
        context_parts = []
        if session_context:
            context_parts.append(session_context)
        context_parts.append(format_session_safety(result))
        emit(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": "\n\n".join(context_parts),
                }
            }
        )
    elif event == "task-completed":
        print(reason, file=sys.stderr)
        if config.get("mode") == "warn":
            emit({})
            return 0
        return 2
    elif config.get("mode") == "warn":
        emit({"systemMessage": reason})
    else:
        emit({"decision": "block", "reason": reason})
    return 0


def check_main(scope: str) -> int:
    root = find_git_root(Path.cwd())
    if root is None:
        print("WishGraph memory check requires a Git repository.", file=sys.stderr)
        return 2
    try:
        config = load_config(root)
    except ValueError as exc:
        print(f"WishGraph hook configuration error: {exc}", file=sys.stderr)
        return 2
    if config is None:
        print("WishGraph hooks are not installed in this repository.", file=sys.stderr)
        return 2
    result = check_sync(root, config, scope)
    if result.ok:
        print(f"WishGraph external-memory sync: PASS ({scope})")
        if result.warnings:
            print(format_warnings(result), file=sys.stderr)
        return 0
    if config.get("mode") == "warn":
        print(
            "WishGraph external-memory sync: WARNING "
            f"({scope}; warn mode does not block)\n\n{format_failure(result, scope)}",
            file=sys.stderr,
        )
        return 0
    print(format_failure(result, scope), file=sys.stderr)
    return 1


def status_main(view: str = "active", task_id: Optional[str] = None) -> int:
    root = find_git_root(Path.cwd())
    if root is None:
        print("WishGraph integration status requires a Git repository.", file=sys.stderr)
        return 2
    try:
        config = load_config(root)
    except ValueError as exc:
        print(f"WishGraph hook configuration error: {exc}", file=sys.stderr)
        return 2
    if config is None:
        print("WishGraph hooks are not installed in this repository.", file=sys.stderr)
        return 2
    try:
        state = integration_state(root, config, view=view, task_id=task_id)
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(state.as_dict(), ensure_ascii=False, indent=2))
    return 0


def integration_plan_main(host_capability: str) -> int:
    root = find_git_root(Path.cwd())
    if root is None:
        print(json.dumps({"ok": False, "error": "git_repository_required"}))
        return 2
    try:
        config = load_config(root)
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": "invalid_config", "detail": str(exc)}))
        return 2
    if config is None:
        print(json.dumps({"ok": False, "error": "wishgraph_not_installed"}))
        return 2
    state = integration_state(root, config, view="active").as_dict()
    if not state["auto_integration_eligible"]:
        host_action = state["next_action"]
    elif host_capability in {"background", "active_agent"}:
        host_action = "enter_discussion_local_integration"
    else:
        host_action = "persist_integration_pending_until_discussion_resume"
    payload = {
        "ok": True,
        "visibility": "silent_unless_blocked",
        "host_capability": host_capability,
        "host_action": host_action,
        "creates_visible_integration_window": False,
        "integration_prompt": config["paths"]["integration_prompt"],
        "ready_reports": state["selected_reports"] or state["ready_reports"],
        "status": state,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def flow_plan_main(args: argparse.Namespace) -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        state = orchestration_state_from_dict(payload["state"])
        event_value = payload["event"]
        event = UserEvent(
            kind=str(event_value["kind"]),
            data=event_value.get("data", {}) if isinstance(event_value, dict) else {},
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": "invalid_flow_input", "detail": str(exc)}))
        return 2
    capability = HostCapability(
        host=args.host,
        can_spawn_execution_thread=args.can_spawn_execution_thread,
        can_inspect_execution_thread=args.can_inspect_execution_thread,
        can_bind_thread_id=args.can_bind_thread_id,
        can_stop_or_steer_thread=args.can_stop_or_steer_thread,
        can_isolate_worktree=args.can_isolate_worktree,
        can_observe_terminal_result=args.can_observe_terminal_result,
        can_gate_writes=True,
        can_gate_builds=True,
        can_gate_reads=args.can_gate_reads,
        can_deliver_result_to_discussion=args.can_deliver_result_to_discussion,
    )
    plan = reduce_orchestration(state, event, capability)
    action = map_flow_plan_to_host(plan, capability)
    print(
        json.dumps(
            {
                "ok": True,
                "plan": flow_plan_to_dict(plan),
                "host_action": {
                    "action": action.action,
                    "state_patch": action.state_patch,
                    "user_message": action.user_message,
                    "stop_after_action": action.stop_after_action,
                    "creates_inspectable_thread": action.creates_inspectable_thread,
                    "target_worker_id": action.target_worker_id,
                    "work_payload": action.work_payload,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


SESSION_DIAGNOSTIC_PATCH_KEYS = {"diagnostics", "adapter_diagnostics"}
DISCUSSION_TRANSITION_EVENTS = {
    "integration_evaluated",
    "decision_resolved",
    "integration_completed",
}


def _discussion_provenance_patch(host: str) -> dict[str, Any]:
    return {
        "initial_role": "neutral",
        "host": host,
        "discussion_authorized": True,
        "discussion_authorized_at": _utc_now(),
    }


def _verified_discussion_runtime(
    runtime: Optional[dict[str, Any]], session_id: str
) -> bool:
    if not isinstance(runtime, dict):
        return False
    session = runtime.get("session") if isinstance(runtime.get("session"), dict) else {}
    provenance = (
        runtime.get("session_provenance")
        if isinstance(runtime.get("session_provenance"), dict)
        else {}
    )
    launch_context = (
        runtime.get("launch_context")
        if isinstance(runtime.get("launch_context"), dict)
        else {}
    )
    return bool(
        session.get("session_id") == session_id
        and session.get("role") == "discussion"
        and provenance.get("initial_role") == "neutral"
        and provenance.get("discussion_authorized") is True
        and launch_context.get("agent_kind")
        not in {"formal_worker", "helper", "hidden_internal"}
    )


def _integration_transition_selection(
    root: Path,
    config: dict[str, Any],
    runtime: dict[str, Any],
    data: dict[str, Any],
) -> dict[str, Any]:
    """Recompute exact safe Integration evidence from durable Task/Report/Claim facts."""
    session = runtime.get("session") if isinstance(runtime.get("session"), dict) else {}
    task_runtime = runtime.get("task") if isinstance(runtime.get("task"), dict) else {}
    expected = (
        session.get("expected_transition")
        if isinstance(session.get("expected_transition"), dict)
        else {}
    )
    if session.get("phase") != "integration_pending":
        return {"ok": False, "error": "integration_pending_phase_required"}
    if expected.get("kind") != "auto_integrate":
        return {"ok": False, "error": "auto_integration_transition_required"}

    raw_task_ids = data.get("task_ids")
    if not isinstance(raw_task_ids, list) or not raw_task_ids:
        raw_task_ids = [task_runtime.get("task_id") or expected.get("task_id")]
    task_ids = [canonical_task_id(value) for value in raw_task_ids]
    if any(not value for value in task_ids) or len(set(task_ids)) != len(task_ids):
        return {"ok": False, "error": "invalid_or_duplicate_integration_task_id"}
    raw_reports = data.get("reports")
    if not isinstance(raw_reports, list) or not raw_reports:
        raw_reports = [expected.get("report_id") or task_runtime.get("run_report")]
    reports = [str(value or "").replace("\\", "/") for value in raw_reports]
    if any(not value for value in reports) or len(reports) != len(task_ids):
        return {"ok": False, "error": "integration_task_report_cardinality_mismatch"}
    integration_id = str(data.get("integration_id") or expected.get("integration_id") or "")
    if not integration_id or not RUNTIME_ID_RE.fullmatch(integration_id):
        return {"ok": False, "error": "invalid_integration_id"}

    status = integration_state(
        root,
        config,
        view="active",
        task_id=task_ids[0] if len(task_ids) == 1 else None,
    ).as_dict()
    decision_receipt = (
        (runtime.get("integration_runtime") or {}).get("decision_receipt")
        if isinstance(runtime.get("integration_runtime"), dict)
        else None
    )
    decision_confirmed = bool(
        isinstance(decision_receipt, dict)
        and decision_receipt.get("confirmed") is True
        and decision_receipt.get("task_id") in task_ids
    )
    safe_route = bool(status.get("auto_integration_eligible"))
    selected_reports = list(status.get("selected_reports") or [])
    if safe_route:
        if sorted(selected_reports) != sorted(reports):
            return {"ok": False, "error": "integration_report_selection_mismatch"}
        outcome = "safe"
    elif decision_confirmed:
        if not set(reports).issubset(set(status.get("ready_reports") or [])):
            return {"ok": False, "error": "confirmed_report_selection_not_ready"}
        outcome = "decision_confirmed"
    else:
        return {
            "ok": False,
            "error": "integration_evidence_not_safe",
            "next_action": status.get("next_action"),
        }

    units_by_report = {
        str(item.get("run_report") or ""): item
        for item in status.get("work_units", [])
        if isinstance(item, dict)
    }
    for task_id, report_path in zip(task_ids, reports):
        unit = units_by_report.get(report_path)
        if unit is None:
            return {"ok": False, "error": "integration_report_not_bound_to_work_unit"}
        unit_task_id = canonical_task_id(
            unit.get("task_id") or unit.get("parent_task_id")
        )
        if unit_task_id != task_id:
            return {"ok": False, "error": "integration_task_report_mismatch"}
        if unit.get("lifecycle_status") != "completed" or unit.get("errors"):
            return {"ok": False, "error": "integration_work_unit_not_completed"}
        if unit.get("active_claims"):
            return {"ok": False, "error": "active_worker_claim_exists"}
        report_content = read_version(root, report_path, "worktree")
        if report_content is None:
            return {"ok": False, "error": "integration_run_report_missing"}
        parsed_report = report_state(report_path, report_content)
        if parsed_report.status not in {"completed", "done"} or parsed_report.safety_errors:
            return {"ok": False, "error": "integration_run_report_invalid"}
        matching_claims = [
            claim
            for claim in inspect_claims(root, task_id)
            if (
                str(claim.get("revision_id") or "")
                == str(unit.get("revision_id") or "")
            )
        ]
        if any(
            claim.get("effective_lease_status") == "active"
            for claim in matching_claims
        ):
            return {"ok": False, "error": "active_worker_claim_exists"}
        if not any(claim.get("lease_status") == "released" for claim in matching_claims):
            return {"ok": False, "error": "released_worker_claim_required"}

    return {
        "ok": True,
        "integration_id": integration_id,
        "task_ids": task_ids,
        "reports": reports,
        "outcome": outcome,
        "status": status,
    }


def transition_session_runtime(
    root: Path,
    config: dict[str, Any],
    session_id: str,
    event_kind: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    runtime = read_session_runtime(root, session_id)
    if not _verified_discussion_runtime(runtime, session_id):
        return {"ok": False, "error": "verified_discussion_session_required"}
    if event_kind not in DISCUSSION_TRANSITION_EVENTS:
        return {"ok": False, "error": "unsupported_public_session_transition"}
    assert runtime is not None
    evidence: Optional[dict[str, Any]] = None
    reducer_data = dict(data)
    if event_kind == "integration_evaluated" and data.get("outcome") == "safe":
        evidence = _integration_transition_selection(root, config, runtime, data)
        if not evidence.get("ok"):
            return evidence
        reducer_data["outcome"] = "safe"
        reducer_data["integration_id"] = evidence["integration_id"]
    plan = reduce_orchestration(
        orchestration_state_from_dict(runtime),
        UserEvent(kind=event_kind, data=reducer_data),
        host_capability_for(str((runtime.get("session") or {}).get("host") or "unknown")),
    )
    if not plan.accepted:
        return {
            "ok": False,
            "error": plan.denial_reason or "session_transition_rejected",
            "plan": flow_plan_to_dict(plan),
        }
    previous = dict(runtime)
    persisted = apply_session_runtime_patch(root, session_id, plan.state_patch)
    if not persisted.get("ok"):
        return {"ok": False, "error": "session_transition_persistence_failed"}
    grant_payload: Optional[dict[str, Any]] = None
    if plan.required_integration_lease:
        if evidence is None:
            write_session_runtime(root, session_id, previous)
            return {"ok": False, "error": "integration_transition_evidence_required"}
        grant_payload = create_integration_transition_grant(
            root,
            session_id=session_id,
            integration_id=evidence["integration_id"],
            task_ids=evidence["task_ids"],
            reports=evidence["reports"],
            outcome=evidence["outcome"],
        )
        if not grant_payload.get("ok"):
            write_session_runtime(root, session_id, previous)
            return grant_payload
        grant = grant_payload["grant"]
        bound = apply_session_runtime_patch(
            root,
            session_id,
            {
                "integration_runtime": {
                    "integration_id": evidence["integration_id"],
                    "transition_grant_id": grant["grant_id"],
                    "selected_task_ids": evidence["task_ids"],
                    "selected_reports": evidence["reports"],
                    "base_branch": grant["base_branch"],
                    "worktree": grant["worktree"],
                }
            },
        )
        if not bound.get("ok"):
            write_session_runtime(root, session_id, previous)
            return {"ok": False, "error": "integration_grant_binding_failed"}
    return {
        "ok": True,
        "plan": flow_plan_to_dict(plan),
        "runtime": read_session_runtime(root, session_id),
        "grant": grant_payload.get("grant") if grant_payload else None,
    }


def _validate_integration_grant_evidence(
    root: Path,
    config: dict[str, Any],
    runtime: dict[str, Any],
    grant_id: str,
    integration_id: str,
    task_ids: list[str],
    reports: list[str],
) -> dict[str, Any]:
    grant = inspect_integration_grant(root, grant_id)
    if grant is None:
        return {"ok": False, "error": "integration_transition_grant_not_found"}
    session_id = str((runtime.get("session") or {}).get("session_id") or "")
    expected = {
        "discussion_session_id": session_id,
        "integration_id": integration_id,
        "selected_task_ids": list(task_ids),
        "selected_reports": list(reports),
        "base_branch": current_branch(root),
        "worktree": str(root.resolve()),
    }
    for field, value in expected.items():
        if grant.get(field) != value:
            return {"ok": False, "error": "integration_transition_grant_mismatch", "field": field}
    if grant.get("consumed_at"):
        return {"ok": False, "error": "integration_transition_grant_consumed"}

    pending_runtime = json.loads(json.dumps(runtime))
    pending_runtime["session"]["phase"] = "integration_pending"
    pending_runtime["session"]["expected_transition"] = {
        "kind": "auto_integrate",
        "task_id": task_ids[0],
        "report_id": reports[0] if len(reports) == 1 else "",
        "integration_id": integration_id,
    }
    evidence = _integration_transition_selection(
        root,
        config,
        pending_runtime,
        {
            "task_ids": task_ids,
            "reports": reports,
            "integration_id": integration_id,
        },
    )
    if not evidence.get("ok"):
        return evidence
    if evidence.get("outcome") != grant.get("outcome"):
        return {"ok": False, "error": "integration_transition_outcome_changed"}
    return {"ok": True, "grant": grant, "evidence": evidence}


def session_main(args: argparse.Namespace) -> int:
    root = find_git_root(Path.cwd())
    if root is None:
        payload = {"ok": False, "error": "git_repository_required"}
    elif args.session_action == "get":
        runtime = read_session_runtime(root, args.session_id)
        payload = (
            {"ok": True, "runtime": runtime}
            if runtime is not None
            else {"ok": False, "error": "session_runtime_not_found"}
        )
    elif args.session_action == "transition":
        config = load_config(root)
        if config is None:
            payload = {"ok": False, "error": "wishgraph_not_enabled"}
        else:
            try:
                data = (
                    json.loads(args.data_json)
                    if args.data_json
                    else json.load(sys.stdin)
                )
            except (OSError, json.JSONDecodeError) as exc:
                payload = {"ok": False, "error": "invalid_transition_event", "detail": str(exc)}
            else:
                if not isinstance(data, dict):
                    payload = {"ok": False, "error": "transition_event_must_be_object"}
                else:
                    payload = transition_session_runtime(
                        root, config, args.session_id, args.event_kind, data
                    )
    elif args.session_action == "apply":
        try:
            patch = json.load(sys.stdin)
        except (OSError, json.JSONDecodeError) as exc:
            payload = {
                "ok": False,
                "error": "invalid_session_runtime_patch",
                "detail": str(exc),
            }
        else:
            invalid = sorted(set(patch) - SESSION_DIAGNOSTIC_PATCH_KEYS) if isinstance(patch, dict) else []
            if not isinstance(patch, dict) or invalid:
                payload = {
                    "ok": False,
                    "error": "session_direct_authority_write_forbidden",
                    "forbidden_fields": invalid,
                }
            else:
                payload = apply_session_runtime_patch(root, args.session_id, patch)
    else:
        payload = {
            "ok": False,
            "error": "session_direct_authority_write_forbidden",
            "message": "Use session transition; role and phase cannot be set directly.",
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


def integration_lease_main(args: argparse.Namespace) -> int:
    root = find_git_root(Path.cwd())
    if root is None:
        payload = {"ok": False, "error": "git_repository_required"}
    elif args.lease_action == "inspect":
        payload = {"ok": True, "lease": inspect_integration_lease(root)}
    elif args.lease_action == "acquire":
        config = load_config(root)
        runtime = read_session_runtime(root, args.session_id)
        session = runtime.get("session", {}) if isinstance(runtime, dict) else {}
        integration_runtime = (
            runtime.get("integration_runtime", {}) if isinstance(runtime, dict) else {}
        )
        if config is None:
            payload = {"ok": False, "error": "wishgraph_not_enabled"}
        elif not _verified_discussion_runtime(runtime, args.session_id):
            payload = {"ok": False, "error": "verified_discussion_session_required"}
        elif session.get("phase") != "integrating":
            payload = {"ok": False, "error": "integration_phase_required"}
        elif not isinstance(integration_runtime, dict) or integration_runtime.get(
            "transition_grant_id"
        ) != args.grant_id:
            payload = {"ok": False, "error": "integration_transition_grant_not_bound"}
        else:
            evidence = _validate_integration_grant_evidence(
                root,
                config,
                runtime,
                args.grant_id,
                args.integration_id,
                args.task_id,
                args.report,
            )
            if not evidence.get("ok"):
                payload = evidence
            else:
                payload = acquire_integration_lease(
                    root,
                    session_id=args.session_id,
                    grant_id=args.grant_id,
                    integration_id=args.integration_id,
                    task_ids=args.task_id,
                    reports=args.report,
                    require_clean=not args.allow_dirty,
                )
            if payload.get("ok"):
                persisted = apply_session_runtime_patch(
                    root,
                    args.session_id,
                    {
                        "integration_runtime": {
                            "lease_id": payload["lease"]["lease_id"],
                            "integration_id": args.integration_id,
                            "base_branch": payload["lease"]["base_branch"],
                            "worktree": payload["lease"]["worktree"],
                            "selected_task_ids": list(args.task_id),
                            "selected_reports": list(args.report),
                        }
                    },
                )
                if not persisted.get("ok"):
                    update_integration_lease(
                        root,
                        "revoke",
                        session_id=args.session_id,
                    )
                    payload = {
                        "ok": False,
                        "error": "integration_runtime_persistence_failed",
                        "detail": persisted,
                    }
    else:
        payload = update_integration_lease(
            root,
            args.lease_action,
            session_id=args.session_id,
            branch=(
                current_branch(root)
                if args.lease_action != "revoke" or args.enforce_binding
                else None
            ),
            worktree=(
                str(root)
                if args.lease_action != "revoke" or args.enforce_binding
                else None
            ),
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


def task_specs(root: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for pattern in configured_task_globs(config):
        for path in sorted(root.glob(pattern)):
            if path in seen or path.name.startswith(("EXAMPLE-", "NNN-")):
                continue
            seen.add(path)
            relative = path.relative_to(root).as_posix()
            content = read_version(root, relative, "worktree")
            if content is None:
                continue
            state = parse_task_state(relative, content)
            change_set = markdown_section(content, "Change Set") or markdown_section(
                content, "变更范围"
            )
            validation = markdown_section(content, "Validation") or markdown_section(
                content, "验证"
            )
            specs.append(
                {
                    "task_id": state.task_id,
                    "task_path": relative,
                    "status": state.status,
                    "parent_task_id": state.parent_task_id or None,
                    "dependencies": state.dependencies,
                    "attempt": state.attempt,
                    "execution_mode": state.execution_mode,
                    "comparison_group": state.comparison_group or None,
                    "run_report": state.run_report,
                    "worker_creation_authorized": state.worker_creation_authorized,
                    "errors": state.errors,
                    "allowed_scope": _markdown_scope_items(change_set),
                    "validation_plan": _markdown_list_items(validation),
                }
            )
    return specs


def _markdown_list_items(section: Optional[str]) -> list[str]:
    if not section:
        return []
    items: list[str] = []
    for line in section.splitlines():
        match = re.match(r"^\s*(?:[-*]|\d+[.)])\s+(.+?)\s*$", line)
        if match:
            item = re.sub(r"^\[[ xX]\]\s*", "", match.group(1).strip())
            item = item.strip().strip("`")
            if item:
                items.append(item)
    return items


def _markdown_scope_items(section: Optional[str]) -> list[str]:
    """Read list scopes and the Target column used by the standard Task table."""
    if not section:
        return []
    items = _markdown_list_items(section)
    for line in section.splitlines():
        if "|" not in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        target = cells[0].strip().strip("`")
        if (
            not target
            or target.lower() in {"target", "目标", "文件"}
            or not target.strip("-: ")
        ):
            continue
        if target not in items:
            items.append(target)
    return items


def revision_specs(root: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for path in sorted(root.glob(configured_revision_glob(config))):
        relative = path.relative_to(root).as_posix()
        content = read_version(root, relative, "worktree")
        if content is None:
            continue
        state = parse_revision_state(relative, content)
        specs.append(
            {
                "revision_id": state.revision_id,
                "parent_task_id": state.parent_task_id,
                "revision_path": relative,
                "status": state.status,
                "user_request": state.user_request,
                "allowed_scope": state.allowed_scope,
                "validation_plan": state.validation_plan,
                "run_report": state.run_report,
                "errors": state.errors,
            }
        )
    return specs


def resolve_revision(
    root: Path, config: dict[str, Any], revision_id: str
) -> dict[str, Any]:
    requested = canonical_revision_id(revision_id)
    if not requested:
        return {"ok": False, "error": "invalid_revision_id", "requested": revision_id}
    matches = [
        item for item in revision_specs(root, config) if item["revision_id"] == requested
    ]
    if len(matches) > 1:
        return {"ok": False, "error": "duplicate_revision_id", "matches": matches}
    if not matches:
        return {"ok": False, "error": "revision_not_found", "revision_id": requested}
    parent = resolve_task(root, config, matches[0]["parent_task_id"])
    if not parent.get("ok"):
        return {
            "ok": False,
            "error": "revision_parent_task_not_found",
            "revision_id": requested,
            "parent_task_id": matches[0]["parent_task_id"],
        }
    return {"ok": True, "revision": matches[0]}


def next_revision_id(
    root: Path, config: dict[str, Any], parent_task_id: str
) -> dict[str, Any]:
    parent = canonical_task_id(parent_task_id)
    if not parent:
        return {"ok": False, "error": "invalid_task_id", "requested": parent_task_id}
    if not resolve_task(root, config, parent).get("ok"):
        return {"ok": False, "error": "task_not_found", "task_id": parent}
    existing = [
        item
        for item in revision_specs(root, config)
        if item["revision_id"] and item["parent_task_id"] == parent
    ]
    open_revisions = [
        item for item in existing if item["status"] in {"pending", "running"}
    ]
    if len(open_revisions) == 1:
        return {
            "ok": True,
            "parent_task_id": parent,
            "revision_id": open_revisions[0]["revision_id"],
            "reuse_open_revision": True,
            "revision": open_revisions[0],
        }
    if len(open_revisions) > 1:
        return {
            "ok": False,
            "error": "multiple_open_revisions_require_repair",
            "parent_task_id": parent,
            "revision_ids": [item["revision_id"] for item in open_revisions],
        }
    numbers = [
        revision_id_parts(item["revision_id"])[1]
        for item in existing
    ]
    next_id = f"{parent}-r{max(numbers, default=0) + 1}"
    return {
        "ok": True,
        "parent_task_id": parent,
        "revision_id": next_id,
        "reuse_open_revision": False,
    }


def resolve_task(root: Path, config: dict[str, Any], task_id: str) -> dict[str, Any]:
    requested = canonical_task_id(task_id)
    if not requested:
        return {"ok": False, "error": "invalid_task_id", "requested": task_id}
    specs = task_specs(root, config)
    matches = [item for item in specs if item["task_id"] == requested]
    if len(matches) > 1:
        return {
            "ok": False,
            "error": "duplicate_task_id",
            "task_id": requested,
            "matches": [item["task_path"] for item in matches],
        }
    if not matches:
        valid_ids = sorted({item["task_id"] for item in specs if item["task_id"]})
        return {
            "ok": False,
            "error": "task_not_found",
            "task_id": requested,
            "nearest_task_ids": difflib.get_close_matches(requested, valid_ids, n=5),
        }
    return {"ok": True, "task": matches[0]}


def task_main(action: str, value: str) -> int:
    root = find_git_root(Path.cwd())
    if root is None:
        print(json.dumps({"ok": False, "error": "git_repository_required"}))
        return 2
    try:
        config = load_config(root)
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": "invalid_config", "detail": str(exc)}))
        return 2
    if config is None:
        print(json.dumps({"ok": False, "error": "wishgraph_not_installed"}))
        return 2

    if action == "route":
        command = parse_task_command(value)
        if command is None:
            print(json.dumps({"ok": False, "error": "unrecognized_task_command"}))
            return 1
        if command["action"] == "family":
            action = "family"
            value = command["task_id"]
        else:
            payload = resolve_task(root, config, command["task_id"])
            payload["command"] = command
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0 if payload["ok"] else 1

    if action == "family":
        task_id = canonical_task_id(value)
        if not task_id:
            payload = {"ok": False, "error": "invalid_task_id", "requested": value}
        else:
            number, _ = task_id_parts(task_id)
            matches = [
                item
                for item in task_specs(root, config)
                if item["task_id"] and task_id_parts(item["task_id"])[0] == number
            ]
            payload = {"ok": True, "root_task_id": number, "tasks": matches}
    else:
        payload = resolve_task(root, config, value)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


def revision_main(action: str, value: str, host: str) -> int:
    root = find_git_root(Path.cwd())
    if root is None:
        payload = {"ok": False, "error": "git_repository_required"}
    else:
        try:
            config = load_config(root)
        except ValueError as exc:
            payload = {"ok": False, "error": "invalid_config", "detail": str(exc)}
        else:
            if config is None:
                payload = {"ok": False, "error": "wishgraph_not_installed"}
            elif action == "next":
                payload = next_revision_id(root, config, value)
            else:
                payload = resolve_revision(root, config, value)
                if action == "route" and payload.get("ok"):
                    revision = payload["revision"]
                    busy_worker_refs = {
                        str(claim.get("host_thread_ref"))
                        for claim in inspect_claims(root)
                        if claim.get("effective_lease_status") == "active"
                        and claim.get("agent_platform", "unknown")
                        in {"", "unknown", host}
                        and claim.get("host_thread_ref")
                    }
                    previous = sorted(
                        (
                            claim
                            for claim in inspect_claims(
                                root, revision["parent_task_id"]
                            )
                            if claim.get("lease_status") == "released"
                            and claim.get("agent_platform") == host
                            and claim.get("host_thread_ref")
                            and str(claim.get("host_thread_ref"))
                            not in busy_worker_refs
                        ),
                        key=lambda claim: str(claim.get("updated_at") or ""),
                        reverse=True,
                    )
                    if host == "codex" and previous:
                        payload["host_action"] = {
                            "action": "send_to_existing_worker",
                            "target_worker_id": previous[0]["host_thread_ref"],
                            "revision": revision,
                        }
                    elif host == "codex":
                        payload["host_action"] = {
                            "action": "launch_codex_revision_worker",
                            "revision": revision,
                        }
                    else:
                        payload["host_action"] = {
                            "action": "show_manual_worker_command",
                            "user_message": (
                                f"在任务 {revision['parent_task_id']} 的执行窗口"
                                f"执行修订 {revision['revision_id']}"
                            ),
                            "stop_after_action": True,
                        }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


def competitive_plan_main(task_id: str, candidate_count: int) -> int:
    root = find_git_root(Path.cwd())
    if root is None:
        payload = {"ok": False, "error": "git_repository_required"}
    else:
        try:
            config = load_config(root)
        except ValueError as exc:
            payload = {"ok": False, "error": "invalid_config", "detail": str(exc)}
        else:
            resolved = resolve_task(root, config, task_id) if config else {
                "ok": False,
                "error": "wishgraph_not_installed",
            }
            if not resolved["ok"]:
                payload = resolved
            else:
                number, suffix = task_id_parts(task_id)
                if suffix:
                    payload = {"ok": False, "error": "competitive_root_must_be_numeric"}
                else:
                    used = {
                        item["task_id"]
                        for item in task_specs(root, config)
                        if item["task_id"]
                    }
                    candidates = []
                    for candidate_id in competitive_candidate_ids(
                        number, used, candidate_count
                    ):
                        candidates.append(
                            {
                                "task_id": candidate_id,
                                "parent_task_id": number,
                                "dependencies": [],
                                "execution_mode": "competitive",
                                "comparison_group": number,
                                "attempt": 1,
                                "run_report": f"reports/runs/{candidate_id}-attempt-1.md",
                            }
                        )
                    payload = {
                        "ok": True,
                        "authorization": "explicit_competitive_user_command",
                        "comparison_group": number,
                        "candidates": candidates,
                        "rules": {
                            "separate_claims": True,
                            "separate_worktrees": True,
                            "integrate_exactly_one_winner": True,
                        },
                    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


def execution_preflight(
    root: Path, config: dict[str, Any], task_id: str, authorization_action: str
) -> dict[str, Any]:
    resolved = resolve_task(root, config, task_id)
    if not resolved["ok"]:
        return resolved
    task = resolved["task"]
    _, errors = evaluate_execution_preflight(
        root, config, task["task_path"], authorization_action
    )
    if task.get("worker_creation_authorized") is not True:
        errors.append("worker_creation_authorized_must_be_true")
    return {"ok": not errors, "task": task, "errors": errors}


def _record_worker_claim_failure(
    root: Path,
    session_id: str,
    discussion_session_id: str,
    task_id: str,
    reason: str,
) -> None:
    """Persist a recoverable terminal preflight state without claiming execution."""
    patch = {
        "worker_runtime": {
            "claim_id": "",
            "active_task_id": task_id,
            "binding_status": "claim_failed",
            "worker_availability": "blocked",
            "sync_status": "manual_intervention_required",
            "recovery_reason": reason,
            "last_observed_at": _utc_now(),
            "worker_handle": {
                "claim_id": "",
                "terminal_state": "claim_failed",
                "last_observed_at": _utc_now(),
            },
        }
    }
    if session_id:
        apply_session_runtime_patch(root, session_id, patch)
    if discussion_session_id and discussion_session_id != session_id:
        apply_session_runtime_patch(root, discussion_session_id, patch)


def claim_main(args: argparse.Namespace) -> int:
    root = find_git_root(Path.cwd())
    if root is None:
        payload = {"ok": False, "error": "git_repository_required"}
    elif args.claim_action == "inspect":
        task_id = canonical_task_id(args.task_id) if args.task_id else None
        if args.task_id and not task_id:
            payload = {"ok": False, "error": "invalid_task_id"}
        else:
            payload = {
                "ok": True,
                "claims": inspect_claims(root, task_id, args.stale_after),
            }
    elif args.claim_action in {"heartbeat", "release", "revoke"}:
        if args.claim_action == "revoke" and not args.authorized_by_user:
            payload = {"ok": False, "error": "explicit_user_authorization_required"}
        else:
            enforce_binding = args.claim_action != "revoke"
            terminal_config: Optional[dict[str, Any]] = None
            terminal_preflight = {"ok": True}
            if args.claim_action == "release":
                matches = [
                    claim
                    for claim in inspect_claims(root)
                    if claim.get("claim_id") == args.claim_id
                ]
                if len(matches) != 1:
                    terminal_preflight = {"ok": False, "error": "claim_not_found"}
                else:
                    try:
                        terminal_config = load_config(root)
                    except ValueError as exc:
                        terminal_preflight = {
                            "ok": False,
                            "error": "invalid_config",
                            "detail": str(exc),
                        }
                    else:
                        terminal_preflight = (
                            enqueue_terminal_notification_from_claim(
                                root,
                                terminal_config,
                                matches[0],
                                dry_run=True,
                            )
                            if terminal_config is not None
                            else {"ok": False, "error": "wishgraph_not_installed"}
                        )
            if not terminal_preflight.get("ok"):
                payload = {
                    "ok": False,
                    "error": "terminal_notification_preflight_failed",
                    "detail": terminal_preflight,
                }
            else:
                payload = update_claim(
                    root,
                    args.claim_id,
                    args.claim_action,
                    branch=current_branch(root) if enforce_binding else None,
                    worktree=str(root) if enforce_binding else None,
                )
            if payload.get("ok") and args.claim_action == "release":
                released_claim = payload.get("claim", {})
                persisted = {"ok": True}
                if args.session_id:
                    persisted = apply_session_runtime_patch(
                        root,
                        args.session_id,
                        {
                            "worker_runtime": {
                                "claim_id": "",
                                "previous_task_id": released_claim.get("task_id", ""),
                                "previous_claim_id": released_claim.get("claim_id", ""),
                                "active_task_id": "",
                                "active_revision_id": "",
                                "worker_availability": "idle",
                                "binding_status": "released",
                                "allowed_scope": [],
                                "validation_plan": [],
                                "execution_ownership": "",
                                "worker_handle": {
                                    "claim_id": "",
                                    "terminal_state": str(
                                        released_claim.get("terminal_event")
                                        or "released"
                                    ),
                                    "last_observed_at": _utc_now(),
                                },
                            }
                        },
                    )
                notification = enqueue_terminal_notification_from_claim(
                    root, terminal_config, released_claim
                )
                payload["notification"] = notification
                if not persisted.get("ok") or not notification.get("ok"):
                    payload = {
                        "ok": False,
                        "error": "claim_released_but_closeout_signal_failed",
                        "claim": released_claim,
                        "runtime": persisted,
                        "notification": notification,
                    }
    elif args.claim_action == "rebind":
        try:
            config = load_config(root)
        except ValueError as exc:
            payload = {"ok": False, "error": "invalid_config", "detail": str(exc)}
        else:
            if config is None:
                payload = {"ok": False, "error": "wishgraph_not_installed"}
            elif not current_host_execution_guard(root, config, args.host).get("ok"):
                payload = current_host_execution_guard(root, config, args.host)
            elif args.revision_id:
                resolved_revision = resolve_revision(root, config, args.revision_id)
                if not resolved_revision.get("ok"):
                    payload = resolved_revision
                else:
                    revision = resolved_revision["revision"]
                    payload = rebind_worker_claim(
                        root,
                        session_id=args.session_id,
                        old_claim_id=args.old_claim_id,
                        old_task_status=args.old_task_status,
                        next_task_id=revision["parent_task_id"],
                        revision_id=revision["revision_id"],
                        attempt=args.attempt,
                        worker_id=args.worker_id,
                        host_thread_ref=args.host_thread_ref or args.session_id,
                        agent_platform=args.host,
                        container_kind=args.container_kind,
                        agent_kind=args.agent_kind,
                        allowed_scope=revision["allowed_scope"],
                        validation_plan=revision["validation_plan"],
                        require_clean=not args.allow_dirty,
                    )
            else:
                resolved = resolve_task(root, config, args.next_task_id)
                if not resolved.get("ok"):
                    payload = resolved
                else:
                    task = resolved["task"]
                    payload = rebind_worker_claim(
                        root,
                        session_id=args.session_id,
                        old_claim_id=args.old_claim_id,
                        old_task_status=args.old_task_status,
                        next_task_id=task["task_id"],
                        attempt=task["attempt"],
                        worker_id=args.worker_id,
                        host_thread_ref=args.host_thread_ref or args.session_id,
                        agent_platform=args.host,
                        container_kind=args.container_kind,
                        agent_kind=args.agent_kind,
                        allowed_scope=task["allowed_scope"],
                        validation_plan=task["validation_plan"],
                        require_clean=not args.allow_dirty,
                    )
    else:
        try:
            config = load_config(root)
        except ValueError as exc:
            payload = {"ok": False, "error": "invalid_config", "detail": str(exc)}
        else:
            if config is None:
                payload = {"ok": False, "error": "wishgraph_not_installed"}
            else:
                host_guard = current_host_execution_guard(root, config, args.host)
                if not host_guard.get("ok"):
                    print(json.dumps(host_guard, ensure_ascii=False, indent=2))
                    return 1
                if args.revision_id:
                    resolved_revision = resolve_revision(root, config, args.revision_id)
                    if not resolved_revision.get("ok"):
                        preflight = resolved_revision
                    else:
                        revision = resolved_revision["revision"]
                        preflight = {
                            "ok": not revision["errors"]
                            and revision["status"] in {"pending", "running", "blocked"},
                            "task": {
                                "task_id": revision["parent_task_id"],
                                "attempt": args.attempt,
                                "execution_mode": "exclusive",
                                "run_report": revision["run_report"],
                                "allowed_scope": revision["allowed_scope"],
                                "validation_plan": revision["validation_plan"],
                            },
                            "revision": revision,
                            "errors": revision["errors"],
                        }
                else:
                    preflight = execution_preflight(
                        root, config, args.task_id, args.authorization_action
                    )
                if not preflight["ok"]:
                    payload = {
                        "ok": False,
                        "error": "execution_preflight_failed",
                        **preflight,
                    }
                else:
                    task = preflight["task"]
                    existing_runtime = (
                        read_session_runtime(root, args.session_id)
                        if args.session_id
                        else None
                    ) or {}
                    launch_context = (
                        existing_runtime.get("launch_context")
                        if isinstance(existing_runtime.get("launch_context"), dict)
                        else {}
                    )
                    existing_worker_runtime = (
                        existing_runtime.get("worker_runtime")
                        if isinstance(existing_runtime.get("worker_runtime"), dict)
                        else {}
                    )
                    discussion_session_id = str(
                        args.discussion_session_id
                        or launch_context.get("discussion_session_id")
                        or existing_worker_runtime.get("discussion_session_id")
                        or ""
                    )
                    launch_context_error = ""
                    if args.container_kind != MANUAL_WORKER_WINDOW:
                        expected_thread_id = str(
                            launch_context.get("thread_or_session_id") or ""
                        )
                        expected_discussion_id = str(
                            launch_context.get("discussion_session_id") or ""
                        )
                        expected_worktree = str(launch_context.get("worktree") or "")
                        expected_branch = str(launch_context.get("branch") or "")
                        actual_thread_ids = {
                            str(args.worker_id or ""),
                            str(args.session_id or ""),
                            str(args.host_thread_ref or ""),
                        }
                        if launch_context.get("agent_kind") != "formal_worker":
                            launch_context_error = "formal_worker_launch_context_required"
                        elif launch_context.get("container_kind") != args.container_kind:
                            launch_context_error = "worker_container_kind_mismatch"
                        elif launch_context.get("task_id") != task["task_id"]:
                            launch_context_error = "worker_launch_task_mismatch"
                        elif (
                            not expected_thread_id
                            or "" in actual_thread_ids
                            or actual_thread_ids != {expected_thread_id}
                        ):
                            launch_context_error = "worker_thread_id_binding_mismatch"
                        elif (
                            not expected_discussion_id
                            or discussion_session_id != expected_discussion_id
                        ):
                            launch_context_error = "worker_discussion_binding_mismatch"
                        elif (
                            not expected_worktree
                            or str(root.resolve())
                            != str(Path(expected_worktree).expanduser().resolve())
                        ):
                            launch_context_error = "worker_worktree_binding_mismatch"
                        elif not expected_branch or current_branch(root) != expected_branch:
                            launch_context_error = "worker_branch_binding_mismatch"
                        elif (
                            args.container_kind == CLAUDE_BACKGROUND_CONTAINER
                            and args.host != "claude"
                        ):
                            launch_context_error = "worker_host_binding_mismatch"
                        elif launch_context.get("inspectable") is not True:
                            launch_context_error = "worker_thread_not_inspectable"
                        elif launch_context.get("controllable") is not True:
                            launch_context_error = "worker_thread_not_controllable"
                        elif launch_context.get("independent_context") is not True:
                            launch_context_error = "worker_context_not_independent"
                    if launch_context_error:
                        payload = {"ok": False, "error": launch_context_error}
                    else:
                        payload = acquire_claim(
                            root,
                            task["task_id"],
                            task["attempt"],
                            args.worker_id,
                            execution_mode=(
                                "competitive"
                                if task["execution_mode"] == "competitive"
                                else "exclusive"
                            ),
                            host_thread_ref=args.host_thread_ref or args.session_id,
                            agent_platform=args.host,
                            revision_id=(args.revision_id or None),
                            allowed_scope=task.get("allowed_scope", []),
                            validation_plan=task.get("validation_plan", []),
                            discussion_session_id=discussion_session_id or None,
                            container_kind=args.container_kind,
                            agent_kind=args.agent_kind,
                            stale_after_seconds=args.stale_after,
                        )
                    if (
                        args.container_kind != MANUAL_WORKER_WINDOW
                        and not payload.get("ok")
                    ):
                        _record_worker_claim_failure(
                            root,
                            str(args.session_id or ""),
                            discussion_session_id,
                            task["task_id"],
                            str(payload.get("error") or "worker_claim_acquire_failed"),
                        )
                    if payload.get("ok"):
                        payload["task"] = task
                        if args.session_id:
                            runtime_payload = apply_session_runtime_patch(
                                root,
                                args.session_id,
                                {
                                    "session": {
                                        "session_id": args.session_id,
                                        "role": "worker",
                                        "host": args.host,
                                        "phase": "waiting_for_worker",
                                        "expected_transition": {
                                            "kind": "wait_for_worker",
                                            "task_id": task["task_id"],
                                        },
                                    },
                                    "task": {
                                        "task_id": task["task_id"],
                                        "lifecycle": "running",
                                        "worker_authorized": True,
                                        "run_report": task["run_report"],
                                    },
                                    "worker_runtime": {
                                        "claim_id": payload["claim"]["claim_id"],
                                        "branch": payload["claim"]["branch"],
                                        "worktree": payload["claim"]["worktree"],
                                        "host_window_or_thread_id": (
                                            args.host_thread_ref or args.session_id
                                        ),
                                        "active_task_id": task["task_id"],
                                        "active_revision_id": args.revision_id or "",
                                        "worker_session_id": args.session_id,
                                        "discussion_session_id": discussion_session_id,
                                        "worker_availability": "busy",
                                        "binding_status": "active",
                                        "allowed_scope": task.get("allowed_scope", []),
                                        "validation_plan": task.get(
                                            "validation_plan", []
                                        ),
                                        "execution_ownership": "worker_claim",
                                        "worker_handle": {
                                            "host": args.host,
                                            "container_kind": args.container_kind,
                                            "thread_or_session_id": (
                                                args.host_thread_ref
                                                or args.session_id
                                                or args.worker_id
                                            ),
                                            "parent_discussion_id": discussion_session_id,
                                            "task_id": task["task_id"],
                                            "claim_id": payload["claim"]["claim_id"],
                                            "branch": payload["claim"]["branch"],
                                            "worktree": payload["claim"]["worktree"],
                                            "inspectable": (
                                                args.container_kind
                                                in FORMAL_WORKER_CONTAINERS
                                            ),
                                            "controllable": (
                                                args.container_kind
                                                in FORMAL_WORKER_CONTAINERS
                                            ),
                                            "terminal_state": "running",
                                            "last_observed_at": _utc_now(),
                                        },
                                    },
                                },
                            )
                            if not runtime_payload.get("ok"):
                                update_claim(
                                    root,
                                    payload["claim"]["claim_id"],
                                    "revoke",
                                )
                                payload = {
                                    "ok": False,
                                    "error": "worker_runtime_persistence_failed",
                                    "detail": runtime_payload,
                                }
                                if args.container_kind != MANUAL_WORKER_WINDOW:
                                    _record_worker_claim_failure(
                                        root,
                                        str(args.session_id or ""),
                                        discussion_session_id,
                                        task["task_id"],
                                        "worker_runtime_persistence_failed",
                                    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


def codex_worker_main(args: argparse.Namespace) -> int:
    return _codex_worker_provider().codex_worker_main(
        args,
        find_git_root_fn=find_git_root,
        load_config_fn=load_config,
        authorize_launch=_authorize_codex_execution_thread_launch,
        resolve_task_record=resolve_task,
    )


def claude_worker_main(args: argparse.Namespace) -> int:
    root = find_git_root(Path.cwd())
    if root is None:
        print(json.dumps({"ok": False, "error": "git_repository_required"}))
        return 2
    if args.claude_worker_action == "capability":
        capability = detect_claude_worker_capability(root, args.claude_executable)
        print(json.dumps({"ok": True, **capability.as_dict()}, ensure_ascii=False, indent=2))
        return 0
    try:
        config = load_config(root)
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": "invalid_config", "detail": str(exc)}))
        return 2
    if config is None or config.get("mode") == "off":
        print(json.dumps({"ok": False, "error": "wishgraph_not_active"}))
        return 2
    if args.claude_worker_action == "launch":
        payload = launch_claude_worker(
            root,
            config,
            args.task_id,
            args.discussion_session_id,
            claude_executable=args.claude_executable,
        )
        if payload.get("fallback"):
            print(payload["user_message"])
            return 0
    else:
        payload = refresh_claude_worker(
            root,
            config,
            args.discussion_session_id,
            claude_executable=args.claude_executable,
            include_logs=args.include_logs,
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "codex-worker":
        return _codex_worker_provider().main(
            sys.argv[2:],
            find_git_root_fn=find_git_root,
            load_config_fn=load_config,
            authorize_launch=_authorize_codex_execution_thread_launch,
            resolve_task_record=resolve_task,
        )
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for event in (
        "session-start",
        "user-prompt-submit",
        "pre-tool-use",
        "stop",
        "task-completed",
    ):
        event_parser = subparsers.add_parser(event)
        event_parser.add_argument(
            "--host", choices=("codex", "claude", "unknown"), default="unknown"
        )
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--scope", choices=("worktree", "staged"), default="worktree")
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--full", action="store_true")
    status_parser.add_argument("--task")
    integration_plan_parser = subparsers.add_parser("integration-plan")
    integration_plan_parser.add_argument(
        "--host-capability",
        choices=("background", "active_agent", "inactive"),
        required=True,
    )
    flow_parser = subparsers.add_parser("flow-plan")
    flow_parser.add_argument("--host", choices=("codex", "claude", "unknown"), required=True)
    flow_parser.add_argument("--can-spawn-execution-thread", action="store_true")
    flow_parser.add_argument("--can-inspect-execution-thread", action="store_true")
    flow_parser.add_argument("--can-bind-thread-id", action="store_true")
    flow_parser.add_argument("--can-stop-or-steer-thread", action="store_true")
    flow_parser.add_argument("--can-isolate-worktree", action="store_true")
    flow_parser.add_argument("--can-observe-terminal-result", action="store_true")
    flow_parser.add_argument("--can-gate-reads", action="store_true")
    flow_parser.add_argument("--can-deliver-result-to-discussion", action="store_true")
    claude_worker_parser = subparsers.add_parser("claude-worker")
    claude_worker_subparsers = claude_worker_parser.add_subparsers(
        dest="claude_worker_action", required=True
    )
    claude_capability_parser = claude_worker_subparsers.add_parser("capability")
    claude_capability_parser.add_argument("--claude-executable", default="claude")
    claude_launch_parser = claude_worker_subparsers.add_parser("launch")
    claude_launch_parser.add_argument("task_id")
    claude_launch_parser.add_argument("--discussion-session-id", required=True)
    claude_launch_parser.add_argument("--claude-executable", default="claude")
    claude_refresh_parser = claude_worker_subparsers.add_parser("refresh")
    claude_refresh_parser.add_argument("--discussion-session-id", required=True)
    claude_refresh_parser.add_argument("--claude-executable", default="claude")
    claude_refresh_parser.add_argument("--include-logs", action="store_true")
    session_parser = subparsers.add_parser("session")
    session_subparsers = session_parser.add_subparsers(
        dest="session_action", required=True
    )
    session_get_parser = session_subparsers.add_parser("get")
    session_get_parser.add_argument("session_id")
    session_apply_parser = session_subparsers.add_parser("apply")
    session_apply_parser.add_argument("session_id")
    session_transition_parser = session_subparsers.add_parser("transition")
    session_transition_parser.add_argument("session_id")
    session_transition_parser.add_argument(
        "event_kind", choices=sorted(DISCUSSION_TRANSITION_EVENTS)
    )
    session_transition_parser.add_argument("--data-json", default="")
    session_set_parser = session_subparsers.add_parser("set")
    session_set_parser.add_argument("session_id")
    session_set_parser.add_argument("--role", choices=sorted(SESSION_ROLES), required=True)
    session_set_parser.add_argument("--host", choices=("codex", "claude", "unknown"), default="unknown")
    session_set_parser.add_argument("--phase", choices=sorted(FLOW_PHASES), required=True)
    session_set_parser.add_argument("--expected-kind", choices=sorted(EXPECTED_TRANSITIONS))
    session_set_parser.add_argument("--task-id", default="")
    session_set_parser.add_argument("--task-lifecycle", default="draft")
    session_set_parser.add_argument("--worker-authorized", action="store_true")
    session_set_parser.add_argument("--report-id", default="")
    session_set_parser.add_argument("--decision-id", default="")
    session_set_parser.add_argument("--integration-id", default="")
    lease_parser = subparsers.add_parser("integration-lease")
    lease_subparsers = lease_parser.add_subparsers(dest="lease_action", required=True)
    lease_subparsers.add_parser("inspect")
    lease_acquire = lease_subparsers.add_parser("acquire")
    lease_acquire.add_argument("--session-id", required=True)
    lease_acquire.add_argument("--grant-id", required=True)
    lease_acquire.add_argument("--integration-id", required=True)
    lease_acquire.add_argument("--task-id", action="append", required=True)
    lease_acquire.add_argument("--report", action="append", required=True)
    lease_acquire.add_argument("--allow-dirty", action="store_true")
    for lease_action in ("heartbeat", "release", "revoke"):
        lease_action_parser = lease_subparsers.add_parser(lease_action)
        lease_action_parser.add_argument("--session-id", required=True)
        lease_action_parser.add_argument("--enforce-binding", action="store_true")
    competitive_parser = subparsers.add_parser("competitive-plan")
    competitive_parser.add_argument("task_id")
    competitive_parser.add_argument("--candidates", type=int, default=2, choices=range(2, 9))
    task_parser = subparsers.add_parser("task")
    task_parser.add_argument("action", choices=("resolve", "family", "route"))
    task_parser.add_argument("value")
    revision_parser = subparsers.add_parser("revision")
    revision_parser.add_argument("action", choices=("resolve", "next", "route"))
    revision_parser.add_argument("value")
    revision_parser.add_argument(
        "--host", choices=("codex", "claude", "unknown"), default="unknown"
    )
    claim_parser = subparsers.add_parser("claim")
    claim_subparsers = claim_parser.add_subparsers(dest="claim_action", required=True)
    acquire_parser = claim_subparsers.add_parser("acquire")
    acquire_parser.add_argument("task_id", nargs="?", default="")
    acquire_parser.add_argument("--worker-id", required=True)
    acquire_parser.add_argument("--revision-id")
    acquire_parser.add_argument("--attempt", type=int, default=1)
    acquire_parser.add_argument("--session-id")
    acquire_parser.add_argument("--discussion-session-id")
    acquire_parser.add_argument(
        "--host", choices=("codex", "claude", "unknown"), default="unknown"
    )
    acquire_parser.add_argument(
        "--authorization-action",
        choices=("execute", "continue", "retry", "take_over"),
        default="execute",
    )
    acquire_parser.add_argument("--host-thread-ref")
    acquire_parser.add_argument(
        "--container-kind",
        choices=tuple(sorted(FORMAL_WORKER_CONTAINERS | NON_WORKER_CONTAINERS)),
        default=MANUAL_WORKER_WINDOW,
    )
    acquire_parser.add_argument(
        "--agent-kind",
        choices=("formal_worker", "helper", "hidden_internal"),
        default="formal_worker",
    )
    acquire_parser.add_argument("--stale-after", type=int, default=3600)
    inspect_parser = claim_subparsers.add_parser("inspect")
    inspect_parser.add_argument("task_id", nargs="?")
    inspect_parser.add_argument("--stale-after", type=int, default=3600)
    rebind_parser = claim_subparsers.add_parser("rebind")
    rebind_parser.add_argument("--session-id", required=True)
    rebind_parser.add_argument("--old-claim-id", required=True)
    rebind_parser.add_argument(
        "--old-task-status",
        choices=(
            "completed",
            "blocked",
            "incomplete",
            "stopped",
            "abandoned",
            "integrated",
            "reviewed",
        ),
        required=True,
    )
    rebind_parser.add_argument("--next-task-id", default="")
    rebind_parser.add_argument("--revision-id")
    rebind_parser.add_argument("--attempt", type=int, default=1)
    rebind_parser.add_argument("--worker-id", required=True)
    rebind_parser.add_argument("--host-thread-ref")
    rebind_parser.add_argument(
        "--container-kind",
        choices=tuple(sorted(FORMAL_WORKER_CONTAINERS | NON_WORKER_CONTAINERS)),
        default=MANUAL_WORKER_WINDOW,
    )
    rebind_parser.add_argument(
        "--agent-kind",
        choices=("formal_worker", "helper", "hidden_internal"),
        default="formal_worker",
    )
    rebind_parser.add_argument(
        "--host", choices=("codex", "claude", "unknown"), default="unknown"
    )
    rebind_parser.add_argument("--allow-dirty", action="store_true")
    for claim_action in ("heartbeat", "release", "revoke"):
        parser_for_action = claim_subparsers.add_parser(claim_action)
        parser_for_action.add_argument("claim_id")
        parser_for_action.add_argument("--session-id")
        if claim_action == "revoke":
            parser_for_action.add_argument("--authorized-by-user", action="store_true")
    subparsers.add_parser("git-pre-commit")
    args = parser.parse_args()

    if args.command == "check":
        return check_main(args.scope)
    if args.command == "status":
        return status_main("full" if args.full else "active", args.task)
    if args.command == "integration-plan":
        return integration_plan_main(args.host_capability)
    if args.command == "flow-plan":
        return flow_plan_main(args)
    if args.command == "claude-worker":
        return claude_worker_main(args)
    if args.command == "session":
        return session_main(args)
    if args.command == "integration-lease":
        return integration_lease_main(args)
    if args.command == "competitive-plan":
        return competitive_plan_main(args.task_id, args.candidates)
    if args.command == "task":
        return task_main(args.action, args.value)
    if args.command == "revision":
        return revision_main(args.action, args.value, args.host)
    if args.command == "claim":
        return claim_main(args)
    if args.command == "git-pre-commit":
        return check_main("staged")
    return hook_main(args.command, args.host)
