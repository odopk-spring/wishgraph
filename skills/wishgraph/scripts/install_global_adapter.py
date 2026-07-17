#!/usr/bin/env python3
"""Merge the WishGraph no-op-unless-enabled Hook bridge into global host config."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import tempfile
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
BRIDGE = SKILL_ROOT / "scripts" / "global_host_hook.py"
ASSET_ROOT = SKILL_ROOT / "assets" / "hooks"
EVENT_ARGUMENTS = {
    "SessionStart": "session-start",
    "UserPromptSubmit": "user-prompt-submit",
    "PreToolUse": "pre-tool-use",
    "Stop": "stop",
    "TaskCompleted": "task-completed",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def is_wishgraph_hook(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    command = str(value.get("command") or "")
    windows_command = str(value.get("commandWindows") or "")
    combined = f"{command}\n{windows_command}"
    return (
        "global_host_hook.py" in combined
        or ".wishgraph/hooks/memory_sync.py" in combined
    )


def without_wishgraph_hooks(groups: Any) -> list[dict[str, Any]]:
    """Remove only managed Hook entries, preserving unrelated entries and groups."""
    if not isinstance(groups, list):
        return []
    preserved: list[dict[str, Any]] = []
    for value in groups:
        if not isinstance(value, dict):
            continue
        group = json.loads(json.dumps(value))
        hooks = group.get("hooks")
        if not isinstance(hooks, list):
            preserved.append(group)
            continue
        group["hooks"] = [hook for hook in hooks if not is_wishgraph_hook(hook)]
        if group["hooks"]:
            preserved.append(group)
    return preserved


def bridge_group(group: dict[str, Any], event: str, host: str) -> dict[str, Any]:
    converted = json.loads(json.dumps(group))
    event_argument = EVENT_ARGUMENTS[event]
    unix_command = " ".join(
        shlex.quote(value)
        for value in (sys.executable, str(BRIDGE), event_argument, "--host", host)
    )
    windows_command = (
        "powershell -NoProfile -Command \"& '"
        + str(Path(sys.executable)).replace("'", "''")
        + "' '"
        + str(BRIDGE).replace("'", "''")
        + f"' {event_argument} --host {host}\""
    )
    for hook in converted.get("hooks", []):
        if not isinstance(hook, dict):
            continue
        hook["command"] = unix_command
        hook["commandWindows"] = windows_command
    return converted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=("codex", "claude"), required=True)
    parser.add_argument("--config-home")
    args = parser.parse_args()

    if args.host == "codex":
        home = Path(args.config_home or os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        config_path = home / "hooks.json"
        asset_path = ASSET_ROOT / "codex-hooks.json"
    else:
        home = Path(args.config_home or os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
        config_path = home / "settings.json"
        asset_path = ASSET_ROOT / "claude-settings.json"
    existing = read_json(config_path)
    asset = read_json(asset_path)
    hooks = existing.setdefault("hooks", {})
    for event, groups in (asset.get("hooks") or {}).items():
        current = without_wishgraph_hooks(hooks.get(event))
        current.extend(
            bridge_group(group, event, args.host)
            for group in groups
            if isinstance(group, dict)
        )
        hooks[event] = current
    write_json(config_path, existing)
    print(f"Installed WishGraph global {args.host} Host Adapter in {config_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
