"""Typed workflow-state parsing for WishGraph Markdown artifacts.

Semantic project truth stays in human-authored Markdown. Lifecycle facts that
hooks must evaluate live in small JSON blocks embedded in those Markdown files.
Legacy label-based documents remain readable during migration.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional


SCHEMA_VERSION = 1
SUPPORTED_KINDS = {"task", "run", "integration"}


@dataclass(frozen=True)
class WorkflowBlock:
    kind: str
    data: dict[str, Any]


def _block_pattern(kind: str) -> re.Pattern[str]:
    if kind not in SUPPORTED_KINDS:
        raise ValueError(f"Unsupported WishGraph workflow block kind: {kind}")
    return re.compile(
        rf"<!--\s*wishgraph:{kind}-state:start\s*-->(.*?)"
        rf"<!--\s*wishgraph:{kind}-state:end\s*-->",
        re.IGNORECASE | re.DOTALL,
    )


def parse_workflow_block(content: str, kind: str) -> tuple[Optional[WorkflowBlock], list[str]]:
    """Parse one embedded JSON workflow block without interpreting Markdown prose."""
    matches = _block_pattern(kind).findall(content)
    if not matches:
        return None, []
    if len(matches) != 1:
        return None, [f"must contain exactly one wishgraph:{kind}-state block"]

    raw = matches[0].strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL | re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, [f"wishgraph:{kind}-state is invalid JSON: {exc.msg}"]
    if not isinstance(value, dict):
        return None, [f"wishgraph:{kind}-state must contain a JSON object"]

    errors: list[str] = []
    if value.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            f"wishgraph:{kind}-state schema_version must be {SCHEMA_VERSION}"
        )
    if value.get("kind") != kind:
        errors.append(f"wishgraph:{kind}-state kind must be {kind}")
    return WorkflowBlock(kind=kind, data=value), errors


def without_workflow_block(content: str, kind: str) -> str:
    """Remove one workflow block so callers can compare surrounding semantics."""
    return _block_pattern(kind).sub("", content).strip()


def normalized_string(value: Any, default: str = "missing") -> str:
    if value is None:
        return default
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip().strip("`").replace("\\", "/").lower() or default


def validation_values(value: Any) -> list[str]:
    """Return normalized results from a map or a list of validation records."""
    if isinstance(value, dict):
        return [normalized_string(result) for result in value.values()]
    if isinstance(value, list):
        results: list[str] = []
        for item in value:
            if isinstance(item, dict) and "result" in item:
                results.append(normalized_string(item["result"]))
        return results
    return []


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        str(item).strip().strip("`").replace("\\", "/")
        for item in value
        if isinstance(item, str) and item.strip()
    ]
