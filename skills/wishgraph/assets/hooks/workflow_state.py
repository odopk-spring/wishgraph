"""Typed workflow-state parsing for WishGraph Markdown artifacts.

Semantic project truth stays in human-authored Markdown. Lifecycle facts that
hooks must evaluate live in small JSON blocks embedded in those Markdown files.
Legacy label-based documents remain readable during migration.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


SCHEMA_VERSION = 1
SUPPORTED_KINDS = {"task", "run", "integration"}
TASK_STATUS_ALIASES = {"pending": "draft", "done": "completed"}
TASK_ID_RE = re.compile(r"^(?P<number>\d{3,})(?P<suffix>[a-z]*)$")
STATE_BLOCK_RE = re.compile(
    r"<!--\s*wishgraph:state:start\s*-->(.*?)<!--\s*wishgraph:state:end\s*-->",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class WorkflowBlock:
    kind: str
    data: dict[str, Any]


@dataclass
class ReportState:
    path: str
    status: str
    work_type: str
    batch_id: str
    authorization: str
    readiness: str
    safety_errors: list[str] = field(default_factory=list)
    state_source: str = "legacy"
    scope_check: str = "missing"
    conflict_status: str = "missing"
    new_decision: str = "missing"
    validation_results: list[str] = field(default_factory=list)
    task_id: str = ""
    attempt: int = 1


@dataclass
class TaskState:
    path: str
    task_id: str
    status: str
    work_type: str
    batch_id: str
    run_report: str
    worker_creation_authorized: bool
    integration_policy: str
    parent_task_id: str = ""
    dependencies: list[str] = field(default_factory=list)
    attempt: int = 1
    errors: list[str] = field(default_factory=list)
    state_source: str = "legacy"


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


def canonical_task_id(value: Any) -> str:
    """Return a normalized Task ID or an empty string when syntax is invalid."""
    candidate = str(value or "").strip().lower()
    return candidate if TASK_ID_RE.fullmatch(candidate) else ""


def task_id_parts(value: Any) -> tuple[str, str]:
    task_id = canonical_task_id(value)
    if not task_id:
        raise ValueError("Task ID must match ^\\d{3,}[a-z]*$")
    match = TASK_ID_RE.fullmatch(task_id)
    assert match is not None
    return match.group("number"), match.group("suffix")


def suffix_index(suffix: str) -> int:
    """Convert an Excel-like lower-case suffix to a one-based sequence number."""
    if not suffix or not re.fullmatch(r"[a-z]+", suffix):
        raise ValueError("Task suffix must contain one or more lower-case letters")
    value = 0
    for letter in suffix:
        value = value * 26 + (ord(letter) - ord("a") + 1)
    return value


def suffix_for_index(index: int) -> str:
    """Convert a one-based sequence number to an Excel-like lower-case suffix."""
    if index < 1:
        raise ValueError("Task suffix index must be positive")
    letters: list[str] = []
    while index:
        index, remainder = divmod(index - 1, 26)
        letters.append(chr(ord("a") + remainder))
    return "".join(reversed(letters))


def followup_task_id(root_task_id: Any, index: int) -> str:
    number, suffix = task_id_parts(root_task_id)
    if suffix:
        raise ValueError("Follow-up allocation requires a root numeric Task ID")
    return f"{number}{suffix_for_index(index)}"


TASK_COMMANDS = {
    "执行": "execute",
    "继续执行": "continue",
    "查看": "inspect",
    "观察": "observe",
    "停止": "stop",
    "重新执行": "retry",
    "重试": "retry",
    "接管": "take_over",
}


def parse_task_command(text: str) -> Optional[dict[str, Any]]:
    """Parse one exact natural-language Task command without fuzzy execution."""
    candidate = text.strip().lower()
    family = re.fullmatch(r"查看\s*(\d{3,}[a-z]*)\s*系列任务", candidate)
    if family:
        task_id = canonical_task_id(family.group(1))
        return {"action": "family", "task_id": task_id, "authorizes_execution": False}

    action_pattern = "|".join(
        sorted((re.escape(item) for item in TASK_COMMANDS), key=len, reverse=True)
    )
    match = re.fullmatch(
        rf"(?P<action>{action_pattern})\s*(?P<task_id>\d{{3,}}[a-z]*)\s*(?:号)?任务",
        candidate,
    )
    if match:
        action = TASK_COMMANDS[match.group("action")]
        return {
            "action": action,
            "task_id": canonical_task_id(match.group("task_id")),
            "authorizes_execution": action in {"execute", "continue", "retry", "take_over"},
        }

    english = re.fullmatch(
        r"(?P<action>execute|continue|inspect|observe|stop|retry|take over)\s+"
        r"(?:task\s+)?(?P<task_id>\d{3,}[a-z]*)",
        candidate,
    )
    if english:
        action = english.group("action").replace(" ", "_")
        return {
            "action": action,
            "task_id": canonical_task_id(english.group("task_id")),
            "authorizes_execution": action in {"execute", "continue", "retry", "take_over"},
        }
    return None


def positive_attempt(value: Any, errors: list[str]) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        errors.append("attempt must be a positive integer")
        return 1
    return value


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


def normalize_cell(value: str) -> str:
    return value.strip().strip("`").strip().replace("\\", "/")


def integrated_report_paths(content: str, run_report_glob: str) -> set[str]:
    block, errors = parse_workflow_block(content, "integration")
    if block is not None and not errors:
        return set(string_list(block.data.get("reports")))
    prefix = run_report_glob.split("*", 1)[0]
    return {
        normalize_cell(match)
        for match in re.findall(
            rf"{re.escape(prefix)}[A-Za-z0-9._/-]+\.md",
            content,
        )
    }


def parse_report_status(content: str) -> Optional[str]:
    for kind in ("run", "integration"):
        block, errors = parse_workflow_block(content, kind)
        if block is not None and not errors:
            return normalized_string(block.data.get("status"))
    match = re.search(
        r"(?mi)^\s*-\s*(?:Status|状态)\s*[:：]\s*([^\n]+?)\s*$",
        content,
    )
    return normalize_cell(match.group(1)).lower() if match else None


def parse_labeled_field(
    content: str, *labels: str, lowercase: bool = True
) -> Optional[str]:
    label_pattern = "|".join(re.escape(label) for label in labels)
    match = re.search(
        rf"(?mi)^\s*(?:-\s*)?(?:{label_pattern})\s*[:：]\s*([^\n]+?)\s*$",
        content,
    )
    if not match:
        return None
    value = normalize_cell(match.group(1))
    return value.lower() if lowercase else value


def validation_results(content: str) -> list[str]:
    section = markdown_section(content, "Validation") or markdown_section(content, "验证")
    if not section:
        return []
    results: list[str] = []
    for line in section.splitlines():
        if "|" not in line:
            continue
        cells = [normalize_cell(cell) for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        check_name, result = cells[0].lower(), cells[2].lower()
        if check_name in {"check", "检查", "---"} or not check_name.strip("-: "):
            continue
        results.append(result)
    return results


def parse_report_state(report_path: str, content: str) -> ReportState:
    block, block_errors = parse_workflow_block(content, "run")
    if block is not None:
        data = block.data
        status = normalized_string(data.get("status"))
        work_type = normalized_string(data.get("work_type"))
        batch_id = normalized_string(data.get("batch_id"), "n/a")
        readiness = normalized_string(data.get("integration_readiness"))
        authorization = normalized_string(data.get("integration_authorization"))
        scope_check = normalized_string(data.get("scope_check"))
        conflict_status = normalized_string(data.get("conflict_status"))
        new_decision = normalized_string(data.get("new_decision"))
        results = validation_values(data.get("validation"))
        raw_report_task_id = data.get("task_id")
        task_id = "" if raw_report_task_id is None else canonical_task_id(raw_report_task_id)
        if raw_report_task_id is not None and raw_report_task_id != "" and not task_id:
            block_errors.append("task_id must be null or match ^\\d{3,}[a-z]*$")
        attempt = positive_attempt(data.get("attempt", 1), block_errors)
        state_source = "structured"
    else:
        status = parse_report_status(content) or "missing"
        work_type = parse_labeled_field(content, "Work type", "工作类型") or "missing"
        batch_id = parse_labeled_field(content, "Batch ID", "批次 ID") or "n/a"
        readiness = (
            parse_labeled_field(content, "Integration readiness", "集成就绪状态")
            or "missing"
        )
        authorization = (
            parse_labeled_field(content, "Integration authorization", "集成授权")
            or "missing"
        )
        scope_check = parse_labeled_field(content, "Scope check", "范围检查") or "missing"
        conflict_status = (
            parse_labeled_field(content, "Conflict status", "冲突状态") or "missing"
        )
        new_decision = parse_labeled_field(
            content,
            "New product / architecture / data decision",
            "新增产品 / 架构 / 数据决策",
        ) or "missing"
        results = validation_results(content)
        task_id = ""
        attempt = 1
        state_source = "legacy"
    errors: list[str] = list(block_errors)

    return ReportState(
        path=report_path,
        status=status,
        work_type=work_type,
        batch_id=batch_id,
        authorization=authorization,
        readiness=readiness,
        scope_check=scope_check,
        conflict_status=conflict_status,
        new_decision=new_decision,
        validation_results=results,
        task_id=task_id,
        attempt=attempt,
        safety_errors=errors,
        state_source=state_source,
    )


def canonical_task_status(value: Any) -> str:
    status = normalized_string(value)
    return TASK_STATUS_ALIASES.get(status, status)


def canonical_integration_policy(value: Any) -> str:
    policy = normalized_string(value)
    if policy in {
        "inherited_task_approval",
        "inherited task approval",
        "task approval",
        "approved with task",
        "随任务批准授权",
        "任务批准",
    }:
        return "inherited_task_approval"
    if policy in {
        "explicit_user_confirmation",
        "explicit user confirmation",
        "requires explicit user confirmation",
        "user confirmed",
        "explicitly confirmed",
        "用户明确确认",
        "用户已确认",
        "需要用户明确确认",
        "requires_explicit_user_confirmation",
        "explicit_confirmation_required",
    }:
        return "requires_explicit_user_confirmation"
    return policy


def parse_task_state(task_path: str, content: str) -> TaskState:
    block, block_errors = parse_workflow_block(content, "task")
    errors = list(block_errors)
    if block is not None:
        data = block.data
        raw_task_id = str(data.get("task_id", "")).strip()
        task_id = canonical_task_id(raw_task_id)
        if raw_task_id and not task_id:
            errors.append("task_id must match ^\\d{3,}[a-z]*$")
        raw_parent = data.get("parent_task_id")
        parent_task_id = "" if raw_parent is None else canonical_task_id(raw_parent)
        if raw_parent is not None and raw_parent != "" and not parent_task_id:
            errors.append("parent_task_id must be null or match ^\\d{3,}[a-z]*$")
        dependencies = [item.lower() for item in string_list(data.get("dependencies"))]
        if not isinstance(data.get("dependencies", []), list):
            errors.append("dependencies must be a list")
        invalid_dependencies = [item for item in dependencies if not canonical_task_id(item)]
        if invalid_dependencies:
            errors.append("dependencies must contain only valid Task IDs")
        attempt = positive_attempt(data.get("attempt", 1), errors)
        status = canonical_task_status(data.get("status"))
        work_type = normalized_string(data.get("work_type"))
        batch_id = normalized_string(data.get("batch_id"), "n/a")
        run_report = normalize_cell(str(data.get("run_report", "")))
        worker_authorized_value = data.get("worker_creation_authorized")
        worker_authorized = worker_authorized_value is True
        if not isinstance(worker_authorized_value, bool):
            errors.append("worker_creation_authorized must be true or false")
        integration_policy = canonical_integration_policy(data.get("integration_policy"))
        state_source = "structured"
    else:
        task_id = Path(task_path).stem
        parent_task_id = ""
        dependencies = []
        attempt = 1
        status = canonical_task_status(
            parse_labeled_field(content, "Status", "状态") or "draft"
        )
        work_type = parse_labeled_field(content, "Work type", "工作类型") or "missing"
        batch_id = parse_labeled_field(content, "Batch ID", "批次 ID") or "n/a"
        run_report = normalize_cell(
            parse_labeled_field(content, "Run report", "执行报告", lowercase=False)
            or ""
        )
        worker_authorized = status != "draft"
        integration_policy = canonical_integration_policy(
            parse_labeled_field(content, "Integration authorization", "集成授权")
            or "missing"
        )
        state_source = "legacy"

    return TaskState(
        path=task_path,
        task_id=task_id,
        status=status,
        work_type=work_type,
        batch_id=batch_id,
        run_report=run_report,
        worker_creation_authorized=worker_authorized,
        integration_policy=integration_policy,
        parent_task_id=parent_task_id,
        dependencies=dependencies,
        attempt=attempt,
        errors=errors,
        state_source=state_source,
    )


def parse_impact_rows(content: str) -> dict[str, tuple[str, str]]:
    rows: dict[str, tuple[str, str]] = {}
    for line in content.splitlines():
        if "|" not in line:
            continue
        cells = [normalize_cell(cell) for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        path, status, reason = cells[0], cells[1].lower(), cells[2]
        if path.lower() in {"file", "文件", "---"} or not path.strip("-: "):
            continue
        rows[path] = (status, reason)
    return rows
