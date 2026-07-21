#!/usr/bin/env python3
"""Route a global host Hook only when the current Git project enables WishGraph."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


def emit_noop() -> int:
    sys.stdout.write("{}\n")
    return 0


def git_root(start: Path) -> Optional[Path]:
    try:
        result = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return Path(result.stdout.strip()).resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "event",
        choices=(
            "session-start",
            "user-prompt-submit",
            "pre-tool-use",
            "stop",
            "task-completed",
        ),
    )
    parser.add_argument("--host", choices=("codex", "claude"), required=True)
    args = parser.parse_args()

    raw = sys.stdin.read()
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        payload = {}
    cwd = Path(
        payload.get("cwd") if isinstance(payload, dict) and payload.get("cwd") else os.getcwd()
    )
    root = git_root(cwd)
    if root is None:
        return emit_noop()
    config_path = root / ".wishgraph" / "config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return emit_noop()
    if not isinstance(config, dict) or config.get("mode") not in {"warn", "enforce"}:
        return emit_noop()
    required_hosts = config.get("required_hosts")
    if isinstance(required_hosts, list) and args.host not in required_hosts:
        return emit_noop()

    project_runtime = root / ".wishgraph" / "hooks" / "memory_sync.py"
    bundled_runtime = Path(__file__).resolve().parents[1] / "assets" / "hooks" / "memory_sync.py"
    runtime = project_runtime if project_runtime.is_file() else bundled_runtime
    if not runtime.is_file():
        return emit_noop()
    try:
        result = subprocess.run(
            [sys.executable, str(runtime), args.event, "--host", args.host],
            input=raw,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError:
        return emit_noop()
    sys.stdout.write(result.stdout or "{}\n")
    sys.stderr.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
