"""Typed workflow-state parsing for WishGraph Markdown artifacts.

Semantic project truth stays in human-authored Markdown. Lifecycle facts that
hooks must evaluate live in small JSON blocks embedded in those Markdown files.
Legacy label-based documents remain readable during migration.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional


SCHEMA_VERSION = 1
SUPPORTED_KINDS = {"task", "revision", "run", "integration"}
SESSION_ROLES = {"neutral", "discussion", "worker"}
FLOW_PHASES = {
    "planning",
    "awaiting_worker_authorization",
    "routing_worker",
    "waiting_for_user_launch",
    "waiting_for_worker",
    "integration_pending",
    "integrating",
    "decision_required",
    "presenting_result",
}
EXPECTED_TRANSITIONS = {
    "approve_worker_launch",
    "launch_worker_manually",
    "wait_for_worker",
    "auto_integrate",
    "resolve_conflict",
    "repair_worker_closeout",
    "accept_result",
    "route_revision",
    "rebind_worker",
}
CONTEXTUAL_APPROVALS = {
    "可以",
    "开始吧",
    "执行吧",
    "继续",
    "按这个做",
    "创建吧",
    "go ahead",
    "start",
    "proceed",
    "continue",
}
TASK_STATUS_ALIASES = {"pending": "draft", "done": "completed"}
TASK_ID_RE = re.compile(r"^(?P<number>\d{3,})(?P<suffix>[a-z]*)$")
REVISION_ID_RE = re.compile(
    r"^(?P<task_id>\d{3,}[a-z]*)-r(?P<revision_number>[1-9]\d*)$"
)
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
    revision_id: str = ""
    attempt: int = 1
    execution_mode: str = "exclusive"
    changed_paths: list[str] = field(default_factory=list)
    risk_flags_known: bool = False
    risk_flags_clear: bool = False
    change_class: str = "formal"
    candidate_score: Optional[float] = None
    selection_requires_judgment: bool = False


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
    execution_mode: str = "exclusive"
    comparison_group: str = ""
    errors: list[str] = field(default_factory=list)
    state_source: str = "legacy"


@dataclass
class RevisionState:
    path: str
    revision_id: str
    parent_task_id: str
    status: str
    user_request: str
    allowed_scope: list[str]
    validation_plan: list[str]
    run_report: str
    worker_creation_authorized: bool = True
    errors: list[str] = field(default_factory=list)
    state_source: str = "structured"


@dataclass(frozen=True)
class ExpectedTransition:
    """The one contextual transition that a short user reply may consume."""

    kind: str
    task_id: str = ""
    report_id: str = ""
    decision_id: str = ""
    integration_id: str = ""
    revision_id: str = ""


@dataclass(frozen=True)
class SessionFlowState:
    session_id: str
    role: str = "neutral"
    host: str = "unknown"
    phase: str = "planning"
    expected_transition: Optional[ExpectedTransition] = None


@dataclass(frozen=True)
class TaskFlowState:
    task_id: str
    lifecycle: str = "draft"
    attempt: int = 1
    worker_authorized: bool = False
    run_report: str = ""


@dataclass(frozen=True)
class WorkerRuntimeState:
    claim_id: str = ""
    branch: str = ""
    worktree: str = ""
    host_window_or_thread_id: str = ""
    active_task_id: str = ""
    active_revision_id: str = ""
    previous_task_id: str = ""
    previous_claim_id: str = ""
    worker_session_id: str = ""
    worker_availability: str = "unknown"
    binding_status: str = "unbound"
    allowed_scope: tuple[str, ...] = ()
    validation_plan: tuple[str, ...] = ()
    execution_ownership: str = ""


@dataclass(frozen=True)
class IntegrationRuntimeState:
    lease_id: str = ""
    integration_id: str = ""
    base_branch: str = ""
    worktree: str = ""
    selected_task_ids: tuple[str, ...] = ()
    selected_reports: tuple[str, ...] = ()
    revision_id: str = ""


@dataclass(frozen=True)
class PendingDecisionState:
    decision_id: str = ""
    kind: str = ""
    options: tuple[str, ...] = ()
    recommended_option: str = ""


@dataclass(frozen=True)
class OrchestrationState:
    session: SessionFlowState
    task: Optional[TaskFlowState] = None
    worker_runtime: WorkerRuntimeState = field(default_factory=WorkerRuntimeState)
    integration_runtime: IntegrationRuntimeState = field(
        default_factory=IntegrationRuntimeState
    )
    pending_decision: PendingDecisionState = field(
        default_factory=PendingDecisionState
    )
    candidate_task_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class UserEvent:
    kind: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HostCapability:
    host: str = "unknown"
    can_create_visible_worker: bool = False
    can_gate_writes: bool = False
    can_gate_builds: bool = False
    can_gate_reads: bool = False
    can_route_existing_worker: bool = False
    can_reuse_worker: bool = False


@dataclass(frozen=True)
class FlowPlan:
    accepted: bool
    next_action: str
    state_patch: dict[str, Any] = field(default_factory=dict)
    task_id: str = ""
    required_claim: bool = False
    required_integration_lease: bool = False
    host_route: str = ""
    user_message: str = ""
    stop_after_action: bool = False
    denial_reason: str = ""
    revision_id: str = ""
    target_worker_id: str = ""
    work_payload: dict[str, Any] = field(default_factory=dict)


def is_contextual_approval(text: str) -> bool:
    """Return true for a short approval; meaning comes from expected_transition."""
    return normalized_command_text(text) in CONTEXTUAL_APPROVALS


def orchestration_state_from_dict(value: dict[str, Any]) -> OrchestrationState:
    """Parse the JSON shape persisted in session runtime into typed pure state."""
    session_value = value.get("session") if isinstance(value.get("session"), dict) else {}
    expected_value = session_value.get("expected_transition")
    expected = (
        ExpectedTransition(
            kind=str(expected_value.get("kind") or ""),
            task_id=str(expected_value.get("task_id") or ""),
            report_id=str(expected_value.get("report_id") or ""),
            decision_id=str(expected_value.get("decision_id") or ""),
            integration_id=str(expected_value.get("integration_id") or ""),
            revision_id=str(expected_value.get("revision_id") or ""),
        )
        if isinstance(expected_value, dict) and expected_value.get("kind")
        else None
    )
    task_value = value.get("task") if isinstance(value.get("task"), dict) else None
    worker_value = (
        value.get("worker_runtime")
        if isinstance(value.get("worker_runtime"), dict)
        else {}
    )
    integration_value = (
        value.get("integration_runtime")
        if isinstance(value.get("integration_runtime"), dict)
        else {}
    )
    decision_value = (
        value.get("pending_decision")
        if isinstance(value.get("pending_decision"), dict)
        else {}
    )
    return OrchestrationState(
        session=SessionFlowState(
            session_id=str(session_value.get("session_id") or value.get("session_id") or ""),
            role=str(session_value.get("role") or "neutral"),
            host=str(session_value.get("host") or "unknown"),
            phase=str(session_value.get("phase") or "planning"),
            expected_transition=expected,
        ),
        task=(
            TaskFlowState(
                task_id=str(task_value.get("task_id") or ""),
                lifecycle=str(task_value.get("lifecycle") or "draft"),
                attempt=int(task_value.get("attempt") or 1),
                worker_authorized=task_value.get("worker_authorized") is True,
                run_report=str(task_value.get("run_report") or ""),
            )
            if task_value is not None
            else None
        ),
        worker_runtime=WorkerRuntimeState(
            claim_id=str(worker_value.get("claim_id") or ""),
            branch=str(worker_value.get("branch") or ""),
            worktree=str(worker_value.get("worktree") or ""),
            host_window_or_thread_id=str(
                worker_value.get("host_window_or_thread_id") or ""
            ),
            active_task_id=str(worker_value.get("active_task_id") or ""),
            active_revision_id=str(worker_value.get("active_revision_id") or ""),
            previous_task_id=str(worker_value.get("previous_task_id") or ""),
            previous_claim_id=str(worker_value.get("previous_claim_id") or ""),
            worker_session_id=str(worker_value.get("worker_session_id") or ""),
            worker_availability=str(
                worker_value.get("worker_availability") or "unknown"
            ),
            binding_status=str(worker_value.get("binding_status") or "unbound"),
            allowed_scope=tuple(string_list(worker_value.get("allowed_scope"))),
            validation_plan=tuple(string_list(worker_value.get("validation_plan"))),
            execution_ownership=str(
                worker_value.get("execution_ownership") or ""
            ),
        ),
        integration_runtime=IntegrationRuntimeState(
            lease_id=str(integration_value.get("lease_id") or ""),
            integration_id=str(integration_value.get("integration_id") or ""),
            base_branch=str(integration_value.get("base_branch") or ""),
            worktree=str(integration_value.get("worktree") or ""),
            selected_task_ids=tuple(string_list(integration_value.get("selected_task_ids"))),
            selected_reports=tuple(string_list(integration_value.get("selected_reports"))),
            revision_id=str(integration_value.get("revision_id") or ""),
        ),
        pending_decision=PendingDecisionState(
            decision_id=str(decision_value.get("decision_id") or ""),
            kind=str(decision_value.get("kind") or ""),
            options=tuple(string_list(decision_value.get("options"))),
            recommended_option=str(decision_value.get("recommended_option") or ""),
        ),
        candidate_task_ids=tuple(string_list(value.get("candidate_task_ids"))),
    )


def orchestration_state_to_dict(state: OrchestrationState) -> dict[str, Any]:
    return asdict(state)


def flow_plan_to_dict(plan: FlowPlan) -> dict[str, Any]:
    return asdict(plan)


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


def canonical_revision_id(value: Any) -> str:
    """Return an exact Task Revision ID such as 012-r1, never a prefix match."""
    candidate = str(value or "").strip().lower()
    return candidate if REVISION_ID_RE.fullmatch(candidate) else ""


def revision_id_parts(value: Any) -> tuple[str, int]:
    revision_id = canonical_revision_id(value)
    if not revision_id:
        raise ValueError("Revision ID must match ^\\d{3,}[a-z]*-r[1-9]\\d*$")
    match = REVISION_ID_RE.fullmatch(revision_id)
    assert match is not None
    return match.group("task_id"), int(match.group("revision_number"))


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


def competitive_candidate_ids(
    root_task_id: Any, used_task_ids: Iterable[str], candidate_count: int
) -> list[str]:
    """Allocate the next non-reused follow-up IDs for a competitive group."""
    number, suffix = task_id_parts(root_task_id)
    if suffix:
        raise ValueError("Competitive root must be a numeric Task ID")
    used = {canonical_task_id(item) for item in used_task_ids}
    used_indexes = [
        suffix_index(task_id_parts(item)[1])
        for item in used
        if item and task_id_parts(item)[0] == number and task_id_parts(item)[1]
    ]
    next_index = max(used_indexes, default=0) + 1
    candidates: list[str] = []
    while len(candidates) < candidate_count:
        candidate_id = followup_task_id(number, next_index)
        next_index += 1
        if candidate_id not in used:
            candidates.append(candidate_id)
    return candidates


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


def normalized_command_text(text: str) -> str:
    candidate = text.strip().lower().strip("\"'“”‘’`").strip()
    candidate = re.sub(r"[。.!！？?；;，,、：:…]+$", "", candidate).strip()
    return candidate.strip("\"'“”‘’`").strip()


def parse_task_command(text: str) -> Optional[dict[str, Any]]:
    """Parse one exact natural-language Task command without fuzzy execution."""
    candidate = normalized_command_text(text)
    competitive = re.fullmatch(
        r"让\s*(?:两个|2\s*个)\s*agent\s*分别执行\s*(\d{3,}[a-z]*)"
        r"(?:号)?(?:任务)?[，,]?\s*最后比较谁做得好",
        candidate,
    )
    if competitive:
        return {
            "action": "competitive",
            "task_id": canonical_task_id(competitive.group(1)),
            "candidate_count": 2,
            "authorizes_execution": True,
        }
    family = re.fullmatch(r"查看\s*(\d{3,}[a-z]*)\s*系列任务", candidate)
    if family:
        task_id = canonical_task_id(family.group(1))
        return {"action": "family", "task_id": task_id, "authorizes_execution": False}

    action_pattern = "|".join(
        sorted((re.escape(item) for item in TASK_COMMANDS), key=len, reverse=True)
    )
    match = re.fullmatch(
        rf"(?P<action>{action_pattern})\s*(?P<task_id>\d{{3,}}[a-z]*)"
        rf"(?:\s*(?:号\s*)?任务)?",
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


LOW_RISK_LEADING_POLITENESS_RE = re.compile(
    r"^(?:(?:请帮我|麻烦帮我|请问|劳烦你|劳烦|请你|麻烦你|请|麻烦|帮我|能否|可否|可以|"
    r"please\s+help\s+me|please|could\s+you|can\s+you)\s*)+",
    re.IGNORECASE,
)
LOW_RISK_TRAILING_POLITENESS_RE = re.compile(
    r"(?:\s*[,，、]?\s*(?:谢谢你|谢谢|拜托了?|好吗|可以吗|行吗|吗|呢|吧|please))+$",
    re.IGNORECASE,
)


def normalized_low_risk_command_text(text: str) -> str:
    """Normalize bounded read-only entry commands without loosening authority."""
    candidate = text.strip().casefold()
    candidate = candidate.strip("\"'“”‘’`").strip()
    candidate = re.sub(r"\s+", " ", candidate)
    candidate = re.sub(r"[。.!！？?；;，,、：:…]+$", "", candidate).strip()
    candidate = LOW_RISK_LEADING_POLITENESS_RE.sub("", candidate).strip()
    candidate = LOW_RISK_TRAILING_POLITENESS_RE.sub("", candidate).strip()
    candidate = re.sub(r"[。！？!?；;，,、：:]+$", "", candidate).strip()
    candidate = candidate.replace("一下", "")
    return re.sub(r"\s+", "", candidate.strip("\"'“”‘’`").strip())


DISCUSSION_ENTRY_COMMANDS = {
    "开始讨论",
    "进入讨论",
    "进入讨论模式",
    "开启讨论",
    "开启讨论模式",
    "回到讨论",
    "回到讨论模式",
    "回到discussion",
    "继续讨论",
    "继续讨论模式",
    "startdiscussion",
    "enterdiscussion",
    "resumediscussion",
    "returntodiscussion",
    "backtodiscussion",
}
STATUS_REFRESH_COMMANDS = {
    "刷新项目状态",
    "刷新状态",
    "查看项目状态",
    "项目状态",
    "重新加载项目状态",
    "重载项目状态",
    "refreshprojectstatus",
    "refreshstatus",
    "showprojectstatus",
    "reloadprojectstatus",
}


def parse_user_prompt(text: str) -> Optional[dict[str, Any]]:
    """Parse bounded low-risk aliases, then exact authority-bearing commands."""
    candidate = normalized_low_risk_command_text(text)
    if candidate in DISCUSSION_ENTRY_COMMANDS:
        return {"action": "start_discussion", "authorizes_execution": False}
    if candidate in STATUS_REFRESH_COMMANDS:
        return {"action": "refresh_project_status", "authorizes_execution": False}
    return parse_task_command(text)


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
        raw_revision_id = data.get("revision_id")
        revision_id = (
            "" if raw_revision_id is None else canonical_revision_id(raw_revision_id)
        )
        if raw_revision_id is not None and raw_revision_id != "" and not revision_id:
            block_errors.append(
                "revision_id must be null or match ^\\d{3,}[a-z]*-r[1-9]\\d*$"
            )
        if revision_id:
            revision_parent, _ = revision_id_parts(revision_id)
            if task_id != revision_parent:
                block_errors.append("revision_id parent must equal task_id")
        attempt = positive_attempt(data.get("attempt", 1), block_errors)
        execution_mode = normalized_string(data.get("execution_mode"), "exclusive")
        changed_paths = string_list(data.get("changed_paths"))
        risk_values = [
            data.get("public_api_change"),
            data.get("schema_change"),
            data.get("persistence_change"),
            data.get("security_impact"),
            data.get("permission_change"),
            data.get("billing_impact"),
            data.get("deletion_change"),
            data.get("migration_change"),
            data.get("dependency_change"),
            data.get("cross_module_contract_change"),
        ]
        change_class = normalized_string(data.get("change_class"), "formal")
        if change_class == "revision":
            risk_values.append(data.get("privacy_impact"))
        risk_flags_known = all(isinstance(value, bool) for value in risk_values)
        risk_flags_clear = risk_flags_known and not any(risk_values)
        raw_candidate_score = data.get("candidate_score")
        candidate_score = (
            float(raw_candidate_score)
            if isinstance(raw_candidate_score, (int, float))
            and not isinstance(raw_candidate_score, bool)
            else None
        )
        selection_requires_judgment = data.get("selection_requires_judgment") is True
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
        revision_id = ""
        attempt = 1
        execution_mode = "exclusive"
        changed_paths = []
        risk_flags_known = False
        risk_flags_clear = False
        change_class = "formal"
        candidate_score = None
        selection_requires_judgment = False
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
        revision_id=revision_id,
        attempt=attempt,
        execution_mode=execution_mode,
        changed_paths=changed_paths,
        risk_flags_known=risk_flags_known,
        risk_flags_clear=risk_flags_clear,
        change_class=change_class,
        candidate_score=candidate_score,
        selection_requires_judgment=selection_requires_judgment,
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


def parse_revision_state(revision_path: str, content: str) -> RevisionState:
    """Parse the deliberately small durable record for one Task Revision."""
    block, block_errors = parse_workflow_block(content, "revision")
    errors = list(block_errors)
    if block is None:
        return RevisionState(
            path=revision_path,
            revision_id="",
            parent_task_id="",
            status="missing",
            user_request="",
            allowed_scope=[],
            validation_plan=[],
            run_report="",
            worker_creation_authorized=False,
            errors=["Task Revision requires a wishgraph:revision-state block"],
            state_source="legacy",
        )

    data = block.data
    revision_id = canonical_revision_id(data.get("revision_id"))
    if not revision_id:
        errors.append("revision_id must match ^\\d{3,}[a-z]*-r[1-9]\\d*$")
    parent_task_id = canonical_task_id(data.get("parent_task_id"))
    if not parent_task_id:
        errors.append("parent_task_id must match ^\\d{3,}[a-z]*$")
    if revision_id and parent_task_id:
        encoded_parent, _ = revision_id_parts(revision_id)
        if encoded_parent != parent_task_id:
            errors.append("revision_id parent must equal parent_task_id")

    status = normalized_string(data.get("status"))
    if status not in {"pending", "running", "completed", "blocked", "integrated"}:
        errors.append(
            "revision status must be pending, running, completed, blocked, or integrated"
        )
    user_request = str(data.get("user_request") or "").strip()
    if not user_request:
        errors.append("user_request must be non-empty")
    allowed_scope = string_list(data.get("allowed_scope"))
    if not allowed_scope:
        errors.append("allowed_scope must contain at least one path or glob")
    validation_plan = string_list(data.get("validation_plan"))
    if not validation_plan:
        errors.append("validation_plan must contain at least one targeted check")
    run_report = normalize_cell(str(data.get("run_report") or ""))
    worker_authorized = data.get("worker_creation_authorized") is True
    if data.get("worker_creation_authorized") is not True:
        errors.append("worker_creation_authorized must be true for a routed revision")

    return RevisionState(
        path=revision_path,
        revision_id=revision_id,
        parent_task_id=parent_task_id,
        status=status,
        user_request=user_request,
        allowed_scope=allowed_scope,
        validation_plan=validation_plan,
        run_report=run_report,
        worker_creation_authorized=worker_authorized,
        errors=errors,
    )


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
        execution_mode = normalized_string(data.get("execution_mode"), "exclusive")
        raw_comparison_group = data.get("comparison_group")
        comparison_group = (
            "" if raw_comparison_group is None else str(raw_comparison_group).strip()
        )
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
        execution_mode = "exclusive"
        comparison_group = ""
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
        execution_mode=execution_mode,
        comparison_group=comparison_group,
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
