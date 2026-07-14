"""Policy-evaluation boundary for WishGraph lifecycle and closeout rules."""

from __future__ import annotations

import fnmatch
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from git_state import (
    LEGACY_PROJECT_STATUS_PATH,
    changed_paths,
    configured_task_globs,
    matches_any,
    project_status_candidates,
    read_head_version,
    read_version,
    report_contents_across_refs,
    report_paths_in_ref,
    resolve_project_status_path,
    standard_project_status_conflict,
)
from workflow_state import (
    SCHEMA_VERSION as WORKFLOW_STATE_SCHEMA_VERSION,
    STATE_BLOCK_RE,
    ReportState,
    TaskState,
    dynamic_state_block,
    integrated_report_paths,
    normalized_string,
    parse_impact_rows,
    parse_labeled_field,
    parse_report_state,
    parse_report_status,
    parse_task_state,
    parse_workflow_block,
    without_workflow_block,
)


TEXT_ONLY_SUFFIXES = {".md", ".mdx", ".rst", ".txt"}
ACCEPTED_REPORT_STATUSES = {"completed", "blocked", "incomplete", "done"}
UPDATED_STATUSES = {"updated", "yes"}
INTEGRATE_STATUSES = {"integrate", "needs integration", "review", "proposed"}
NOOP_STATUSES = {"n/a", "na", "not applicable", "no"}
WORK_TYPES = {"discussion", "sequential", "parallel_batch", "high_risk"}
TASK_STATUSES = {
    "draft",
    "approved",
    "running",
    "completed",
    "blocked",
    "incomplete",
    "integrated",
    "reviewed",
}
EXPLICIT_AUTHORIZATIONS = {
    "explicit_user_confirmation",
    "explicit user confirmation",
    "requires explicit user confirmation",
    "user confirmed",
    "explicitly confirmed",
    "用户明确确认",
    "用户已确认",
    "需要用户明确确认",
}
INHERITED_AUTHORIZATIONS = {
    "inherited_task_approval",
    "inherited task approval",
    "task approval",
    "approved with task",
    "随任务批准授权",
    "任务批准",
}
READY_STATUSES = {"ready", "safe to integrate", "integration ready", "就绪", "可集成"}
BLOCKED_READINESS = {
    "blocked",
    "needs decision",
    "requires decision",
    "not ready",
    "阻塞",
    "需要决定",
    "未就绪",
}
PASS_RESULTS = {"pass", "passed", "ok", "n/a", "na", "not applicable", "通过", "不适用"}
FAIL_RESULTS = {"fail", "failed", "not run", "error", "失败", "未运行", "错误"}
TASK_TRANSITIONS = {
    "draft": {"approved"},
    "approved": {"running", "completed", "blocked", "incomplete"},
    "running": {"completed", "blocked", "incomplete"},
    "completed": {"integrated"},
    "blocked": {"approved"},
    "incomplete": {"approved"},
    "integrated": {"reviewed"},
    "reviewed": set(),
}
TASK_ONLY_TRANSITIONS = {
    ("draft", "approved"),
    ("blocked", "approved"),
    ("incomplete", "approved"),
    ("integrated", "reviewed"),
}


@dataclass
class CheckResult:
    trigger_paths: list[str] = field(default_factory=list)
    changed_paths: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class IntegrationState:
    pending_integration: bool = False
    integration_kind: str = "none"
    ready_reports: list[str] = field(default_factory=list)
    waiting_reports: list[str] = field(default_factory=list)
    blocked_reports: list[str] = field(default_factory=list)
    work_units: list[dict[str, Any]] = field(default_factory=list)
    requires_user_confirmation: bool = False
    reason: str = "No worker results are waiting for integration."

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": WORKFLOW_STATE_SCHEMA_VERSION,
            "kind": "integration_status",
            "pending_integration": self.pending_integration,
            "integration_kind": self.integration_kind,
            "ready_reports": self.ready_reports,
            "waiting_reports": self.waiting_reports,
            "blocked_reports": self.blocked_reports,
            "work_units": self.work_units,
            "requires_user_confirmation": self.requires_user_confirmation,
            "reason": self.reason,
        }


def shared_memory_paths(config: dict[str, Any]) -> set[str]:
    return set(config.get("required_impact_rows", [])) | set(
        project_status_candidates(config)
    )


def report_state(report_path: str, content: str) -> ReportState:
    state = parse_report_state(report_path, content)
    errors = state.safety_errors
    if state.work_type not in WORK_TYPES:
        errors.append("missing or invalid work type")
    if state.work_type == "parallel_batch" and state.batch_id in {
        "",
        "n/a",
        "na",
        "none",
        "无",
    }:
        errors.append("parallel_batch requires a batch ID")
    if state.work_type in {"parallel_batch", "high_risk"}:
        if state.authorization not in EXPLICIT_AUTHORIZATIONS:
            errors.append(
                "parallel or high-risk work requires explicit integration authorization"
            )
    elif state.authorization not in EXPLICIT_AUTHORIZATIONS | INHERITED_AUTHORIZATIONS:
        errors.append("missing or invalid integration authorization")
    if state.readiness not in READY_STATUSES | BLOCKED_READINESS:
        errors.append("missing or invalid integration readiness")

    if state.status in {"completed", "done"}:
        if state.readiness not in READY_STATUSES:
            errors.append("completed work is not marked integration-ready")
        if not state.validation_results:
            errors.append("completed work has no machine-readable validation results")
        elif any(
            result in FAIL_RESULTS or result not in PASS_RESULTS
            for result in state.validation_results
        ):
            errors.append("completed work has failed, unrun, or unknown validation results")
        if state.scope_check not in PASS_RESULTS:
            errors.append("scope check did not pass")
        if state.conflict_status not in {"none", "no", "clear", "无", "无冲突"}:
            errors.append("an unresolved conflict is present")
        if state.new_decision not in {"no", "none", "false", "无", "否"}:
            errors.append("a new product, architecture, or data decision requires review")
    return state


def task_state(task_path: str, content: str) -> TaskState:
    state = parse_task_state(task_path, content)
    errors = state.errors
    if not state.task_id:
        errors.append("missing task_id")
    if state.status not in TASK_STATUSES:
        errors.append("missing or invalid task status")
    if state.work_type not in WORK_TYPES - {"discussion"}:
        errors.append("missing or invalid task work type")
    if state.work_type == "parallel_batch" and state.batch_id in {
        "",
        "n/a",
        "na",
        "none",
        "无",
    }:
        errors.append("parallel_batch task requires a batch ID")
    if not state.run_report:
        errors.append("missing run_report")
    if state.status == "draft" and state.worker_creation_authorized:
        errors.append("draft task cannot authorize Worker creation")
    if state.status != "draft" and not state.worker_creation_authorized:
        errors.append(
            f"{state.status} task requires explicit Worker creation authorization"
        )
    if state.work_type in {"parallel_batch", "high_risk"}:
        if state.integration_policy != "requires_explicit_user_confirmation":
            errors.append(
                "parallel or high-risk task requires explicit integration confirmation policy"
            )
    elif state.integration_policy not in {
        "inherited_task_approval",
        "requires_explicit_user_confirmation",
    }:
        errors.append("missing or invalid integration policy")
    return state


def task_report_states(
    root: Path, config: dict[str, Any], scope: str = "worktree"
) -> dict[str, TaskState]:
    tasks: dict[str, TaskState] = {}
    seen: set[Path] = set()
    for task_glob in configured_task_globs(config):
        for path in root.glob(task_glob):
            if path in seen:
                continue
            seen.add(path)
            if path.name.startswith("EXAMPLE-") or path.name.startswith("NNN-"):
                continue
            relative = path.relative_to(root).as_posix()
            content = read_version(root, relative, scope)
            if content is None:
                continue
            state = task_state(relative, content)
            if not state.run_report:
                continue
            tasks[state.run_report] = state
    return tasks


def integration_state(root: Path, config: dict[str, Any]) -> IntegrationState:
    reports = report_contents_across_refs(root, config)
    prefix = config["paths"]["run_report_glob"].split("*", 1)[0].rstrip("/")
    settled = report_paths_in_ref(root, "HEAD", prefix)
    overview_path = resolve_project_status_path(root, config)
    overview = read_version(root, overview_path, "worktree") or ""
    settled |= integrated_report_paths(overview, config["paths"]["run_report_glob"])

    pending_states = [
        report_state(path, content)
        for path, content in sorted(reports.items())
        if path not in settled
    ]
    ready = sorted(
        state.path
        for state in pending_states
        if state.status in {"completed", "done"} and not state.safety_errors
    )
    blocked = sorted(
        state.path
        for state in pending_states
        if state.status not in {"completed", "done"} or state.safety_errors
    )
    tasks = task_report_states(root, config)
    waiting = sorted(
        path
        for path, task in tasks.items()
        if path not in reports
        and path not in settled
        and (
            task.status in {"approved", "running"}
            or (task.state_source == "legacy" and task.status == "draft")
        )
    )

    work_types = {
        state.work_type for state in pending_states if state.work_type in WORK_TYPES
    }
    work_types.update(
        state.work_type
        for path, state in tasks.items()
        if path in waiting and state.work_type in WORK_TYPES
    )
    if "high_risk" in work_types:
        kind = "high_risk"
    elif "parallel_batch" in work_types or len(ready) + len(blocked) > 1:
        kind = "parallel_batch"
    elif "sequential" in work_types:
        kind = "sequential"
    else:
        kind = "none"

    pending = bool(ready or blocked)
    confirmation = kind in {"parallel_batch", "high_risk"} or bool(blocked)
    if blocked:
        reason = "Blocked or unsafe worker results require discussion and user review."
    elif kind == "parallel_batch" and waiting:
        reason = "Parallel batch still has planned workers waiting; review before partial integration."
    elif kind == "parallel_batch" and ready:
        reason = "Parallel worker results are ready; explicit user integration approval is required."
    elif kind == "sequential" and ready:
        reason = "A safe sequential result is ready under the task approval's integration authority."
    elif waiting:
        reason = "Planned workers have not produced run reports yet."
    else:
        reason = "No worker results are waiting for integration."
    work_units: list[dict[str, Any]] = []
    for report_path, task in sorted(tasks.items(), key=lambda item: item[1].path):
        if task.status == "reviewed":
            lifecycle = "reviewed"
        elif report_path in settled:
            lifecycle = "integrated"
        elif report_path in reports:
            report = report_state(report_path, reports[report_path])
            lifecycle = (
                "completed"
                if report.status in {"completed", "done"} and not report.safety_errors
                else "blocked"
            )
        else:
            lifecycle = task.status
        work_units.append(
            {
                "task_path": task.path,
                "task_id": task.task_id,
                "lifecycle_status": lifecycle,
                "task_status": task.status,
                "work_type": task.work_type,
                "run_report": report_path,
                "worker_creation_authorized": task.worker_creation_authorized,
                "integration_policy": task.integration_policy,
                "state_source": task.state_source,
                "errors": task.errors,
            }
        )

    return IntegrationState(
        pending_integration=pending,
        integration_kind=kind,
        ready_reports=ready,
        waiting_reports=waiting,
        blocked_reports=blocked,
        work_units=work_units,
        requires_user_confirmation=confirmation,
        reason=reason,
    )


def is_substantive(path: str, config: dict[str, Any]) -> bool:
    stateful = {
        config["paths"]["prd"],
        config["paths"]["architecture"],
        config["paths"]["codemap"],
        config["paths"]["conventions"],
        config["paths"]["execution_prompt"],
    }
    if path in stateful or any(
        fnmatch.fnmatch(path, pattern) for pattern in configured_task_globs(config)
    ):
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
    state = report_state(report_path, content)
    for error in state.safety_errors:
        if error.startswith("wishgraph:") or error.startswith("must contain exactly"):
            result.errors.append(f"{report_path} {error}")
    if state.work_type not in WORK_TYPES:
        result.errors.append(
            f"{report_path} must set Work type/工作类型 to discussion, sequential, parallel_batch, or high_risk"
        )
    if state.work_type == "parallel_batch" and state.batch_id in {
        "",
        "n/a",
        "na",
        "none",
        "无",
    }:
        result.errors.append(f"{report_path} parallel_batch requires Batch ID/批次 ID")
    if state.readiness not in READY_STATUSES | BLOCKED_READINESS:
        result.errors.append(
            f"{report_path} must set Integration readiness/集成就绪状态"
        )
    if state.status in {"completed", "done"} and state.safety_errors:
        result.errors.append(
            f"{report_path} cannot be Completed and integration-ready: "
            + "; ".join(state.safety_errors)
        )
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


def validate_project_status_limits(
    config: dict[str, Any], status_path: str, content: str, result: CheckResult
) -> None:
    line_limit = int(config.get("project_status_max_lines", 160))
    char_limit = int(config.get("project_status_max_chars", 12000))
    line_count = len(content.splitlines())
    if line_count > line_limit:
        result.errors.append(
            f"{status_path} has {line_count} lines; limit is {line_limit}. Rewrite the "
            "current snapshot more concisely and move historical detail to reports/runs/*.md. "
            "Do not remove unresolved risks, conflicts, or pending decisions."
        )
    if len(content) > char_limit:
        result.errors.append(
            f"{status_path} has {len(content)} characters; limit is {char_limit}. Rewrite "
            "the current snapshot more concisely and move historical detail to "
            "reports/runs/*.md. Do not remove unresolved risks, conflicts, or pending decisions."
        )


def validate_single_current_snapshot(
    status_path: str, content: str, result: CheckResult
) -> None:
    current_headings = re.findall(
        r"(?mi)^##\s+(?:Current Integration|当前集成)\s*$", content
    )
    if len(current_headings) != 1:
        result.errors.append(
            f"{status_path} must contain exactly one Current Integration/当前集成 section. "
            "Rewrite the current snapshot instead of appending integration history."
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
    overview_path = resolve_project_status_path(root, config, scope)
    discussion_path = paths["discussion_prompt"]
    overview = read_version(root, overview_path, scope)
    if overview is None:
        result.errors.append(f"Cannot read the {scope} version of {overview_path}")
        return
    validate_status(result, overview_path, overview)
    validate_project_status_limits(config, overview_path, overview, result)
    validate_single_current_snapshot(overview_path, overview, result)

    report_states: list[ReportState] = []
    for report_path in run_reports:
        report_content = read_version(root, report_path, scope)
        if report_content is not None:
            report_states.append(report_state(report_path, report_content))
    integration_kind = parse_labeled_field(
        overview, "Integration kind", "集成类型"
    )
    authorization = parse_labeled_field(
        overview, "Authorization", "授权"
    )
    integration_block, integration_block_errors = parse_workflow_block(
        overview, "integration"
    )
    for error in integration_block_errors:
        result.errors.append(f"{overview_path} {error}")
    if integration_block is not None:
        integration_id = normalized_string(
            integration_block.data.get("integration_id")
        )
        if integration_id == "missing":
            result.errors.append(
                f"{overview_path} wishgraph:integration-state requires integration_id"
            )
        integration_kind = normalized_string(
            integration_block.data.get("integration_kind")
        )
        authorization = normalized_string(integration_block.data.get("authorization"))
    expected_kind = "sequential"
    if any(state.work_type == "high_risk" for state in report_states):
        expected_kind = "high_risk"
    elif any(state.work_type == "parallel_batch" for state in report_states) or len(
        report_states
    ) > 1:
        expected_kind = "parallel_batch"
    if integration_kind != expected_kind:
        result.errors.append(
            f"{overview_path} must set Integration kind/集成类型 to {expected_kind}"
        )
    if expected_kind in {"parallel_batch", "high_risk"}:
        if authorization not in EXPLICIT_AUTHORIZATIONS:
            result.errors.append(
                f"{overview_path} requires explicit user confirmation before {expected_kind} integration"
            )
    elif authorization not in EXPLICIT_AUTHORIZATIONS | INHERITED_AUTHORIZATIONS:
        result.errors.append(
            f"{overview_path} must record inherited task approval or explicit user confirmation"
        )
    for state in report_states:
        if state.status not in {"completed", "done"} or state.safety_errors:
            result.errors.append(
                f"Integration cannot absorb unsafe report {state.path}: "
                + "; ".join(state.safety_errors or [f"status is {state.status}"])
            )

    tasks = task_report_states(root, config, scope)
    for report_path in run_reports:
        task = tasks.get(report_path)
        if task is not None and task.state_source == "structured" and task.status != "integrated":
            result.errors.append(
                f"{task.path} must move task status to integrated when absorbing {report_path}"
            )

    listed_reports = integrated_report_paths(overview, paths["run_report_glob"])
    for report_path in run_reports:
        if report_path not in listed_reports:
            result.errors.append(
                f"{overview_path} must list integrated run report {report_path}"
            )
    historical_reports = sorted(listed_reports - set(run_reports))
    if historical_reports:
        result.errors.append(
            f"{overview_path} must list only reports absorbed by this integration; move "
            "historical execution detail to reports/runs/*.md and Git history. Extra paths: "
            + ", ".join(historical_reports)
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
    elif len(current_state.splitlines()) > int(
        config.get("discussion_dynamic_max_lines", 30)
    ):
        result.errors.append(
            f"{discussion_path} dynamic wishgraph:state block exceeds "
            f"{int(config.get('discussion_dynamic_max_lines', 30))} lines. Keep only the "
            "current discussion focus, results to present, pending decisions, next action, "
            f"and a pointer to {overview_path}."
        )


def validate_task_spec(
    root: Path,
    config: dict[str, Any],
    scope: str,
    task_path: str,
    result: CheckResult,
) -> Optional[TaskState]:
    content = read_version(root, task_path, scope)
    if content is None:
        result.errors.append(f"Cannot read the {scope} version of {task_path}")
        return None
    state = task_state(task_path, content)
    for error in state.errors:
        result.errors.append(f"{task_path} {error}")
    if state.run_report and not fnmatch.fnmatch(
        state.run_report, config["paths"]["run_report_glob"]
    ):
        result.errors.append(
            f"{task_path} run_report must match {config['paths']['run_report_glob']}"
        )

    previous_content = read_head_version(root, task_path)
    if previous_content is not None:
        previous_block, previous_errors = parse_workflow_block(previous_content, "task")
        current_block, current_errors = parse_workflow_block(content, "task")
        if (
            previous_block is not None
            and current_block is not None
            and not previous_errors
            and not current_errors
        ):
            previous = task_state(task_path, previous_content)
            transition = (previous.status, state.status)
            draft_revision = transition == ("draft", "draft")
            if not draft_revision:
                if previous.task_id != state.task_id:
                    result.errors.append(f"{task_path} task_id is immutable after approval")
                stable_fields = (
                    ("work_type", previous.work_type, state.work_type),
                    ("batch_id", previous.batch_id, state.batch_id),
                    (
                        "integration_policy",
                        previous.integration_policy,
                        state.integration_policy,
                    ),
                )
                for field_name, old_value, new_value in stable_fields:
                    if old_value != new_value:
                        result.errors.append(
                            f"{task_path} {field_name} is immutable after approval"
                        )
                if transition in {("blocked", "approved"), ("incomplete", "approved")}:
                    if previous.run_report == state.run_report:
                        result.errors.append(
                            f"{task_path} retry approval requires a new immutable run_report path"
                        )
                elif previous.run_report != state.run_report:
                    result.errors.append(
                        f"{task_path} run_report may change only when retrying blocked or incomplete work"
                    )
            if previous.status != state.status and state.status not in TASK_TRANSITIONS.get(
                previous.status, set()
            ):
                result.errors.append(
                    f"{task_path} has invalid task transition {previous.status} -> {state.status}"
                )

    if state.status in {"completed", "blocked", "incomplete", "integrated", "reviewed"}:
        if read_version(root, state.run_report, scope) is None:
            result.errors.append(
                f"{task_path} status {state.status} requires run report {state.run_report}"
            )
    if state.status in {"integrated", "reviewed"}:
        prefix = config["paths"]["run_report_glob"].split("*", 1)[0].rstrip("/")
        settled = report_paths_in_ref(root, "HEAD", prefix)
        overview_path = resolve_project_status_path(root, config, scope)
        overview = read_version(root, overview_path, scope) or ""
        settled |= integrated_report_paths(
            overview, config["paths"]["run_report_glob"]
        )
        if state.run_report not in settled:
            result.errors.append(
                f"{task_path} status {state.status} requires {state.run_report} to be integrated"
            )
    return state


def task_state_only_change(
    root: Path, scope: str, task_path: str, state: TaskState
) -> bool:
    content = read_version(root, task_path, scope)
    previous_content = read_head_version(root, task_path)
    if content is None:
        return False
    if previous_content is None:
        return state.state_source == "structured" and state.status == "draft" and not state.errors
    previous_block, previous_errors = parse_workflow_block(previous_content, "task")
    current_block, current_errors = parse_workflow_block(content, "task")
    if (
        previous_block is None
        or current_block is None
        or previous_errors
        or current_errors
        or state.errors
    ):
        return False
    previous = task_state(task_path, previous_content)
    transition = (previous.status, state.status)
    if transition == ("draft", "draft"):
        return (
            previous.state_source == "structured"
            and not previous.worker_creation_authorized
            and not state.worker_creation_authorized
        )
    return (
        transition in TASK_ONLY_TRANSITIONS
        and without_workflow_block(previous_content, "task")
        == without_workflow_block(content, "task")
    )


def discussion_state_only_change(root: Path, scope: str, discussion_path: str) -> bool:
    content = read_version(root, discussion_path, scope)
    previous_content = read_head_version(root, discussion_path)
    if content is None or previous_content is None:
        return False
    current_state = dynamic_state_block(content)
    previous_state = dynamic_state_block(previous_content)
    if current_state is None or previous_state is None or current_state == previous_state:
        return False
    return STATE_BLOCK_RE.sub("", content).strip() == STATE_BLOCK_RE.sub(
        "", previous_content
    ).strip()


def check_sync(root: Path, config: dict[str, Any], scope: str) -> CheckResult:
    result = CheckResult()
    if standard_project_status_conflict(root, scope):
        result.errors.append(
            "Both reports/PROJECT_STATUS.md and reports/DEV_REPORT.md exist. Confirm the "
            "authoritative current facts, migrate with git mv when appropriate, and keep only "
            "reports/PROJECT_STATUS.md; strict mode cannot continue with two status sources."
        )
    overview_path = resolve_project_status_path(root, config, scope)
    if overview_path == LEGACY_PROJECT_STATUS_PATH:
        result.warnings.append(
            "Legacy status file reports/DEV_REPORT.md is still in use. Read its current "
            "snapshot, rename it with git mv to reports/PROJECT_STATUS.md, update project "
            "references, and do not maintain both names."
        )
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
    discussion_path = paths["discussion_prompt"]
    run_report_glob = paths["run_report_glob"]
    run_reports = sorted(path for path in changed if fnmatch.fnmatch(path, run_report_glob))
    task_paths = sorted(
        path
        for path in changed
        if any(fnmatch.fnmatch(path, pattern) for pattern in configured_task_globs(config))
        and not Path(path).name.startswith(("EXAMPLE-", "NNN-"))
    )
    validated_tasks: dict[str, TaskState] = {}
    for task_path in task_paths:
        state = validate_task_spec(root, config, scope, task_path, result)
        if state is not None:
            validated_tasks[task_path] = state
    lifecycle_paths = set(task_paths)
    if discussion_path in changed:
        lifecycle_paths.add(discussion_path)
    if task_paths and set(changed) == lifecycle_paths and all(
        task_path in validated_tasks
        and task_state_only_change(root, scope, task_path, validated_tasks[task_path])
        for task_path in task_paths
    ) and (
        discussion_path not in changed
        or discussion_state_only_change(root, scope, discussion_path)
    ):
        return result
    trigger_paths = [
        path
        for path in changed
        if path not in set(project_status_candidates(config)) | {discussion_path}
        and path not in run_reports
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

    tasks_by_report = task_report_states(root, config, scope)
    for report_path in run_reports:
        task = tasks_by_report.get(report_path)
        if task is None or task.state_source != "structured":
            continue
        report_content = read_version(root, report_path, scope)
        if report_content is None:
            continue
        report = report_state(report_path, report_content)
        expected_task_status = {
            "completed": "completed",
            "done": "completed",
            "blocked": "blocked",
            "incomplete": "incomplete",
        }.get(report.status)
        if expected_task_status and task.status != expected_task_status:
            result.errors.append(
                f"{task.path} must set task status to {expected_task_status} for {report_path}"
            )

    return result
