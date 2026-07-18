"""Private PreToolUse classification and authority gate provider."""

from __future__ import annotations

import fnmatch
import json
import re
import shlex
from pathlib import Path
from typing import Any, Callable, Optional

from git_state import (
    canonical_runtime_id,
    configured_revision_glob,
    configured_task_globs,
    current_branch,
    inspect_claims,
    inspect_integration_lease,
    load_config,
    read_session_runtime,
    read_version,
)
from policy import reduce_orchestration
from workflow_state import (
    FlowPlan,
    HostCapability,
    UserEvent,
    orchestration_state_from_dict,
    parse_revision_state,
    parse_task_state,
)

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
            return canonical_runtime_id(value)
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
    root: Path,
    payload: dict[str, Any],
    *,
    task_specs_loader: Callable[[Path, dict[str, Any]], list[dict[str, Any]]],
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
        for item in task_specs_loader(root, load_config(root) or {})
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
    execution_guard: Callable[..., dict[str, Any]],
    capability_for: Callable[[str], HostCapability],
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
    if role == "worker" and current_host in {"codex", "claude"}:
        host_guard = execution_guard(
            root,
            config,
            current_host,
            bound_claim=bool(runtime["worker_runtime"].get("claim_id")),
        )
        if not host_guard.get("ok"):
            return FlowPlan(
                accepted=False,
                next_action="deny_current_host_execution",
                denial_reason=str(host_guard.get("message") or host_guard.get("error")),
            )
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
    capability = capability_for(state.session.host)
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

def emit_orchestration_gate(
    plan: FlowPlan,
    mode: str,
    *,
    emit_output: Callable[[dict[str, Any]], None],
) -> None:
    reason = "WishGraph orchestration gate blocked this operation. " + plan.denial_reason
    if mode == "warn" and plan.next_action != "deny_current_host_execution":
        emit_output(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": reason,
                }
            }
        )
    else:
        emit_output(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
