#!/usr/bin/env python3
"""Stable WishGraph hook entrypoint.

The runtime is split into Git discovery, workflow-state parsing, policy
evaluation, and host adaptation. Hooks do not start agents or write semantic
project memory.
"""

from __future__ import annotations

import sys

# Hook execution must not dirty a governed repository with __pycache__ files.
# Set this before importing sibling runtime modules.
sys.dont_write_bytecode = True
from pathlib import Path


def _configure_utf8_stdio() -> None:
    """Keep bilingual Hook JSON stable under legacy Windows code pages."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="strict")
        except (AttributeError, OSError, ValueError):
            continue


# Installed project hooks are plain sibling modules rather than a Python package.
sys.path.insert(0, str(Path(__file__).resolve().parent))

_FAST_PRETOOL_ENTRY = (
    __name__ == "__main__"
    and len(sys.argv) > 1
    and sys.argv[1] == "pre-tool-use"
)

# Re-export the four public runtime boundaries through one stable executable.
from git_state import *  # noqa: F401,F403,E402
from workflow_state import *  # noqa: F401,F403,E402
from policy import *  # noqa: F401,F403,E402
if _FAST_PRETOOL_ENTRY:
    from tool_gate_provider import pre_tool_use_entry  # noqa: E402
else:
    from host_adapter import *  # noqa: F401,F403,E402


def _direct_hook_dispatch() -> int | None:
    """Bypass the large diagnostic CLI parser for latency-sensitive host events."""
    if len(sys.argv) < 2 or sys.argv[1] not in {
        "session-start",
        "user-prompt-submit",
        "pre-tool-use",
        "stop",
        "task-completed",
    }:
        return None
    arguments = sys.argv[2:]
    if not arguments:
        host = "unknown"
    elif (
        len(arguments) == 2
        and arguments[0] == "--host"
        and arguments[1] in {"codex", "claude", "unknown"}
    ):
        host = arguments[1]
    else:
        return None
    return hook_main(sys.argv[1], host)


if __name__ == "__main__":
    _configure_utf8_stdio()
    if _FAST_PRETOOL_ENTRY:
        arguments = sys.argv[2:]
        host = (
            arguments[1]
            if len(arguments) == 2
            and arguments[0] == "--host"
            and arguments[1] in {"codex", "claude", "unknown"}
            else "unknown"
        )
        raise SystemExit(pre_tool_use_entry(host))
    hook_result = _direct_hook_dispatch()
    raise SystemExit(main() if hook_result is None else hook_result)
