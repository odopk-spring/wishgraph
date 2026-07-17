"""Policy-evaluation boundary for WishGraph lifecycle and closeout rules."""

from __future__ import annotations

import fnmatch
import re
import subprocess
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Optional

from git_state import (
    LEGACY_PROJECT_STATUS_PATH,
    changed_path_statuses,
    changed_paths,
    configured_revision_glob,
    configured_task_globs,
    inspect_claims,
    matches_any,
    project_status_candidates,
    read_head_version,
    read_version,
    report_contents_across_refs,
    report_contents_for_paths_across_refs,
    report_paths_in_ref,
    resolve_project_status_path,
    standard_project_status_conflict,
)
from workflow_state import (
    SCHEMA_VERSION as WORKFLOW_STATE_SCHEMA_VERSION,
    STATE_BLOCK_RE,
    ReportState,
    RevisionState,
    FlowPlan,
    HostCapability,
    OrchestrationState,
    TaskState,
    UserEvent,
    canonical_revision_id,
    canonical_task_id,
    dynamic_state_block,
    integrated_report_paths,
    markdown_section,
    normalized_string,
    parse_impact_rows,
    parse_labeled_field,
    parse_report_state,
    parse_report_status,
    parse_revision_state,
    parse_task_command,
    parse_task_state,
    parse_workflow_block,
    without_workflow_block,
    is_contextual_approval,
)


TEXT_ONLY_SUFFIXES = {".md", ".mdx", ".rst", ".txt"}
ACCEPTED_REPORT_STATUSES = {
    "completed",
    "blocked",
    "incomplete",
    "done",
    "rejected",
    "abandoned",
    "superseded",
    "cancelled",
}
UPDATED_STATUSES = {"updated", "yes"}
INTEGRATE_STATUSES = {"integrate", "needs integration", "review", "proposed"}
NOOP_STATUSES = {"n/a", "na", "not applicable", "no"}
WORK_TYPES = {"discussion", "sequential", "parallel_batch", "high_risk"}
EXECUTION_MODES = {"exclusive", "parallel_independent", "competitive"}
TASK_STATUSES = {
    "draft",
    "approved",
    "running",
    "completed",
    "blocked",
    "incomplete",
    "integrated",
    "reviewed",
    "rejected",
    "abandoned",
    "superseded",
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
    "draft": {"approved", "cancelled"},
    "approved": {"running", "completed", "blocked", "incomplete"},
    "running": {"completed", "blocked", "incomplete", "rejected", "abandoned"},
    "completed": {"integrated", "rejected", "superseded"},
    "blocked": {"approved", "abandoned"},
    "incomplete": {"approved", "abandoned"},
    "rejected": {"approved"},
    "abandoned": {"approved"},
    "superseded": set(),
    "cancelled": set(),
    "integrated": {"reviewed"},
    "reviewed": set(),
}
TASK_ONLY_TRANSITIONS = {
    ("draft", "approved"),
    ("blocked", "approved"),
    ("incomplete", "approved"),
    ("rejected", "approved"),
    ("abandoned", "approved"),
    ("integrated", "reviewed"),
    ("draft", "cancelled"),
}


def _expected_patch(
    kind: str,
    task_id: str,
    *,
    report_id: str = "",
    decision_id: str = "",
    integration_id: str = "",
    revision_id: str = "",
) -> dict[str, str]:
    return {
        "kind": kind,
        "task_id": task_id,
        "report_id": report_id,
        "decision_id": decision_id,
        "integration_id": integration_id,
        "revision_id": revision_id,
    }


def _manual_worker_plan(task_id: str, reason: str) -> FlowPlan:
    return FlowPlan(
        accepted=True,
        next_action="show_manual_worker_command",
        task_id=task_id,
        host_route="manual_window",
        user_message=f"执行 {task_id} 任务",
        stop_after_action=True,
        denial_reason=reason,
        state_patch={
            "session": {
                "phase": "waiting_for_user_launch",
                "expected_transition": _expected_patch(
                    "launch_worker_manually", task_id
                ),
            }
        },
    )


def _role_denial(task_id: str, reason: str) -> FlowPlan:
    return FlowPlan(
        accepted=False,
        next_action="deny_role_violation",
        task_id=task_id,
        denial_reason=reason,
        stop_after_action=True,
    )


REVISION_RISK_FIELDS = (
    "public_api_change",
    "schema_change",
    "persistence_change",
    "migration_change",
    "dependency_change",
    "permission_change",
    "security_impact",
    "privacy_impact",
    "new_product_decision",
)


def _revision_is_lightweight(data: dict[str, Any]) -> bool:
    """Require affirmative scope evidence and explicit negative risk evidence."""
    required_true = (
        "request_is_clear",
        "belongs_to_parent_task",
        "small_scope",
        "independently_revertible",
    )
    return (
        all(data.get(name) is True for name in required_true)
        and all(data.get(name) is False for name in REVISION_RISK_FIELDS)
        and bool(data.get("allowed_scope"))
        and bool(data.get("validation_plan"))
    )


def _manual_revision_plan(
    task_id: str, revision_id: str, reason: str
) -> FlowPlan:
    return FlowPlan(
        accepted=True,
        next_action="fallback_manual_worker_command",
        task_id=task_id,
        revision_id=revision_id,
        host_route="manual_existing_or_recovery_worker",
        user_message=f"在任务 {task_id} 的执行窗口执行修订 {revision_id}",
        stop_after_action=True,
        denial_reason=reason,
        state_patch={
            "session": {
                "phase": "waiting_for_user_launch",
                "expected_transition": _expected_patch("route_revision", task_id),
            }
        },
    )


def reduce_orchestration(
    current_state: OrchestrationState,
    user_event: UserEvent,
    host_capability: HostCapability,
) -> FlowPlan:
    """Purely reduce orchestration state and one event to a unique next action."""
    session = current_state.session
    task = current_state.task
    task_id = task.task_id if task is not None else ""
    data = user_event.data

    if user_event.kind in {"refresh", "inspect"}:
        return FlowPlan(accepted=True, next_action="read_status")

    if user_event.kind == "host_revision_route_failed":
        parent_task_id = str(data.get("parent_task_id") or task_id)
        revision_id = str(data.get("revision_id") or "")
        payload = data.get("work_payload")
        payload = payload if isinstance(payload, dict) else {}
        if revision_id and host_capability.supports_formal_worker_thread:
            return FlowPlan(
                accepted=True,
                next_action="create_lightweight_revision",
                task_id=parent_task_id,
                revision_id=revision_id,
                host_route="automatic_thread",
                work_payload=payload,
                stop_after_action=True,
                denial_reason="existing_worker_route_failed",
            )
        if revision_id:
            return _manual_revision_plan(
                parent_task_id, revision_id, "existing_worker_route_failed"
            )
        return FlowPlan(
            accepted=True,
            next_action="fallback_manual_worker_command",
            task_id=parent_task_id,
            user_message=f"在任务 {parent_task_id} 的执行窗口处理当前反馈",
            stop_after_action=True,
            denial_reason="existing_worker_route_failed",
        )

    if user_event.kind in {"user_requested_revision", "worker_feedback_received"}:
        parent_task_id = str(data.get("parent_task_id") or task_id)
        candidates = tuple(
            str(item) for item in data.get("candidate_parent_task_ids", ()) if item
        )
        if len(candidates) > 1 or (candidates and parent_task_id not in candidates):
            return FlowPlan(
                accepted=False,
                next_action="ask_task_choice",
                task_id=parent_task_id,
                denial_reason="revision_parent_is_ambiguous",
            )
        if task is None or task.task_id != parent_task_id:
            return FlowPlan(
                accepted=False,
                next_action="ask_task_choice",
                task_id=parent_task_id,
                denial_reason="revision_parent_task_not_loaded",
            )
        if not _revision_is_lightweight(data):
            return FlowPlan(
                accepted=True,
                next_action="request_formal_followup_task",
                task_id=parent_task_id,
                stop_after_action=True,
                denial_reason="revision_exceeds_lightweight_boundary",
            )

        request = str(data.get("user_request") or "").strip()
        allowed_scope = [str(item) for item in data.get("allowed_scope", ()) if item]
        validation_plan = [
            str(item) for item in data.get("validation_plan", ()) if item
        ]
        payload = {
            "parent_task_id": parent_task_id,
            "user_request": request,
            "allowed_scope": allowed_scope,
            "validation_plan": validation_plan,
        }
        runtime = current_state.worker_runtime
        active_matches = (
            runtime.active_task_id in {"", parent_task_id}
            and runtime.binding_status in {"bound", "active", "unbound"}
        )
        if task.lifecycle == "running":
            if not active_matches:
                return FlowPlan(
                    accepted=False,
                    next_action="request_formal_followup_task",
                    task_id=parent_task_id,
                    denial_reason="active_worker_is_bound_to_unrelated_task",
                )
            if session.role == "worker" and runtime.claim_id:
                return FlowPlan(
                    accepted=True,
                    next_action="append_feedback_to_active_task",
                    task_id=parent_task_id,
                    target_worker_id=runtime.host_window_or_thread_id,
                    work_payload=payload,
                )
            if session.role == "discussion":
                if host_capability.can_route_worker_thread and runtime.host_window_or_thread_id:
                    return FlowPlan(
                        accepted=True,
                        next_action="route_to_active_worker",
                        task_id=parent_task_id,
                        target_worker_id=runtime.host_window_or_thread_id,
                        work_payload=payload,
                        stop_after_action=True,
                    )
                return FlowPlan(
                    accepted=True,
                    next_action="fallback_manual_worker_command",
                    task_id=parent_task_id,
                    user_message=f"在任务 {parent_task_id} 的执行窗口处理当前反馈",
                    stop_after_action=True,
                    denial_reason="host_cannot_route_to_active_worker",
                )

        if task.lifecycle not in {"completed", "integrated", "reviewed"}:
            return FlowPlan(
                accepted=False,
                next_action="request_formal_followup_task",
                task_id=parent_task_id,
                denial_reason="parent_task_is_not_running_or_terminal",
            )
        revision_number = int(data.get("next_revision_number") or 1)
        revision_id = str(data.get("revision_id") or f"{parent_task_id}-r{revision_number}")
        if not canonical_revision_id(revision_id):
            return FlowPlan(
                accepted=False,
                next_action="request_formal_followup_task",
                task_id=parent_task_id,
                denial_reason="revision_id_is_invalid",
            )
        run_report = str(
            data.get("run_report")
            or f"reports/runs/{revision_id}-attempt-1.md"
        )
        payload["revision_id"] = revision_id
        payload["run_report"] = run_report
        payload["worker_creation_authorized"] = True
        revision_patch = {
            "revision": {
                "revision_id": revision_id,
                "parent_task_id": parent_task_id,
                "status": "pending",
                "user_request": request,
                "allowed_scope": allowed_scope,
                "validation_plan": validation_plan,
                "run_report": run_report,
                "worker_creation_authorized": True,
            }
        }
        reusable_previous = (
            runtime.previous_task_id == parent_task_id
            and runtime.worker_availability in {"idle", "available"}
            and runtime.binding_status in {"released", "unbound", "idle"}
        )
        if (
            reusable_previous
            and host_capability.can_route_worker_thread
            and host_capability.can_reuse_worker_thread
            and runtime.host_window_or_thread_id
        ):
            return FlowPlan(
                accepted=True,
                next_action="route_to_previous_worker",
                task_id=parent_task_id,
                revision_id=revision_id,
                target_worker_id=runtime.host_window_or_thread_id,
                work_payload=payload,
                state_patch=revision_patch,
                stop_after_action=True,
            )
        if host_capability.supports_formal_worker_thread:
            return FlowPlan(
                accepted=True,
                next_action="create_lightweight_revision",
                task_id=parent_task_id,
                revision_id=revision_id,
                host_route="automatic_thread",
                work_payload=payload,
                state_patch=revision_patch,
                stop_after_action=True,
            )
        plan = _manual_revision_plan(
            parent_task_id, revision_id, "host_cannot_route_or_create_revision_worker"
        )
        return replace(
            plan,
            state_patch={**revision_patch, **plan.state_patch},
            work_payload=payload,
        )

    if user_event.kind == "task_rebind_requested":
        runtime = current_state.worker_runtime
        next_task_id = str(data.get("next_task_id") or "")
        current_terminal = data.get("current_task_terminal") is True
        if not current_terminal:
            return FlowPlan(
                accepted=False,
                next_action="deny_worker_rebind",
                task_id=next_task_id,
                denial_reason="active_task_must_finish_stop_or_suspend_before_rebind",
            )
        if not next_task_id or not data.get("allowed_scope") or not data.get("validation_plan"):
            return FlowPlan(
                accepted=False,
                next_action="deny_worker_rebind",
                task_id=next_task_id,
                denial_reason="new_binding_requires_task_scope_and_validation_plan",
            )
        return FlowPlan(
            accepted=True,
            next_action="rebind_worker",
            task_id=next_task_id,
            revision_id=str(data.get("revision_id") or ""),
            required_claim=True,
            target_worker_id=runtime.host_window_or_thread_id,
            work_payload={
                "session_id": session.session_id,
                "task_id": next_task_id,
                "revision_id": str(data.get("revision_id") or ""),
                "worktree": str(data.get("worktree") or runtime.worktree),
                "branch": str(data.get("branch") or runtime.branch),
                "allowed_scope": list(data.get("allowed_scope") or ()),
                "validation_plan": list(data.get("validation_plan") or ()),
                "execution_ownership": str(
                    data.get("execution_ownership") or "worker_claim"
                ),
                "old_claim_id": runtime.claim_id or runtime.previous_claim_id,
                "old_task_status": task.lifecycle if task is not None else "completed",
            },
            state_patch={
                "worker_runtime": {
                    "claim_id": "",
                    "previous_claim_id": (
                        runtime.claim_id or runtime.previous_claim_id
                    ),
                    "previous_task_id": runtime.active_task_id or task_id,
                    "active_task_id": next_task_id,
                    "active_revision_id": str(data.get("revision_id") or ""),
                    "binding_status": "binding",
                    "allowed_scope": list(data.get("allowed_scope") or ()),
                    "validation_plan": list(data.get("validation_plan") or ()),
                    "execution_ownership": str(
                        data.get("execution_ownership") or "worker_claim"
                    ),
                }
            },
        )

    if user_event.kind == "task_rebind_completed":
        next_task_id = str(data.get("task_id") or "")
        claim_id = str(data.get("claim_id") or "")
        if not next_task_id or not claim_id or data.get("old_claim_released") is not True:
            return FlowPlan(
                accepted=False,
                next_action="deny_worker_rebind",
                task_id=next_task_id,
                denial_reason="rebind_completion_requires_released_old_and_acquired_new_claim",
            )
        return FlowPlan(
            accepted=True,
            next_action="start_rebound_work",
            task_id=next_task_id,
            revision_id=str(data.get("revision_id") or ""),
            required_claim=True,
            state_patch={
                "worker_runtime": {
                    "claim_id": claim_id,
                    "active_task_id": next_task_id,
                    "active_revision_id": str(data.get("revision_id") or ""),
                    "binding_status": "active",
                    "worker_availability": "busy",
                }
            },
        )

    if user_event.kind in {"revision_completed", "revision_blocked"}:
        revision_id = str(data.get("revision_id") or "")
        completed = user_event.kind == "revision_completed"
        if current_state.worker_runtime.claim_id and data.get("claim_released") is not True:
            return FlowPlan(
                accepted=False,
                next_action="repair_worker_closeout",
                task_id=task_id,
                revision_id=revision_id,
                denial_reason="revision_terminal_requires_released_worker_claim",
            )
        return FlowPlan(
            accepted=completed,
            next_action=("evaluate_integration" if completed else "repair_worker_closeout"),
            task_id=task_id,
            revision_id=revision_id,
            state_patch={
                "session": {
                    "phase": "integration_pending" if completed else "waiting_for_worker",
                    "expected_transition": (
                        _expected_patch(
                            "auto_integrate",
                            task_id,
                            report_id=str(data.get("report_id") or ""),
                            revision_id=revision_id,
                        )
                        if completed
                        else _expected_patch("repair_worker_closeout", task_id)
                    ),
                },
                "revision": {
                    "revision_id": revision_id,
                    "parent_task_id": task_id,
                    "status": "completed" if completed else "blocked",
                    "run_report": str(data.get("report_id") or ""),
                },
                "worker_runtime": {
                    "claim_id": "",
                    "previous_claim_id": (
                        current_state.worker_runtime.claim_id
                        or current_state.worker_runtime.previous_claim_id
                    ),
                    "previous_task_id": task_id,
                    "active_task_id": "",
                    "active_revision_id": "",
                    "worker_availability": "idle",
                    "binding_status": "released",
                    "allowed_scope": [],
                    "validation_plan": [],
                    "execution_ownership": "",
                },
            },
        )

    if user_event.kind == "operation_requested":
        operation = str(data.get("operation") or "")
        operation_scope = str(data.get("operation_scope") or "")
        runtime = current_state.worker_runtime
        worker_authorized = (
            session.role == "worker"
            and bool(runtime.claim_id)
            and runtime.active_task_id in {"", task_id}
            and runtime.binding_status in {"unbound", "bound", "active"}
        )
        integration_authorized = (
            session.role == "discussion"
            and session.phase == "integrating"
            and bool(current_state.integration_runtime.lease_id)
        )
        allowed = False
        if operation == "source_read":
            allowed = session.role in {"discussion", "worker"}
        elif operation == "governance_write":
            allowed = (
                session.role == "discussion"
                and session.phase
                in {
                    "planning",
                    "awaiting_worker_authorization",
                    "integrating",
                    "presenting_result",
                }
            ) or (
                worker_authorized
                and operation_scope in {"own_task_state", "own_revision_state"}
            )
        elif operation == "business_write":
            allowed = worker_authorized or (
                integration_authorized and operation_scope == "merge_resolution"
            )
            requested_paths = [
                str(path) for path in data.get("requested_paths", ()) if path
            ]
            if worker_authorized and runtime.allowed_scope:
                allowed = bool(requested_paths) and all(
                    any(fnmatch.fnmatch(path, pattern) for pattern in runtime.allowed_scope)
                    for path in requested_paths
                )
        elif operation == "build_test":
            allowed = worker_authorized or integration_authorized
            requested_validation = str(data.get("validation_step") or "")
            if worker_authorized and runtime.validation_plan and requested_validation:
                allowed = requested_validation in runtime.validation_plan
        elif operation == "install_dependency":
            allowed = worker_authorized and data.get("task_authorized") is True
        elif operation == "shared_state_write":
            allowed = integration_authorized or (
                session.role == "discussion" and session.phase == "planning"
            )
        elif operation == "integration_commit":
            allowed = integration_authorized
        elif operation == "commit":
            allowed = worker_authorized or integration_authorized
        if allowed:
            return FlowPlan(accepted=True, next_action="allow_operation", task_id=task_id)
        return _role_denial(
            task_id,
            "An active Worker Claim or Discussion-local Integration lease is required.",
        )

    if user_event.kind == "host_worker_launch_failed":
        return _manual_worker_plan(task_id, str(data.get("reason") or "launch_failed"))

    if user_event.kind == "host_worker_launch_succeeded":
        thread_id = str(data.get("thread_id") or "")
        if not thread_id:
            return _manual_worker_plan(task_id, "missing_real_worker_thread_id")
        if data.get("runtime_persisted") is not True:
            return FlowPlan(
                accepted=False,
                next_action="retry_runtime_persistence",
                task_id=task_id,
                host_route="automatic_thread",
                denial_reason="worker_created_but_runtime_not_persisted",
                state_patch={"worker_runtime": {"host_window_or_thread_id": thread_id}},
            )
        return FlowPlan(
            accepted=True,
            next_action="wait_for_worker",
            task_id=task_id,
            state_patch={
                "session": {
                    "phase": "waiting_for_worker",
                    "expected_transition": _expected_patch("wait_for_worker", task_id),
                },
                "worker_runtime": {"host_window_or_thread_id": thread_id},
            },
        )

    if user_event.kind == "worker_terminal":
        terminal = str(data.get("task_status") or "")
        report_id = str(data.get("report_id") or (task.run_report if task else ""))
        if terminal not in {"completed", "blocked", "incomplete"}:
            return FlowPlan(
                accepted=False,
                next_action="repair_worker_closeout",
                task_id=task_id,
                denial_reason="worker_terminal_status_invalid",
            )
        if current_state.worker_runtime.claim_id and data.get("claim_released") is not True:
            return FlowPlan(
                accepted=False,
                next_action="repair_worker_closeout",
                task_id=task_id,
                denial_reason="worker_terminal_requires_released_worker_claim",
            )
        return FlowPlan(
            accepted=True,
            next_action="evaluate_integration",
            task_id=task_id,
            state_patch={
                "session": {
                    "phase": "integration_pending",
                    "expected_transition": _expected_patch(
                        "auto_integrate", task_id, report_id=report_id
                    ),
                },
                "task": {"lifecycle": terminal, "run_report": report_id},
                "worker_runtime": {
                    "claim_id": "",
                    "previous_claim_id": (
                        current_state.worker_runtime.claim_id
                        or current_state.worker_runtime.previous_claim_id
                    ),
                    "previous_task_id": (
                        current_state.worker_runtime.active_task_id or task_id
                    ),
                    "active_task_id": "",
                    "active_revision_id": "",
                    "worker_availability": "idle",
                    "binding_status": "released",
                    "allowed_scope": [],
                    "validation_plan": [],
                    "execution_ownership": "",
                },
            },
        )

    if user_event.kind == "integration_evaluated":
        if session.phase != "integration_pending":
            return FlowPlan(
                accepted=False,
                next_action="no_action",
                task_id=task_id,
                denial_reason="integration_evaluation_requires_pending_phase",
            )
        outcome = str(data.get("outcome") or "")
        revision_id = str(
            data.get("revision_id")
            or (
                session.expected_transition.revision_id
                if session.expected_transition is not None
                else ""
            )
        )
        if outcome == "safe":
            allowed_lifecycles = (
                {"completed", "integrated", "reviewed"}
                if revision_id
                else {"completed"}
            )
            if task is None or task.lifecycle not in allowed_lifecycles:
                return FlowPlan(
                    accepted=False,
                    next_action="repair_worker_closeout",
                    task_id=task_id,
                    denial_reason="only_completed_tasks_can_integrate",
                    state_patch={
                        "session": {
                            "phase": "waiting_for_worker",
                            "expected_transition": _expected_patch(
                                "repair_worker_closeout", task_id
                            ),
                        },
                        "task": {"lifecycle": "blocked"},
                    },
                )
            return FlowPlan(
                accepted=True,
                next_action="enter_discussion_local_integration",
                task_id=task_id,
                required_integration_lease=True,
                host_route="discussion_local",
                state_patch={
                    "session": {"phase": "integrating", "expected_transition": None},
                    "integration_runtime": {"revision_id": revision_id},
                },
                revision_id=revision_id,
            )
        if outcome == "decision_required":
            decision_id = str(data.get("decision_id") or "material-decision")
            question = str(data.get("question") or "请确认具体风险处理方案。")
            return FlowPlan(
                accepted=True,
                next_action="ask_material_decision",
                task_id=task_id,
                user_message=question,
                stop_after_action=True,
                state_patch={
                    "session": {
                        "phase": "decision_required",
                        "expected_transition": _expected_patch(
                            "resolve_conflict", task_id, decision_id=decision_id
                        ),
                    },
                    "pending_decision": {"decision_id": decision_id},
                },
            )
        if outcome == "blocked":
            reason = str(data.get("reason") or "integration_evidence_incomplete")
            return FlowPlan(
                accepted=False,
                next_action="repair_worker_closeout",
                task_id=task_id,
                denial_reason=reason,
                state_patch={
                    "session": {
                        "phase": "waiting_for_worker",
                        "expected_transition": _expected_patch(
                            "repair_worker_closeout", task_id
                        ),
                    },
                    "task": {"lifecycle": "blocked"},
                },
            )
        return FlowPlan(
            accepted=False,
            next_action="repair_worker_closeout",
            task_id=task_id,
            denial_reason="integration_evaluation_outcome_invalid",
        )

    if user_event.kind == "decision_resolved":
        decision_id = str(data.get("decision_id") or "")
        if (
            session.phase != "decision_required"
            or not decision_id
            or decision_id != current_state.pending_decision.decision_id
        ):
            return FlowPlan(
                accepted=False,
                next_action="no_action",
                task_id=task_id,
                denial_reason="decision_resolution_does_not_match_pending_decision",
            )
        return FlowPlan(
            accepted=True,
            next_action="evaluate_integration",
            task_id=task_id,
            state_patch={
                "session": {
                    "phase": "integration_pending",
                    "expected_transition": _expected_patch(
                        "auto_integrate",
                        task_id,
                        report_id=task.run_report if task is not None else "",
                    ),
                },
                "pending_decision": {
                    "decision_id": "",
                    "kind": "",
                    "options": [],
                    "recommended_option": "",
                },
                "integration_runtime": {
                    "decision_receipt": {
                        "decision_id": decision_id,
                        "task_id": task_id,
                        "confirmed": True,
                        "selected_option": str(data.get("selected_option") or ""),
                    }
                },
            },
        )

    if user_event.kind == "integration_completed":
        integration_id = str(
            data.get("integration_id")
            or current_state.integration_runtime.integration_id
        )
        revision_id = str(
            data.get("revision_id")
            or current_state.integration_runtime.revision_id
        )
        allowed_lifecycles = (
            {"completed", "integrated", "reviewed"}
            if revision_id
            else {"completed"}
        )
        if (
            session.role != "discussion"
            or session.phase != "integrating"
            or not current_state.integration_runtime.lease_id
            or not integration_id
            or task is None
            or task.lifecycle not in allowed_lifecycles
        ):
            return FlowPlan(
                accepted=False,
                next_action="deny_role_violation",
                task_id=task_id,
                denial_reason="integration_completion_requires_bound_active_integration",
            )
        state_patch = {
            "session": {
                "phase": "presenting_result",
                "expected_transition": _expected_patch(
                    "accept_result", task_id, integration_id=integration_id
                ),
            },
            "task": {
                "lifecycle": (
                    task.lifecycle
                    if revision_id and task.lifecycle in {"integrated", "reviewed"}
                    else "integrated"
                )
            },
            "integration_runtime": {
                "lease_id": "",
                "integration_id": integration_id,
                "revision_id": "",
            },
        }
        if revision_id:
            state_patch["revision"] = {
                "revision_id": revision_id,
                "parent_task_id": task_id,
                "status": "integrated",
                "run_report": str(data.get("report_id") or task.run_report),
                "project_status_updated": data.get("project_status_updated") is True,
            }
        return FlowPlan(
            accepted=True,
            next_action="present_result",
            task_id=task_id,
            required_integration_lease=True,
            revision_id=revision_id,
            state_patch=state_patch,
        )

    if user_event.kind != "user_message":
        return FlowPlan(
            accepted=False,
            next_action="no_action",
            task_id=task_id,
            denial_reason="unrecognized_orchestration_event",
        )

    text = str(data.get("text") or "").strip()
    if text.rstrip("。.!！") == "就在当前窗口直接修改":
        return FlowPlan(
            accepted=False,
            next_action="ask_for_worker_authorization",
            task_id=task_id,
            denial_reason="Discussion cannot perform Worker implementation; route an independent Worker.",
            stop_after_action=True,
        )

    command = parse_task_command(text)
    if command is not None and command.get("action") in {
        "inspect",
        "observe",
        "family",
    }:
        return FlowPlan(accepted=True, next_action="read_status", task_id=command["task_id"])
    if command is not None and command.get("authorizes_execution"):
        requested = str(command.get("task_id") or "")
        if task is None or task.task_id != requested:
            return FlowPlan(
                accepted=False,
                next_action="ask_task_choice",
                task_id=requested,
                denial_reason="exact_task_not_loaded",
            )
        if session.role == "neutral":
            if task.lifecycle != "approved" or not task.worker_authorized:
                return FlowPlan(
                    accepted=False,
                    next_action="deny_execution_preflight",
                    task_id=task_id,
                    denial_reason="Task must be approved and Worker-authorized.",
                )
            return FlowPlan(
                accepted=True,
                next_action="enter_worker",
                task_id=task_id,
                required_claim=True,
                host_route="current_neutral_window",
                state_patch={
                    "session": {
                        "role": "worker",
                        "phase": "waiting_for_worker",
                        "expected_transition": _expected_patch(
                            "wait_for_worker", task_id
                        ),
                    },
                    "task": {"lifecycle": "running"},
                },
            )
        if session.role == "discussion":
            return FlowPlan(
                accepted=True,
                next_action="launch_worker",
                task_id=task_id,
                host_route=(
                    "automatic_thread"
                    if host_capability.supports_formal_worker_thread
                    else "manual_window"
                ),
                state_patch={
                    "session": {
                        "phase": "routing_worker",
                        "expected_transition": None,
                    },
                    "task": {"lifecycle": "approved", "worker_authorized": True},
                },
            )

    if is_contextual_approval(text):
        if len(current_state.candidate_task_ids) > 1:
            choices = " 和 ".join(current_state.candidate_task_ids)
            return FlowPlan(
                accepted=False,
                next_action="ask_task_choice",
                user_message=f"当前有 {choices} 两个任务等待启动，你希望执行哪一个？",
                denial_reason="contextual_transition_is_ambiguous",
            )
        expected = session.expected_transition
        if expected is None:
            return FlowPlan(
                accepted=False,
                next_action="ask_task_choice",
                denial_reason="no_unique_expected_transition",
            )
        if expected.kind == "approve_worker_launch":
            if task is None or task.task_id != expected.task_id:
                return FlowPlan(
                    accepted=False,
                    next_action="ask_task_choice",
                    task_id=expected.task_id,
                    denial_reason="expected_worker_task_is_not_current",
                )
            return FlowPlan(
                accepted=True,
                next_action="launch_worker",
                task_id=expected.task_id,
                host_route=(
                    "automatic_thread"
                    if host_capability.supports_formal_worker_thread
                    else "manual_window"
                ),
                state_patch={
                    "session": {"phase": "routing_worker", "expected_transition": None},
                    "task": {"lifecycle": "approved", "worker_authorized": True},
                },
            )
        if expected.kind == "accept_result":
            if (
                task is None
                or task.task_id != expected.task_id
                or task.lifecycle != "integrated"
                or not expected.integration_id
            ):
                return FlowPlan(
                    accepted=False,
                    next_action="no_action",
                    task_id=expected.task_id,
                    denial_reason="result_acceptance_transition_is_stale",
                )
            return FlowPlan(
                accepted=True,
                next_action="accept_result",
                task_id=expected.task_id,
                state_patch={
                    "session": {"phase": "planning", "expected_transition": None},
                    "task": {"lifecycle": "reviewed"},
                },
            )
        return FlowPlan(
            accepted=False,
            next_action="no_action",
            task_id=expected.task_id,
            denial_reason=f"contextual approval cannot consume {expected.kind}",
        )

    return FlowPlan(
        accepted=False,
        next_action="no_action",
        task_id=task_id,
        denial_reason="message_does_not_match_current_expected_transition",
    )


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
    view: str = "full"
    task_filter: Optional[str] = None
    pending_integration: bool = False
    integration_kind: str = "none"
    ready_reports: list[str] = field(default_factory=list)
    waiting_reports: list[str] = field(default_factory=list)
    blocked_reports: list[str] = field(default_factory=list)
    work_units: list[dict[str, Any]] = field(default_factory=list)
    requires_user_confirmation: bool = False
    auto_integration_eligible: bool = False
    next_action: str = "nothing_to_integrate"
    selected_reports: list[str] = field(default_factory=list)
    superseded_reports: list[str] = field(default_factory=list)
    reason: str = "No worker results are waiting for integration."

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": WORKFLOW_STATE_SCHEMA_VERSION,
            "kind": "integration_status",
            "view": self.view,
            "task_filter": self.task_filter,
            "pending_integration": self.pending_integration,
            "integration_kind": self.integration_kind,
            "ready_reports": self.ready_reports,
            "waiting_reports": self.waiting_reports,
            "blocked_reports": self.blocked_reports,
            "work_units": self.work_units,
            "requires_user_confirmation": self.requires_user_confirmation,
            "auto_integration_eligible": self.auto_integration_eligible,
            "next_action": self.next_action,
            "selected_reports": self.selected_reports,
            "superseded_reports": self.superseded_reports,
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
    if state.execution_mode not in EXECUTION_MODES:
        errors.append("missing or invalid execution_mode")
    if state.change_class not in {"formal", "revision", "micro"}:
        errors.append("missing or invalid change_class")
    if state.change_class == "revision":
        if not state.task_id or not state.revision_id:
            errors.append("revision work requires task_id and revision_id")
        if not state.risk_flags_known:
            errors.append("revision work requires every explicit risk flag")
        elif not state.risk_flags_clear:
            errors.append("high-risk work cannot use Task Revision")
        if not state.changed_paths:
            errors.append("revision work requires explicit changed_paths")
    if state.change_class == "micro":
        if not state.risk_flags_known:
            errors.append("micro work requires every explicit risk flag")
        elif not state.risk_flags_clear:
            errors.append("recorded API, data, security, billing, deletion, migration, dependency, or contract risk cannot be micro")
        if state.work_type != "sequential":
            errors.append("micro work must use sequential work_type")
        if state.task_id:
            errors.append("micro work must use an independent ad-hoc unit, not a formal Task")
        if not state.changed_paths:
            errors.append("micro work requires explicit changed_paths")
    if state.work_type == "parallel_batch" and state.batch_id in {
        "",
        "n/a",
        "na",
        "none",
        "无",
    }:
        errors.append("parallel_batch requires a batch ID")
    if state.work_type == "high_risk":
        if state.authorization not in EXPLICIT_AUTHORIZATIONS:
            errors.append(
                "high-risk work requires a decision-required integration recommendation"
            )
    elif state.work_type == "parallel_batch" and state.execution_mode not in {
        "parallel_independent",
        "competitive",
    }:
        if state.authorization not in EXPLICIT_AUTHORIZATIONS:
            errors.append(
                "non-independent parallel work requires a decision-required integration recommendation"
            )
    elif state.authorization not in EXPLICIT_AUTHORIZATIONS | INHERITED_AUTHORIZATIONS:
        errors.append("missing or invalid integration recommendation")
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
    if state.state_source == "structured":
        if state.parent_task_id and state.parent_task_id == state.task_id:
            errors.append("parent_task_id cannot equal task_id")
        if state.task_id in state.dependencies:
            errors.append("dependencies cannot contain task_id itself")
        if len(state.dependencies) != len(set(state.dependencies)):
            errors.append("dependencies cannot contain duplicates")
    if state.status not in TASK_STATUSES:
        errors.append("missing or invalid task status")
    if state.work_type not in WORK_TYPES - {"discussion"}:
        errors.append("missing or invalid task work type")
    if state.execution_mode not in EXECUTION_MODES:
        errors.append("missing or invalid execution_mode")
    if state.execution_mode == "competitive" and not state.comparison_group:
        errors.append("competitive task requires comparison_group")
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
    if state.status in {"draft", "cancelled"} and state.worker_creation_authorized:
        errors.append(f"{state.status} task cannot authorize Worker creation")
    if state.status not in {"draft", "cancelled"} and not state.worker_creation_authorized:
        errors.append(
            f"{state.status} task requires explicit Worker creation authorization"
        )
    if state.work_type == "high_risk":
        if state.integration_policy != "requires_explicit_user_confirmation":
            errors.append("high-risk task requires decision_required integration route")
    elif state.work_type == "parallel_batch" and state.execution_mode not in {
        "parallel_independent",
        "competitive",
    }:
        if state.integration_policy != "requires_explicit_user_confirmation":
            errors.append(
                "non-independent parallel task requires decision_required integration route"
            )
    elif state.integration_policy not in {
        "inherited_task_approval",
        "requires_explicit_user_confirmation",
    }:
        errors.append("missing or invalid integration route")
    return state


def revision_state(revision_path: str, content: str) -> RevisionState:
    state = parse_revision_state(revision_path, content)
    if state.run_report and not state.run_report.endswith(".md"):
        state.errors.append("run_report must be a Markdown path")
    return state


def all_revision_states(
    root: Path, config: dict[str, Any], scope: str = "worktree"
) -> list[RevisionState]:
    revisions: list[RevisionState] = []
    for path in sorted(root.glob(configured_revision_glob(config))):
        relative = path.relative_to(root).as_posix()
        content = read_version(root, relative, scope)
        if content is not None:
            revisions.append(revision_state(relative, content))
    return revisions


def revision_report_states(
    root: Path, config: dict[str, Any], scope: str = "worktree"
) -> dict[str, RevisionState]:
    return {
        state.run_report: state
        for state in all_revision_states(root, config, scope)
        if state.run_report
    }


def all_task_states(
    root: Path, config: dict[str, Any], scope: str = "worktree"
) -> list[TaskState]:
    tasks: list[TaskState] = []
    seen: set[Path] = set()
    for task_glob in configured_task_globs(config):
        for path in root.glob(task_glob):
            if path in seen or path.name.startswith(("EXAMPLE-", "NNN-")):
                continue
            seen.add(path)
            relative = path.relative_to(root).as_posix()
            content = read_version(root, relative, scope)
            if content is not None:
                tasks.append(task_state(relative, content))
    return tasks


def task_report_states(
    root: Path, config: dict[str, Any], scope: str = "worktree"
) -> dict[str, TaskState]:
    tasks: dict[str, TaskState] = {}
    for state in all_task_states(root, config, scope):
        if not state.run_report:
            continue
        tasks[state.run_report] = state
    return tasks


def execution_preflight(
    root: Path,
    config: dict[str, Any],
    task_path: str,
    authorization_action: str,
) -> tuple[TaskState, list[str]]:
    """Evaluate formal execution gates without performing host actions or writes."""
    content = read_version(root, task_path, "worktree") or ""
    state = task_state(task_path, content)
    errors = list(state.errors)
    required_sections = {
        "change_set": ("Change Set", "变更范围", "变更集"),
        "do_not_do": ("Do Not Do", "不要做", "禁止事项"),
        "validation": ("Validation", "验证"),
        "rollback": (
            "Rollback",
            "Rollback / Recovery",
            "Rollback Boundary",
            "回滚",
            "回滚 / 恢复",
            "回滚边界",
        ),
    }
    for key, headings in required_sections.items():
        if not any(markdown_section(content, heading) for heading in headings):
            errors.append(f"missing_{key}_section")

    allowed_by_action = {
        "execute": {"draft", "approved"},
        "continue": {"approved", "running"},
        "retry": {"blocked", "incomplete", "rejected", "abandoned"},
        "take_over": {"running", "blocked", "incomplete", "abandoned"},
    }
    if state.status not in allowed_by_action.get(authorization_action, set()):
        errors.append(f"status_{state.status}_does_not_allow_{authorization_action}")

    by_id = {item.task_id: item for item in all_task_states(root, config) if item.task_id}
    unsatisfied = [
        dependency
        for dependency in state.dependencies
        if dependency not in by_id
        or by_id[dependency].status not in {"integrated", "reviewed"}
    ]
    if unsatisfied:
        errors.append("unsatisfied_dependencies:" + ",".join(unsatisfied))
    return state, errors


def integration_state(
    root: Path,
    config: dict[str, Any],
    *,
    view: str = "full",
    task_id: Optional[str] = None,
) -> IntegrationState:
    """Build integration state without scanning report history for normal views."""
    if view not in {"active", "full"}:
        raise ValueError("view must be active or full")
    task_filter = canonical_task_id(task_id) if task_id else None
    if task_id and not task_filter:
        raise ValueError("task_id must match ^\\d{3,}[a-z]*$")

    all_tasks = all_task_states(root, config)
    all_revisions = all_revision_states(root, config)
    if task_filter:
        selected_tasks = [task for task in all_tasks if task.task_id == task_filter]
        selected_revisions = [
            revision
            for revision in all_revisions
            if revision.parent_task_id == task_filter
        ]
    elif view == "active":
        selected_tasks = [
            task
            for task in all_tasks
            if task.status
            in {"approved", "running", "completed", "blocked", "incomplete"}
            or (task.state_source == "legacy" and task.status == "draft")
        ]
        selected_revisions = [
            revision
            for revision in all_revisions
            if revision.status in {"pending", "running", "completed", "blocked"}
        ]
    else:
        selected_tasks = all_tasks
        selected_revisions = all_revisions

    tasks = {task.run_report: task for task in selected_tasks if task.run_report}
    revisions = {
        revision.run_report: revision
        for revision in selected_revisions
        if revision.run_report
    }
    candidate_reports = set(tasks) | set(revisions)
    if view == "active" and task_filter is None:
        report_glob = config["paths"]["run_report_glob"]
        candidate_reports.update(
            path
            for path in changed_paths(root, "worktree")
            if fnmatch.fnmatch(path, report_glob)
        )
    reports = (
        report_contents_across_refs(root, config)
        if view == "full" and task_filter is None
        else report_contents_for_paths_across_refs(root, config, candidate_reports)
    )
    prefix = config["paths"]["run_report_glob"].split("*", 1)[0].rstrip("/")
    settled = (
        report_paths_in_ref(root, "HEAD", prefix)
        if view == "full" and task_filter is None
        else {
            path for path in candidate_reports if read_head_version(root, path) is not None
        }
    )
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
    waiting.extend(
        sorted(
            path
            for path, revision in revisions.items()
            if path not in reports
            and path not in settled
            and revision.status in {"pending", "running"}
        )
    )
    waiting = sorted(set(waiting))

    work_types = {
        state.work_type for state in pending_states if state.work_type in WORK_TYPES
    }
    work_types.update(
        state.work_type
        for path, state in tasks.items()
        if path in waiting and state.work_type in WORK_TYPES
    )
    if any(path in waiting for path in revisions):
        work_types.add("sequential")
    if "high_risk" in work_types:
        kind = "high_risk"
    elif "parallel_batch" in work_types or len(ready) + len(blocked) > 1:
        kind = "parallel_batch"
    elif "sequential" in work_types:
        kind = "sequential"
    else:
        kind = "none"

    pending = bool(ready or blocked)
    pending_by_path = {state.path: state for state in pending_states}
    task_by_report = tasks
    task_status_by_id = {task.task_id: task.status for task in all_tasks if task.task_id}

    def dependencies_satisfied(task: TaskState) -> bool:
        return all(
            task_status_by_id.get(dependency) in {"integrated", "reviewed"}
            for dependency in task.dependencies
        )

    structured_ready_tasks = [task_by_report.get(path) for path in ready]
    sequential_safe = bool(ready) and all(
        (
            task is None
            and pending_by_path[path].authorization in INHERITED_AUTHORIZATIONS
        )
        or (
            task is not None
            and task.state_source == "legacy"
            and pending_by_path[path].authorization in INHERITED_AUTHORIZATIONS
        )
        or (
            task is not None
            and task.worker_creation_authorized
            and task.integration_policy == "inherited_task_approval"
            and pending_by_path[path].authorization in INHERITED_AUTHORIZATIONS
            and dependencies_satisfied(task)
        )
        for path, task in zip(ready, structured_ready_tasks)
    )

    parallel_states = [pending_by_path[path] for path in ready]
    parallel_tasks_safe = bool(ready) and all(
        task is not None
        and task.state_source == "structured"
        and task.execution_mode == "parallel_independent"
        and task.worker_creation_authorized
        and task.integration_policy
        in {"inherited_task_approval", "requires_explicit_user_confirmation"}
        and dependencies_satisfied(task)
        for task in structured_ready_tasks
    )
    changed_path_sets = [set(state.changed_paths) for state in parallel_states]
    paths_are_known = bool(changed_path_sets) and all(changed_path_sets)
    paths_do_not_overlap = all(
        not left.intersection(right)
        for index, left in enumerate(changed_path_sets)
        for right in changed_path_sets[index + 1 :]
    )
    parallel_reports_safe = bool(parallel_states) and all(
        state.execution_mode == "parallel_independent"
        and state.risk_flags_known
        and state.risk_flags_clear
        for state in parallel_states
    )
    parallel_safe = (
        parallel_tasks_safe
        and parallel_reports_safe
        and paths_are_known
        and paths_do_not_overlap
    )
    competitive = any(
        task is not None and task.execution_mode == "competitive"
        for task in structured_ready_tasks
    ) or any(state.execution_mode == "competitive" for state in parallel_states)

    auto_eligible = False
    confirmation = False
    selected_reports: list[str] = []
    superseded_reports: list[str] = []
    if blocked:
        next_action = "discuss_blocker"
        confirmation = True
        reason = "Blocked or unsafe worker results require discussion and user review."
    elif competitive:
        if waiting:
            next_action = "wait_for_worker"
            reason = "Competitive candidates are still running or waiting for reports."
        else:
            scored = [
                state
                for state in parallel_states
                if state.candidate_score is not None
                and not state.selection_requires_judgment
            ]
            if len(scored) == len(parallel_states) and scored:
                best_score = max(state.candidate_score for state in scored)
                winners = [state for state in scored if state.candidate_score == best_score]
            else:
                winners = []
            if len(winners) == 1:
                selected_reports = [winners[0].path]
                superseded_reports = sorted(set(ready) - set(selected_reports))
                auto_eligible = True
                next_action = "auto_integrate"
                reason = "Objective candidate scoring selected one unique winner."
            else:
                next_action = "compare_candidates"
                confirmation = True
                reason = "Competitive candidates need a preference or tie-break decision."
    elif kind == "high_risk" and ready:
        next_action = "await_user_confirmation"
        confirmation = True
        reason = "High-risk work requires a Discussion decision before integration."
    elif waiting:
        next_action = "wait_for_worker"
        reason = "Planned workers have not all produced terminal run reports yet."
    elif kind == "parallel_batch" and ready and parallel_safe:
        next_action = "auto_integrate"
        auto_eligible = True
        selected_reports = list(ready)
        reason = "Independent parallel results passed mechanical risk and overlap gates."
    elif kind == "parallel_batch" and ready:
        next_action = "await_user_confirmation"
        confirmation = True
        reason = "Parallel results need user judgment because independence is not mechanically proven."
    elif kind == "sequential" and ready and sequential_safe:
        next_action = "auto_integrate"
        auto_eligible = True
        selected_reports = list(ready)
        reason = "A safe sequential result is ready under inherited task authority."
    elif kind == "sequential" and ready:
        next_action = "discuss_blocker"
        confirmation = True
        reason = "Sequential integration gates are incomplete or its dependencies are unresolved."
    else:
        next_action = "nothing_to_integrate"
        reason = "No worker results are waiting for integration."
    work_units: list[dict[str, Any]] = []
    for report_path, task in sorted(tasks.items(), key=lambda item: item[1].path):
        active_claims = [
            claim
            for claim in inspect_claims(root, task.task_id)
            if claim.get("effective_lease_status") == "active"
        ] if task.task_id else []
        report = report_state(report_path, reports[report_path]) if report_path in reports else None
        if task.status == "reviewed":
            lifecycle = "reviewed"
        elif report_path in settled:
            lifecycle = "integrated"
        elif report is not None:
            lifecycle = (
                "completed"
                if report.status in {"completed", "done"} and not report.safety_errors
                else "blocked"
            )
        elif active_claims:
            lifecycle = "running"
        else:
            lifecycle = task.status
        work_units.append(
            {
                "task_path": task.path,
                "task_id": task.task_id,
                "parent_task_id": task.parent_task_id or None,
                "dependencies": task.dependencies,
                "attempt": task.attempt,
                "execution_mode": task.execution_mode,
                "comparison_group": task.comparison_group or None,
                "lifecycle_status": lifecycle,
                "task_status": task.status,
                "work_type": task.work_type,
                "run_report": report_path,
                "worker_creation_authorized": task.worker_creation_authorized,
                "integration_policy": task.integration_policy,
                "state_source": task.state_source,
                "errors": task.errors,
                "candidate_score": report.candidate_score if report else None,
                "selection_requires_judgment": (
                    report.selection_requires_judgment if report else False
                ),
                "active_claims": [
                    {
                        "claim_id": claim.get("claim_id"),
                        "worker_id": claim.get("worker_id"),
                        "branch": claim.get("branch"),
                        "worktree": claim.get("worktree"),
                        "updated_at": claim.get("updated_at"),
                        "execution_mode": claim.get("execution_mode"),
                        "agent_platform": claim.get("agent_platform", "unknown"),
                    }
                    for claim in active_claims
                ],
            }
        )

    for revision in selected_revisions:
        active_claims = [
            claim
            for claim in inspect_claims(root, revision.parent_task_id)
            if claim.get("effective_lease_status") == "active"
            and claim.get("revision_id") == revision.revision_id
        ]
        report = (
            report_state(revision.run_report, reports[revision.run_report])
            if revision.run_report in reports
            else None
        )
        if revision.status == "integrated" or revision.run_report in settled:
            lifecycle = "integrated"
        elif report is not None:
            lifecycle = (
                "completed"
                if report.status in {"completed", "done"} and not report.safety_errors
                else "blocked"
            )
        elif active_claims:
            lifecycle = "running"
        else:
            lifecycle = revision.status
        work_units.append(
            {
                "revision_path": revision.path,
                "revision_id": revision.revision_id,
                "parent_task_id": revision.parent_task_id,
                "lifecycle_status": lifecycle,
                "revision_status": revision.status,
                "work_type": "sequential",
                "execution_mode": "exclusive",
                "run_report": revision.run_report,
                "worker_creation_authorized": revision.worker_creation_authorized,
                "integration_policy": "inherited_task_approval",
                "state_source": revision.state_source,
                "errors": revision.errors,
                "active_claims": [
                    {
                        "claim_id": claim.get("claim_id"),
                        "worker_id": claim.get("worker_id"),
                        "branch": claim.get("branch"),
                        "worktree": claim.get("worktree"),
                        "updated_at": claim.get("updated_at"),
                        "agent_platform": claim.get("agent_platform", "unknown"),
                    }
                    for claim in active_claims
                ],
            }
        )

    return IntegrationState(
        view=view,
        task_filter=task_filter,
        pending_integration=pending,
        integration_kind=kind,
        ready_reports=ready,
        waiting_reports=waiting,
        blocked_reports=blocked,
        work_units=work_units,
        requires_user_confirmation=confirmation,
        auto_integration_eligible=auto_eligible,
        next_action=next_action,
        selected_reports=selected_reports,
        superseded_reports=superseded_reports,
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
    ) or fnmatch.fnmatch(path, configured_revision_glob(config)):
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
    required_report_integrations: set[str] = set()
    for report_path in run_reports:
        report_content = read_version(root, report_path, scope)
        if report_content is not None:
            report_states.append(report_state(report_path, report_content))
            required_report_integrations.update(
                memory_path
                for memory_path, (status, _) in parse_impact_rows(report_content).items()
                if status in INTEGRATE_STATUSES
            )
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
    revisions = revision_report_states(root, config, scope)
    for report_path in run_reports:
        task = tasks.get(report_path)
        if task is not None and task.state_source == "structured" and task.status != "integrated":
            result.errors.append(
                f"{task.path} must move task status to integrated when absorbing {report_path}"
            )
        revision = revisions.get(report_path)
        if revision is not None and revision.status != "integrated":
            result.errors.append(
                f"{revision.path} must move revision status to integrated when absorbing {report_path}"
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
        if memory_path in required_report_integrations and status not in UPDATED_STATUSES:
            result.errors.append(
                f"{overview_path} must mark {memory_path} Updated because a selected "
                "Run Report marked it Integrate"
            )
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
    known_task_ids = {
        item.task_id for item in all_task_states(root, config, scope) if item.task_id
    }
    if state.parent_task_id and state.parent_task_id not in known_task_ids:
        result.errors.append(
            f"{task_path} parent_task_id {state.parent_task_id} does not resolve to a Task"
        )
    for dependency in state.dependencies:
        if dependency not in known_task_ids:
            result.errors.append(
                f"{task_path} dependency {dependency} does not resolve to a Task"
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
                    ("parent_task_id", previous.parent_task_id, state.parent_task_id),
                    ("dependencies", previous.dependencies, state.dependencies),
                    ("execution_mode", previous.execution_mode, state.execution_mode),
                    ("comparison_group", previous.comparison_group, state.comparison_group),
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
                if transition in {
                    ("blocked", "approved"),
                    ("incomplete", "approved"),
                    ("rejected", "approved"),
                    ("abandoned", "approved"),
                }:
                    if previous.run_report == state.run_report:
                        result.errors.append(
                            f"{task_path} retry approval requires a new immutable run_report path"
                        )
                    if state.attempt != previous.attempt + 1:
                        result.errors.append(
                            f"{task_path} retry approval must increment attempt by exactly one"
                        )
                elif previous.run_report != state.run_report:
                    result.errors.append(
                        f"{task_path} run_report may change only when retrying blocked or incomplete work"
                    )
                elif previous.attempt != state.attempt:
                    result.errors.append(
                        f"{task_path} attempt may change only when retrying blocked or incomplete work"
                    )
            if previous.status != state.status and state.status not in TASK_TRANSITIONS.get(
                previous.status, set()
            ):
                result.errors.append(
                    f"{task_path} has invalid task transition {previous.status} -> {state.status}"
                )

    if state.status in {
        "completed",
        "blocked",
        "incomplete",
        "rejected",
        "abandoned",
        "superseded",
        "integrated",
        "reviewed",
    }:
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


REVISION_TRANSITIONS = {
    "pending": {"running", "completed", "blocked"},
    "running": {"completed", "blocked"},
    "blocked": {"running", "completed"},
    "completed": {"integrated"},
    "integrated": set(),
}


def validate_revision_spec(
    root: Path,
    config: dict[str, Any],
    scope: str,
    revision_path: str,
    result: CheckResult,
) -> Optional[RevisionState]:
    content = read_version(root, revision_path, scope)
    if content is None:
        result.errors.append(f"Cannot read the {scope} version of {revision_path}")
        return None
    state = revision_state(revision_path, content)
    for error in state.errors:
        result.errors.append(f"{revision_path} {error}")
    if state.revision_id and Path(revision_path).stem != state.revision_id:
        result.errors.append(
            f"{revision_path} filename must exactly match revision_id {state.revision_id}"
        )
    task_by_id = {
        item.task_id: item for item in all_task_states(root, config, scope) if item.task_id
    }
    if state.parent_task_id and state.parent_task_id not in task_by_id:
        result.errors.append(
            f"{revision_path} parent_task_id {state.parent_task_id} does not resolve to a Task"
        )
    elif state.parent_task_id and task_by_id[state.parent_task_id].status not in {
        "completed",
        "integrated",
        "reviewed",
    }:
        result.errors.append(
            f"{revision_path} parent Task must be completed, integrated, or reviewed"
        )
    if state.run_report and not fnmatch.fnmatch(
        state.run_report, config["paths"]["run_report_glob"]
    ):
        result.errors.append(
            f"{revision_path} run_report must match {config['paths']['run_report_glob']}"
        )
    previous_content = read_head_version(root, revision_path)
    if previous_content is not None:
        previous = revision_state(revision_path, previous_content)
        if previous.revision_id != state.revision_id:
            result.errors.append(f"{revision_path} revision_id is immutable")
        for name in (
            "parent_task_id",
            "user_request",
            "allowed_scope",
            "validation_plan",
            "run_report",
        ):
            if getattr(previous, name) != getattr(state, name):
                result.errors.append(f"{revision_path} {name} is immutable")
        if previous.status != state.status and state.status not in REVISION_TRANSITIONS.get(
            previous.status, set()
        ):
            result.errors.append(
                f"{revision_path} has invalid revision transition {previous.status} -> {state.status}"
            )
    if state.status in {"completed", "blocked", "integrated"}:
        if not state.run_report or read_version(root, state.run_report, scope) is None:
            result.errors.append(
                f"{revision_path} status {state.status} requires run report {state.run_report or '(missing)'}"
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

    try:
        path_statuses = changed_path_statuses(root, scope)
    except (OSError, subprocess.CalledProcessError) as exc:
        result.errors.append(f"Unable to inspect Git path transitions: {exc}")
        path_statuses = []
    task_globs = configured_task_globs(config)
    revision_glob = configured_revision_glob(config)
    for status, old_path, new_path in path_statuses:
        if status == "D" and fnmatch.fnmatch(old_path, revision_glob):
            result.errors.append(
                f"Task Revision records cannot be deleted: {old_path}; preserve the audit record"
            )
            continue
        if status.startswith("R") and new_path is not None and fnmatch.fnmatch(
            old_path, revision_glob
        ):
            result.errors.append(
                f"Task Revision filename is immutable: {old_path} -> {new_path}"
            )
            continue
        if status == "D" and any(
            fnmatch.fnmatch(old_path, pattern) for pattern in task_globs
        ):
            previous_content = read_head_version(root, old_path)
            if previous_content is not None:
                previous = task_state(old_path, previous_content)
                if previous.state_source == "structured":
                    result.errors.append(
                        f"Task Specs with allocated IDs cannot be deleted: {old_path}; mark the Task cancelled instead"
                    )
            continue
        if not status.startswith("R") or new_path is None:
            continue
        if not any(fnmatch.fnmatch(old_path, pattern) for pattern in task_globs):
            continue
        previous_content = read_head_version(root, old_path)
        if previous_content is None:
            continue
        previous = task_state(old_path, previous_content)
        if previous.state_source == "structured" and previous.status != "draft":
            result.errors.append(
                f"Approved Task Spec filename is immutable: {old_path} -> {new_path}"
            )

    task_paths_by_id: dict[str, list[str]] = {}
    for state in all_task_states(root, config, scope):
        if state.state_source == "structured" and state.task_id:
            task_paths_by_id.setdefault(state.task_id, []).append(state.path)
    for task_id, duplicate_paths in sorted(task_paths_by_id.items()):
        if len(duplicate_paths) > 1:
            result.errors.append(
                f"Duplicate task_id {task_id} is declared by: {', '.join(sorted(duplicate_paths))}"
            )
    revision_paths_by_id: dict[str, list[str]] = {}
    for state in all_revision_states(root, config, scope):
        if state.revision_id:
            revision_paths_by_id.setdefault(state.revision_id, []).append(state.path)
    for revision_id, duplicate_paths in sorted(revision_paths_by_id.items()):
        if len(duplicate_paths) > 1:
            result.errors.append(
                f"Duplicate revision_id {revision_id} is declared by: "
                + ", ".join(sorted(duplicate_paths))
            )

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
    revision_paths = sorted(
        path for path in changed if fnmatch.fnmatch(path, revision_glob)
    )
    validated_tasks: dict[str, TaskState] = {}
    for task_path in task_paths:
        state = validate_task_spec(root, config, scope, task_path, result)
        if state is not None:
            validated_tasks[task_path] = state
    validated_revisions: dict[str, RevisionState] = {}
    for revision_path in revision_paths:
        state = validate_revision_spec(root, config, scope, revision_path, result)
        if state is not None:
            validated_revisions[revision_path] = state
    lifecycle_paths = set(task_paths) | set(revision_paths)
    if discussion_path in changed:
        lifecycle_paths.add(discussion_path)
    revision_routing_only = bool(revision_paths) and all(
        state.status in {"pending", "running"}
        for state in validated_revisions.values()
    )
    if (task_paths or revision_routing_only) and set(changed) == lifecycle_paths and all(
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
        and path not in revision_paths
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
    revisions_by_report = revision_report_states(root, config, scope)
    for report_path in run_reports:
        task = tasks_by_report.get(report_path)
        report_content = read_version(root, report_path, scope)
        if report_content is None:
            continue
        report = report_state(report_path, report_content)
        if task is not None and task.state_source == "structured":
            if report.task_id and report.task_id != task.task_id:
                result.errors.append(
                    f"{report_path} task_id {report.task_id} does not match {task.path} task_id {task.task_id}"
                )
            if report.attempt != task.attempt:
                result.errors.append(
                    f"{report_path} attempt {report.attempt} does not match {task.path} attempt {task.attempt}"
                )
            expected_task_status = {
                "completed": "completed",
                "done": "completed",
                "blocked": "blocked",
                "incomplete": "incomplete",
                "rejected": "rejected",
                "abandoned": "abandoned",
                "superseded": "superseded",
            }.get(report.status)
            if expected_task_status and task.status != expected_task_status:
                result.errors.append(
                    f"{task.path} must set task status to {expected_task_status} for {report_path}"
                )

        revision = revisions_by_report.get(report_path)
        if revision is None:
            continue
        if report.revision_id != revision.revision_id:
            result.errors.append(
                f"{report_path} revision_id {report.revision_id or '(missing)'} does not match "
                f"{revision.path} revision_id {revision.revision_id}"
            )
        if report.task_id != revision.parent_task_id:
            result.errors.append(
                f"{report_path} task_id {report.task_id or '(missing)'} does not match "
                f"{revision.path} parent_task_id {revision.parent_task_id}"
            )
        expected_revision_status = {
            "completed": "completed",
            "done": "completed",
            "blocked": "blocked",
            "incomplete": "blocked",
        }.get(report.status)
        if expected_revision_status and revision.status != expected_revision_status:
            result.errors.append(
                f"{revision.path} must set revision status to {expected_revision_status} for {report_path}"
            )

    return result
