"""Host-hook, CLI, and user-facing output boundary for WishGraph."""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

from git_state import (
    LEGACY_PROJECT_STATUS_PATH,
    acquire_claim,
    configured_task_globs,
    current_branch,
    find_git_root,
    load_config,
    inspect_claims,
    read_version,
    resolve_project_status_path,
    standard_project_status_conflict,
    update_claim,
)
from policy import (
    CheckResult,
    check_sync,
    execution_preflight as evaluate_execution_preflight,
    integration_state,
)
from workflow_state import (
    canonical_task_id,
    competitive_candidate_ids,
    dynamic_state_block,
    markdown_section,
    parse_task_command,
    parse_task_state,
    task_id_parts,
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

    if event == "pre-tool-use":
        tool_input = payload.get("tool_input")
        command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
        if payload.get("tool_name") != "Bash" or not is_git_commit_command(str(command)):
            emit({})
            return 0
        if commit_uses_implicit_staging(str(command)):
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
        result = check_sync(root, config, "staged")
        if result.ok:
            if result.warnings:
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
    elif host_capability == "background":
        host_action = "launch_temporary_background_integrator"
    elif host_capability == "active_agent":
        host_action = "enter_internal_integration_phase"
    else:
        host_action = "keep_pending_until_discussion_or_refresh"
    payload = {
        "ok": True,
        "visibility": "silent_unless_blocked",
        "host_capability": host_capability,
        "host_action": host_action,
        "integration_prompt": config["paths"]["integration_prompt"],
        "ready_reports": state["selected_reports"] or state["ready_reports"],
        "status": state,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


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
                        host_thread_ref=args.host_thread_ref,
                        stale_after_seconds=args.stale_after,
                    )
                    if payload.get("ok"):
                        payload["task"] = task
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
    if args.command == "competitive-plan":
        return competitive_plan_main(args.task_id, args.candidates)
    if args.command == "task":
        return task_main(args.action, args.value)
    if args.command == "claim":
        return claim_main(args)
    if args.command == "git-pre-commit":
        return check_main("staged")
    return hook_main(args.command)
