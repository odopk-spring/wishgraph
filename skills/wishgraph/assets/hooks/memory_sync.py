#!/usr/bin/env python3
"""Deterministic closeout checks for WishGraph-managed repositories.

The hook never writes semantic project memory. Worker agents create immutable
task-scoped reports under reports/runs/. An integration agent is the single
writer for shared project memory and reports/DEV_REPORT.md.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


DEFAULT_CONFIG: dict[str, Any] = {
    "version": 2,
    "mode": "enforce",
    "paths": {
        "prd": "PRD.md",
        "architecture": "ARCHITECTURE.md",
        "codemap": "CODEMAP.md",
        "conventions": "CONVENTIONS.md",
        "discussion_prompt": "prompts/DISCUSSION_AI.md",
        "execution_prompt": "prompts/EXECUTION_AI.md",
        "integration_prompt": "prompts/INTEGRATION_AI.md",
        "dev_report": "reports/DEV_REPORT.md",
        "run_report_glob": "reports/runs/*.md",
        "task_glob": ".tasks/build/*.md",
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
    "inject_project_summary_on_session_start": True,
    "session_summary_max_chars": 2000,
}

TEXT_ONLY_SUFFIXES = {".md", ".mdx", ".rst", ".txt"}
ACCEPTED_REPORT_STATUSES = {"completed", "blocked", "incomplete", "done"}
UPDATED_STATUSES = {"updated", "yes"}
INTEGRATE_STATUSES = {"integrate", "needs integration", "review", "proposed"}
NOOP_STATUSES = {"n/a", "na", "not applicable", "no"}
STATE_BLOCK_RE = re.compile(
    r"<!--\s*wishgraph:state:start\s*-->(.*?)<!--\s*wishgraph:state:end\s*-->",
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class CheckResult:
    trigger_paths: list[str] = field(default_factory=list)
    changed_paths: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


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
    return deep_merge(DEFAULT_CONFIG, data)


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


def matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def read_version(root: Path, path: str, scope: str) -> Optional[str]:
    if scope == "staged":
        try:
            result = run_git(root, "show", f":{path}")
        except subprocess.CalledProcessError:
            return None
        return result.stdout.decode("utf-8", errors="replace")
    full_path = root / path
    try:
        return full_path.read_text(encoding="utf-8")
    except OSError:
        return None


def read_head_version(root: Path, path: str) -> Optional[str]:
    try:
        result = run_git(root, "show", f"HEAD:{path}")
    except subprocess.CalledProcessError:
        return None
    return result.stdout.decode("utf-8", errors="replace")


def dynamic_state_block(content: Optional[str]) -> Optional[str]:
    if content is None:
        return None
    match = STATE_BLOCK_RE.search(content)
    return match.group(1).strip() if match else None


def markdown_section(content: Optional[str], heading: str) -> Optional[str]:
    if content is None:
        return None
    match = re.search(
        rf"(?ims)^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)",
        content,
    )
    return match.group(1).strip() if match else None


def integrated_report_paths(content: str, run_report_glob: str) -> set[str]:
    prefix = run_report_glob.split("*", 1)[0]
    return {
        normalize_cell(match)
        for match in re.findall(
            rf"{re.escape(prefix)}[A-Za-z0-9._/-]+\.md",
            content,
        )
    }


def shared_memory_paths(config: dict[str, Any]) -> set[str]:
    paths = config["paths"]
    return set(config.get("required_impact_rows", [])) | {paths["dev_report"]}


def project_session_context(root: Path, config: dict[str, Any]) -> Optional[str]:
    if not config.get("inject_project_summary_on_session_start", True):
        return None
    paths = config["paths"]
    overview = read_version(root, paths["dev_report"], "worktree")
    discussion = read_version(root, paths["discussion_prompt"], "worktree")
    results = markdown_section(overview, "Latest Integrated Results") or markdown_section(
        overview, "最新集成结果"
    )
    state = dynamic_state_block(discussion)
    sections: list[str] = []
    if results:
        sections.append(f"Latest integrated results:\n{results}")
    if state:
        sections.append(f"Current discussion handoff:\n{state}")
    if not sections:
        return None
    text = "WishGraph project update (read-only context):\n\n" + "\n\n".join(sections)
    limit = int(config.get("session_summary_max_chars", 2000))
    if len(text) > limit:
        text = text[: max(0, limit - 18)].rstrip() + "\n... summary clipped"
    return text


def normalize_cell(value: str) -> str:
    value = value.strip().strip("`").strip()
    return value.replace("\\", "/")


def parse_report_status(content: str) -> Optional[str]:
    match = re.search(
        r"(?mi)^\s*-\s*(?:Status|状态)\s*[:：]\s*([^\n]+?)\s*$",
        content,
    )
    return normalize_cell(match.group(1)).lower() if match else None


def parse_impact_rows(content: str) -> dict[str, tuple[str, str]]:
    rows: dict[str, tuple[str, str]] = {}
    for line in content.splitlines():
        if "|" not in line:
            continue
        cells = [normalize_cell(cell) for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        path, status, reason = cells[0], cells[1].lower(), cells[2]
        if path and not set(path) <= {"-", ":"}:
            rows[path] = (status, reason)
    return rows


def is_substantive(path: str, config: dict[str, Any]) -> bool:
    stateful = {
        config["paths"]["prd"],
        config["paths"]["architecture"],
        config["paths"]["codemap"],
        config["paths"]["conventions"],
        config["paths"]["execution_prompt"],
    }
    if path in stateful or fnmatch.fnmatch(path, config["paths"]["task_glob"]):
        return True
    return Path(path).suffix.lower() not in TEXT_ONLY_SUFFIXES


def validate_status(result: CheckResult, report_path: str, content: str) -> None:
    status = parse_report_status(content)
    if status not in ACCEPTED_REPORT_STATUSES:
        result.errors.append(
            f"{report_path} must set Status/状态 to Completed, Blocked, or Incomplete"
        )


def validate_run_report(
    root: Path,
    config: dict[str, Any],
    scope: str,
    report_path: str,
    result: CheckResult,
) -> None:
    content = read_version(root, report_path, scope)
    if content is None:
        result.errors.append(f"Cannot read the {scope} version of {report_path}")
        return
    if read_head_version(root, report_path) is not None:
        result.errors.append(
            f"{report_path} already exists in HEAD; run reports are immutable and must use a new ID"
        )
    validate_status(result, report_path, content)
    impact_rows = parse_impact_rows(content)
    for memory_path in config.get("required_impact_rows", []):
        row = impact_rows.get(memory_path)
        if row is None:
            result.errors.append(f"{report_path} is missing an impact row for {memory_path}")
            continue
        status, reason = row
        if status not in INTEGRATE_STATUSES | NOOP_STATUSES:
            result.errors.append(
                f"Worker impact for {memory_path} must be Integrate or N/A, got {status or 'blank'}"
            )
        if len(reason.strip()) < 3:
            result.errors.append(
                f"{status or 'Impact'} for {memory_path} requires a concrete reason"
            )


def validate_integration_overview(
    root: Path,
    config: dict[str, Any],
    scope: str,
    changed: list[str],
    run_reports: list[str],
    result: CheckResult,
) -> None:
    paths = config["paths"]
    overview_path = paths["dev_report"]
    discussion_path = paths["discussion_prompt"]
    overview = read_version(root, overview_path, scope)
    if overview is None:
        result.errors.append(f"Cannot read the {scope} version of {overview_path}")
        return
    validate_status(result, overview_path, overview)

    listed_reports = integrated_report_paths(overview, paths["run_report_glob"])
    for report_path in run_reports:
        if report_path not in listed_reports:
            result.errors.append(
                f"{overview_path} must list integrated run report {report_path}"
            )

    impact_rows = parse_impact_rows(overview)
    for memory_path in config.get("required_impact_rows", []):
        row = impact_rows.get(memory_path)
        if row is None:
            result.errors.append(f"{overview_path} is missing an impact row for {memory_path}")
            continue
        status, reason = row
        if status in UPDATED_STATUSES:
            if memory_path not in changed:
                result.errors.append(
                    f"{overview_path} says {memory_path} is Updated, but it is not in the {scope} diff"
                )
        elif status in NOOP_STATUSES:
            if memory_path in changed:
                result.errors.append(
                    f"{overview_path} says {memory_path} is N/A, but that file changed"
                )
            if config.get("allow_noop_with_reason", True) and len(reason.strip()) < 3:
                result.errors.append(f"N/A for {memory_path} requires a concrete reason")
        else:
            result.errors.append(
                f"Integration impact for {memory_path} must be Updated or N/A, got {status or 'blank'}"
            )

    if discussion_path not in changed:
        result.errors.append(
            f"Integration must update {discussion_path} so discussion agents receive the merged results"
        )
        return
    current_state = dynamic_state_block(read_version(root, discussion_path, scope))
    previous_state = dynamic_state_block(read_head_version(root, discussion_path))
    if current_state is None:
        result.errors.append(f"{discussion_path} is missing wishgraph:state start/end markers")
    elif previous_state is not None and current_state == previous_state:
        result.errors.append(
            f"{discussion_path} changed, but its dynamic wishgraph:state block did not"
        )


def check_sync(root: Path, config: dict[str, Any], scope: str) -> CheckResult:
    result = CheckResult()
    try:
        all_changed = changed_paths(root, scope)
    except (OSError, subprocess.CalledProcessError) as exc:
        result.errors.append(f"Unable to inspect Git changes: {exc}")
        return result

    ignored = list(config.get("ignore_globs", []))
    changed = sorted(path for path in all_changed if not matches_any(path, ignored))
    result.changed_paths = changed

    if not changed:
        return result

    paths = config["paths"]
    overview_path = paths["dev_report"]
    discussion_path = paths["discussion_prompt"]
    run_report_glob = paths["run_report_glob"]
    run_reports = sorted(path for path in changed if fnmatch.fnmatch(path, run_report_glob))
    trigger_paths = [
        path
        for path in changed
        if path not in {overview_path, discussion_path} and path not in run_reports
    ]
    result.trigger_paths = trigger_paths

    integration_mode = overview_path in changed
    if integration_mode:
        if not run_reports:
            result.errors.append(
                f"Integration must include at least one new {run_report_glob} file; use a no-commit merge or cherry-pick"
            )
        for report_path in run_reports:
            validate_run_report(root, config, scope, report_path, result)
        validate_integration_overview(
            root, config, scope, changed, run_reports, result
        )
        return result

    shared_changed = sorted(path for path in changed if path in shared_memory_paths(config))
    for path in shared_changed:
        result.errors.append(
            f"Worker agents must not update shared memory {path}; record Integrate in a task-scoped run report"
        )
    if len(run_reports) != 1:
        result.errors.append(
            f"Worker closeout requires exactly one new {run_report_glob} report, found {len(run_reports)}"
        )
    for report_path in run_reports:
        validate_run_report(root, config, scope, report_path, result)

    return result


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
            "Worker: create one new immutable reports/runs/<work-unit-id>.md,",
            "record Integrate or N/A for shared-memory impact, and do not edit shared state.",
            "Integration: merge with --no-commit, update reports/DEV_REPORT.md and",
            "prompts/DISCUSSION_AI.md, then record Updated or N/A for shared memory.",
            "Ad-hoc work does not require a task file, but still needs a unique run report.",
        ]
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
        if session_context:
            emit(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": session_context,
                    }
                }
            )
        else:
            emit({})
        return 0
    reason = format_failure(result, "worktree")

    if event == "session-start":
        context_parts = []
        if session_context:
            context_parts.append(session_context)
        context_parts.append(
            "WishGraph found pending or unsynchronized project changes from a prior "
            f"session. Resolve them before claiming new work complete.\n\n{reason}"
        )
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
        return 0
    print(format_failure(result, scope), file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for event in ("session-start", "pre-tool-use", "stop", "task-completed"):
        subparsers.add_parser(event)
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--scope", choices=("worktree", "staged"), default="worktree")
    subparsers.add_parser("git-pre-commit")
    args = parser.parse_args()

    if args.command == "check":
        return check_main(args.scope)
    if args.command == "git-pre-commit":
        return check_main("staged")
    return hook_main(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
