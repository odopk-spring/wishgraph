#!/usr/bin/env python3
"""Stable WishGraph hook entrypoint and compatibility facade.

The runtime is split into Git discovery, workflow-state parsing, policy
evaluation, and host adaptation. Hooks do not start agents or write semantic
project memory.
"""

from __future__ import annotations

import sys
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

# Keep the historical module API available to installed hooks and downstream tests.
from git_state import *  # noqa: F401,F403,E402
from workflow_state import *  # noqa: F401,F403,E402
from policy import *  # noqa: F401,F403,E402
from host_adapter import *  # noqa: F401,F403,E402


if __name__ == "__main__":
    _configure_utf8_stdio()
    raise SystemExit(main())
