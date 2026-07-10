#!/usr/bin/env python3
"""Install WishGraph project-local hooks without replacing existing hooks."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional


SKILL_ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = SKILL_ROOT / "assets" / "hooks"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Cannot merge invalid JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def merge_hook_config(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    existing_hooks = merged.setdefault("hooks", {})
    if not isinstance(existing_hooks, dict):
        raise ValueError("Existing top-level hooks value must be a JSON object")
    incoming_hooks = incoming.get("hooks", {})
    for event, groups in incoming_hooks.items():
        current = existing_hooks.setdefault(event, [])
        if not isinstance(current, list):
            raise ValueError(f"Existing hooks.{event} value must be a JSON array")
        preserved: list[Any] = []
        for group in current:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                preserved.append(group)
                continue
            remaining_handlers = [
                handler
                for handler in group["hooks"]
                if not (
                    isinstance(handler, dict)
                    and ".wishgraph/hooks/memory_sync.py"
                    in str(handler.get("command", "")).replace("\\", "/")
                )
            ]
            if remaining_handlers:
                preserved_group = dict(group)
                preserved_group["hooks"] = remaining_handlers
                preserved.append(preserved_group)
        current[:] = preserved
        fingerprints = {
            json.dumps(group, sort_keys=True, separators=(",", ":")) for group in current
        }
        for group in groups:
            fingerprint = json.dumps(group, sort_keys=True, separators=(",", ":"))
            if fingerprint not in fingerprints:
                current.append(group)
                fingerprints.add(fingerprint)
    return merged


def install_runtime(target: Path, mode: str, force_assets: bool) -> list[Path]:
    installed: list[Path] = []
    target_hook_dir = target / ".wishgraph" / "hooks"
    target_hook_dir.mkdir(parents=True, exist_ok=True)
    runtime_target = target_hook_dir / "memory_sync.py"
    if runtime_target.exists() and not force_assets:
        current = runtime_target.read_bytes()
        incoming = (ASSET_ROOT / "memory_sync.py").read_bytes()
        if current != incoming:
            raise FileExistsError(
                f"{runtime_target} already exists and differs; re-run with --force-assets"
            )
    else:
        shutil.copy2(ASSET_ROOT / "memory_sync.py", runtime_target)
        runtime_target.chmod(runtime_target.stat().st_mode | stat.S_IXUSR)
        installed.append(runtime_target)

    config_target = target / ".wishgraph" / "config.json"
    default_config = read_json(ASSET_ROOT / "config.json")
    existing_config = read_json(config_target) if config_target.exists() else {}
    config = deep_merge(default_config, existing_config)
    config["version"] = default_config["version"]
    config["required_impact_rows"] = list(
        dict.fromkeys(
            list(default_config.get("required_impact_rows", []))
            + list(existing_config.get("required_impact_rows", []))
        )
    )
    config["mode"] = mode
    write_json_atomic(config_target, config)
    installed.append(config_target)
    return installed


def install_host_config(target: Path, host: str) -> Path:
    if host == "codex":
        destination = target / ".codex" / "hooks.json"
        source = ASSET_ROOT / "codex-hooks.json"
    else:
        destination = target / ".claude" / "settings.json"
        source = ASSET_ROOT / "claude-settings.json"
    merged = merge_hook_config(read_json(destination), read_json(source))
    write_json_atomic(destination, merged)
    return destination


def git_root(target: Path) -> Optional[Path]:
    result = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "--show-toplevel"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return Path(result.stdout.strip()).resolve() if result.returncode == 0 else None


def install_git_hook(target: Path) -> tuple[Optional[Path], Optional[str]]:
    root = git_root(target)
    if root is None:
        return None, "Git pre-commit hook skipped: target is not a Git repository."
    hook_location = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--git-path", "hooks/pre-commit"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    ).stdout.strip()
    hook_path = Path(hook_location)
    if not hook_path.is_absolute():
        hook_path = (root / hook_path).resolve()
    if hook_path.exists():
        return None, (
            f"Git pre-commit hook skipped because {hook_path} already exists. "
            "Chain `.wishgraph/hooks/memory_sync.py git-pre-commit` manually if desired."
        )
    hook_path.parent.mkdir(parents=True, exist_ok=True)
    hook_path.write_text(
        "#!/bin/sh\n"
        "root=$(git rev-parse --show-toplevel) || exit 0\n"
        "if command -v python3 >/dev/null 2>&1; then\n"
        "  exec python3 \"$root/.wishgraph/hooks/memory_sync.py\" git-pre-commit\n"
        "fi\n"
        "if command -v python >/dev/null 2>&1; then\n"
        "  exec python \"$root/.wishgraph/hooks/memory_sync.py\" git-pre-commit\n"
        "fi\n"
        "echo 'WishGraph pre-commit requires Python 3.' >&2\n"
        "exit 1\n",
        encoding="utf-8",
    )
    hook_path.chmod(hook_path.stat().st_mode | stat.S_IXUSR)
    return hook_path, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default=".", help="Target project directory")
    parser.add_argument(
        "--host",
        choices=("codex", "claude", "all"),
        default="all",
        help="Project-level agent configuration to merge",
    )
    parser.add_argument(
        "--mode",
        choices=("off", "warn", "enforce"),
        default="warn",
        help="Initial hook enforcement mode",
    )
    parser.add_argument(
        "--force-assets",
        action="store_true",
        help="Replace an existing generated memory_sync.py runtime",
    )
    parser.add_argument(
        "--git-hook",
        action="store_true",
        help="Also install an opt-in Git pre-commit hook when none exists",
    )
    args = parser.parse_args()

    if sys.version_info < (3, 9):
        print(
            "WishGraph hooks require Python 3.9 or newer. "
            "A typical Python install uses about 100-300 MB and takes 2-10 minutes.",
            file=sys.stderr,
        )
        return 3
    if shutil.which("git") is None:
        print(
            "WishGraph hooks require Git. A typical Git install uses about "
            "200-500 MB and takes 2-10 minutes. Install Git, reopen the terminal, "
            "then retry.",
            file=sys.stderr,
        )
        return 3

    target = Path(args.target).expanduser().resolve()
    if not target.is_dir():
        print(f"Target directory does not exist: {target}", file=sys.stderr)
        return 2
    repository_root = git_root(target)
    if repository_root is None:
        print(
            f"WishGraph hooks need a Git repository, but {target} is not inside one.\n"
            "Run `git init` there, or ask your agent to initialize Git, then retry. "
            "Initializing an empty repository normally takes under a second and "
            "uses less than 1 MB.",
            file=sys.stderr,
        )
        return 3
    if repository_root != target:
        print(f"Using detected Git repository root: {repository_root}")
        target = repository_root

    try:
        installed = install_runtime(target, args.mode, args.force_assets)
        hosts = ("codex", "claude") if args.host == "all" else (args.host,)
        installed.extend(install_host_config(target, host) for host in hosts)
        warning = None
        if args.git_hook:
            hook_path, warning = install_git_hook(target)
            if hook_path:
                installed.append(hook_path)
    except (OSError, ValueError, FileExistsError) as exc:
        print(f"WishGraph hook installation failed: {exc}", file=sys.stderr)
        return 1

    print("WishGraph project hooks installed or merged:")
    for path in installed:
        try:
            display = path.relative_to(target)
        except ValueError:
            display = path
        print(f"- {display}")
    if warning:
        print(warning, file=sys.stderr)
    if "codex" in hosts:
        print("Codex: trust the project, then review the hook definitions with /hooks.")
    print(f"Mode: {args.mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
