"""Host-hook, CLI, and user-facing output boundary for WishGraph."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

from git_state import (
    LEGACY_PROJECT_STATUS_PATH,
    find_git_root,
    load_config,
    read_version,
    resolve_project_status_path,
    standard_project_status_conflict,
)
from policy import CheckResult, check_sync, integration_state
from workflow_state import dynamic_state_block, markdown_section


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for event in ("session-start", "pre-tool-use", "stop", "task-completed"):
        subparsers.add_parser(event)
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--scope", choices=("worktree", "staged"), default="worktree")
    subparsers.add_parser("status")
    subparsers.add_parser("git-pre-commit")
    args = parser.parse_args()

    if args.command == "check":
        return check_main(args.scope)
    if args.command == "status":
        return status_main()
    if args.command == "git-pre-commit":
        return check_main("staged")
    return hook_main(args.command)
