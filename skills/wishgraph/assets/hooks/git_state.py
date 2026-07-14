"""Git and repository-state boundary for the WishGraph hook runtime."""

from __future__ import annotations

import fnmatch
import json
import subprocess
from pathlib import Path
from typing import Any, Optional


DEFAULT_CONFIG: dict[str, Any] = {
    "version": 8,
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
