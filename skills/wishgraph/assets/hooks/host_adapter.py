"""Host-hook, CLI, and user-facing output boundary for WishGraph."""

from __future__ import annotations

import argparse
import difflib
import fnmatch
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from git_state import (
    LEGACY_PROJECT_STATUS_PATH,
    apply_session_runtime_patch,
    acquire_claim,
    acquire_integration_lease,
    configured_task_globs,
    current_branch,
    find_git_root,
    load_config,
    inspect_claims,
    inspect_integration_lease,
    read_version,
    read_session_runtime,
    resolve_project_status_path,
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
    competitive_candidate_ids,
    dynamic_state_block,
    markdown_section,
    parse_task_command,
    parse_task_state,
    flow_plan_to_dict,
    orchestration_state_from_dict,
    task_id_parts,
)


@dataclass(frozen=True)
class HostAction:
    action: str
    state_patch: dict[str, Any] = field(default_factory=dict)
    user_message: str = ""
    stop_after_action: bool = False
    creates_visible_window: bool = False


def map_flow_plan_to_host(
    plan: FlowPlan, capability: HostCapability
) -> HostAction:
    """Map one authorized semantic plan to a host action without changing authority."""
    if plan.next_action == "launch_worker":
        if capability.can_create_visible_worker:
            return HostAction(
                action="create_visible_worker_task",
                state_patch=plan.state_patch,
                stop_after_action=True,
                creates_visible_window=True,
            )
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
            creates_visible_window=False,
        )
    if plan.next_action == "enter_discussion_local_integration":
        return HostAction(
            action="enter_discussion_local_integration",
            state_patch=plan.state_patch,
            stop_after_action=False,
            creates_visible_window=False,
        )
    return HostAction(
        action=plan.next_action,
        state_patch=plan.state_patch,
        user_message=plan.user_message,
        stop_after_action=plan.stop_after_action,
        creates_visible_window=False,
    )


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
    integration = integration_state(root, config).as_dict()
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
            "Ad-hoc work does not require a task file, but still needs a unique run report.",
        ]
    )
    return "\n".join(lines)


def format_warnings(result: CheckResult) -> str:
    return "WishGraph status warnings:\n" + "\n".join(
        f"- {warning}" for warning in result.warnings
    )


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
    r"xcodebuild|cargo\s+(?:test|build|check)|go\s+test|"
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
    for key in ("file_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            paths.append(value.strip().replace("\\", "/"))
    patch = tool_input.get("patch") or tool_input.get("input")
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
    if path.is_absolute():
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return value.replace("\\", "/")
    return value.lstrip("./")


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
    return "business_write", ""


def classify_tool_operation(
    root: Path, config: dict[str, Any], payload: dict[str, Any]
) -> Optional[tuple[str, str]]:
    tool_name = str(payload.get("tool_name") or "").lower()
    tool_input = payload.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    if tool_name == "bash":
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
            return "business_write", ""
        return None
    if tool_name in {"write", "edit", "multiedit", "notebookedit", "apply_patch"}:
        return _path_operation(root, config, _tool_paths(tool_input))
    return None


def orchestration_gate_plan(
    root: Path, config: dict[str, Any], payload: dict[str, Any]
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
    state = orchestration_state_from_dict(runtime)
    capability = HostCapability(
        host=state.session.host,
        can_create_visible_worker=state.session.host == "codex",
        can_gate_writes=True,
        can_gate_builds=True,
        can_gate_reads=config.get("read_gate_mode") == "enforce",
    )
    return reduce_orchestration(
        state,
        UserEvent(
            kind="operation_requested",
            data={
                "operation": operation,
                "operation_scope": operation_scope,
                "task_authorized": bool(task_value.get("worker_authorized")),
            },
        ),
        capability,
    )


def emit_orchestration_gate(plan: FlowPlan, mode: str) -> None:
    reason = "WishGraph orchestration gate blocked this operation. " + plan.denial_reason
    if mode == "warn":
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


def hook_main(event: str) -> int:
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

    if event == "session-start":
        session_id = hook_session_id(payload)
        if session_id and read_session_runtime(root, session_id) is None:
            write_session_runtime(
                root,
                session_id,
                {
                    "session": {
                        "session_id": session_id,
                        "role": "neutral",
                        "host": str(payload.get("host") or "unknown"),
                        "phase": "planning",
                        "expected_transition": None,
                    }
                },
            )

    if event == "pre-tool-use":
        tool_input = payload.get("tool_input")
        command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
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
        gate_plan = orchestration_gate_plan(root, config, payload)
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
    session_context = project_session_context(root, config) if event == "session-start" else None
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


def status_main() -> int:
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
    print(json.dumps(integration_state(root, config).as_dict(), ensure_ascii=False, indent=2))
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
    state = integration_state(root, config).as_dict()
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
        can_create_visible_worker=args.can_create_visible_worker,
        can_gate_writes=True,
        can_gate_builds=True,
        can_gate_reads=args.can_gate_reads,
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
                    "creates_visible_window": action.creates_visible_window,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


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
            payload = apply_session_runtime_patch(root, args.session_id, patch)
    else:
        expected = None
        if args.expected_kind:
            expected = {
                "kind": args.expected_kind,
                "task_id": args.task_id,
                "report_id": args.report_id,
                "decision_id": args.decision_id,
                "integration_id": args.integration_id,
            }
        runtime = {
            "session": {
                "session_id": args.session_id,
                "role": args.role,
                "host": args.host,
                "phase": args.phase,
                "expected_transition": expected,
            }
        }
        if args.task_id:
            runtime["task"] = {
                "task_id": args.task_id,
                "lifecycle": args.task_lifecycle,
                "worker_authorized": args.worker_authorized,
                "run_report": args.report_id,
            }
        payload = write_session_runtime(root, args.session_id, runtime)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


def integration_lease_main(args: argparse.Namespace) -> int:
    root = find_git_root(Path.cwd())
    if root is None:
        payload = {"ok": False, "error": "git_repository_required"}
    elif args.lease_action == "inspect":
        payload = {"ok": True, "lease": inspect_integration_lease(root)}
    elif args.lease_action == "acquire":
        runtime = read_session_runtime(root, args.session_id)
        session = runtime.get("session", {}) if isinstance(runtime, dict) else {}
        if not isinstance(session, dict) or session.get("role") != "discussion":
            payload = {"ok": False, "error": "discussion_session_required"}
        elif session.get("phase") != "integrating":
            payload = {"ok": False, "error": "integration_phase_required"}
        else:
            payload = acquire_integration_lease(
                root,
                session_id=args.session_id,
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
                    "errors": state.errors,
                }
            )
    return specs


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
    return {"ok": not errors, "task": task, "errors": errors}


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
            payload = update_claim(
                root,
                args.claim_id,
                args.claim_action,
                branch=current_branch(root) if enforce_binding else None,
                worktree=str(root) if enforce_binding else None,
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
                        stale_after_seconds=args.stale_after,
                    )
                    if payload.get("ok"):
                        payload["task"] = task
                        if args.session_id:
                            runtime_payload = write_session_runtime(
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
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for event in ("session-start", "pre-tool-use", "stop", "task-completed"):
        subparsers.add_parser(event)
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--scope", choices=("worktree", "staged"), default="worktree")
    subparsers.add_parser("status")
    integration_plan_parser = subparsers.add_parser("integration-plan")
    integration_plan_parser.add_argument(
        "--host-capability",
        choices=("background", "active_agent", "inactive"),
        required=True,
    )
    flow_parser = subparsers.add_parser("flow-plan")
    flow_parser.add_argument("--host", choices=("codex", "claude", "unknown"), required=True)
    flow_parser.add_argument("--can-create-visible-worker", action="store_true")
    flow_parser.add_argument("--can-gate-reads", action="store_true")
    session_parser = subparsers.add_parser("session")
    session_subparsers = session_parser.add_subparsers(
        dest="session_action", required=True
    )
    session_get_parser = session_subparsers.add_parser("get")
    session_get_parser.add_argument("session_id")
    session_apply_parser = session_subparsers.add_parser("apply")
    session_apply_parser.add_argument("session_id")
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
    claim_parser = subparsers.add_parser("claim")
    claim_subparsers = claim_parser.add_subparsers(dest="claim_action", required=True)
    acquire_parser = claim_subparsers.add_parser("acquire")
    acquire_parser.add_argument("task_id")
    acquire_parser.add_argument("--worker-id", required=True)
    acquire_parser.add_argument("--session-id")
    acquire_parser.add_argument(
        "--host", choices=("codex", "claude", "unknown"), default="unknown"
    )
    acquire_parser.add_argument(
        "--authorization-action",
        choices=("execute", "continue", "retry", "take_over"),
        default="execute",
    )
    acquire_parser.add_argument("--host-thread-ref")
    acquire_parser.add_argument("--stale-after", type=int, default=3600)
    inspect_parser = claim_subparsers.add_parser("inspect")
    inspect_parser.add_argument("task_id", nargs="?")
    inspect_parser.add_argument("--stale-after", type=int, default=3600)
    for claim_action in ("heartbeat", "release", "revoke"):
        parser_for_action = claim_subparsers.add_parser(claim_action)
        parser_for_action.add_argument("claim_id")
        if claim_action == "revoke":
            parser_for_action.add_argument("--authorized-by-user", action="store_true")
    subparsers.add_parser("git-pre-commit")
    args = parser.parse_args()

    if args.command == "check":
        return check_main(args.scope)
    if args.command == "status":
        return status_main()
    if args.command == "integration-plan":
        return integration_plan_main(args.host_capability)
    if args.command == "flow-plan":
        return flow_plan_main(args)
    if args.command == "session":
        return session_main(args)
    if args.command == "integration-lease":
        return integration_lease_main(args)
    if args.command == "competitive-plan":
        return competitive_plan_main(args.task_id, args.candidates)
    if args.command == "task":
        return task_main(args.action, args.value)
    if args.command == "claim":
        return claim_main(args)
    if args.command == "git-pre-commit":
        return check_main("staged")
    return hook_main(args.command)
