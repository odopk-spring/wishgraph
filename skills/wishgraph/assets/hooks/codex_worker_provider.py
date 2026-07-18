"""Private Codex native Worker provider behind host_adapter.py."""

from __future__ import annotations

import argparse
import json
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from git_state import (
    apply_session_runtime_patch,
    current_branch,
    inspect_claims,
    read_session_runtime,
)
from workflow_state import canonical_task_id


CODEX_AGENT_THREAD = "codex_agent_thread"
CODEX_RUNNING_STATES = {"starting", "running", "working", "waiting"}
CODEX_TERMINAL_STATES = {"completed", "failed", "stopped", "cancelled"}
CODEX_MODELS = {"gpt-5.6-terra", "gpt-5.6-sol"}
CODEX_EFFORTS = {"minimal", "low", "medium", "high", "xhigh", "max", "ultra"}
CLAUDE_MODELS = {"sonnet", "opus", "fable"}
CLAUDE_EFFORTS = {"low", "medium", "high", "xhigh", "max"}
MODEL_DISPLAY_NAMES = {
    "gpt-5.6-terra": "terra",
    "gpt-5.6-sol": "sol",
}
EFFORT_DISPLAY_NAMES = {
    "minimal": "最低",
    "low": "低",
    "medium": "中",
    "high": "高",
    "xhigh": "极高",
    "max": "最高",
    "ultra": "极强",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _manual_profiles(root: Path, discussion_session_id: str) -> dict[str, dict[str, str]]:
    profiles: dict[str, dict[str, str]] = {"codex": {}, "claude": {}}
    runtime = read_session_runtime(root, discussion_session_id) or {}
    task_runtime = runtime.get("task")
    task_runtime = task_runtime if isinstance(task_runtime, dict) else {}
    recommendations = task_runtime.get("worker_execution_profiles")
    if isinstance(recommendations, dict):
        for host in ("codex", "claude"):
            value = recommendations.get(host)
            if isinstance(value, dict):
                profiles[host].update(
                    {
                        key: str(value[key]).strip()
                        for key in ("model", "reasoning_effort")
                        if value.get(key)
                    }
                )
    worker_runtime = runtime.get("worker_runtime")
    worker_runtime = worker_runtime if isinstance(worker_runtime, dict) else {}
    requested = worker_runtime.get("requested_execution_profile")
    if not isinstance(requested, dict):
        stored = worker_runtime.get("execution_profile")
        requested = stored.get("requested", {}) if isinstance(stored, dict) else {}
    model = str(requested.get("model") or "")
    effort = str(requested.get("reasoning_effort") or "")
    if model in CODEX_MODELS:
        profiles["codex"]["model"] = model
    if effort in CODEX_EFFORTS:
        profiles["codex"]["reasoning_effort"] = effort
    if model in CLAUDE_MODELS:
        profiles["claude"]["model"] = model
    if effort in CLAUDE_EFFORTS:
        profiles["claude"]["reasoning_effort"] = effort
    return profiles


def _manual_command(host: str, profile: dict[str, str]) -> str:
    command = [host]
    if profile.get("model"):
        command.extend(["--model", profile["model"]])
    if profile.get("reasoning_effort"):
        if host == "codex":
            command.extend(
                ["-c", f'model_reasoning_effort="{profile["reasoning_effort"]}"']
            )
        else:
            command.extend(["--effort", profile["reasoning_effort"]])
    return shlex.join(command)


def _manual_profile_display(profile: dict[str, str]) -> str:
    if not profile:
        return "当前默认配置"
    raw_model = profile.get("model", "")
    raw_effort = profile.get("reasoning_effort", "")
    model = MODEL_DISPLAY_NAMES.get(raw_model, raw_model) or "当前默认模型"
    effort = EFFORT_DISPLAY_NAMES.get(raw_effort, raw_effort) or "当前默认强度"
    return f"{model} / {effort}"


def _manual_codex_worker_fallback(
    root: Path,
    discussion_session_id: str,
    task_id: str,
    reason: str,
) -> dict[str, Any]:
    """Persist the strict Codex manual fallback without expanding Discussion rights."""
    persisted = apply_session_runtime_patch(
        root,
        discussion_session_id,
        {
            "session": {
                "phase": "waiting_for_user_launch",
                "expected_transition": {
                    "kind": "launch_worker_manually",
                    "task_id": task_id,
                },
            },
            "worker_runtime": {
                "agent_platform": "codex",
                "host_capability": "manual_command_only",
                "active_task_id": task_id,
                "launch_status": "manual_required",
                "launch_error": reason,
                "claim_id": "",
                "binding_status": "unbound",
                "worker_availability": "manual_required",
                "sync_status": "waiting_for_user_launch",
                "last_observed_at": _utc_now(),
                "worker_handle": {
                    "host": "codex",
                    "container_kind": "",
                    "thread_or_session_id": "",
                    "parent_discussion_id": discussion_session_id,
                    "task_id": task_id,
                    "claim_id": "",
                    "branch": "",
                    "worktree": "",
                    "inspectable": False,
                    "controllable": False,
                    "terminal_state": "not_created",
                    "last_observed_at": _utc_now(),
                },
            },
        },
    )
    profiles = _manual_profiles(root, discussion_session_id)
    codex_profile = profiles["codex"]
    claude_profile = profiles["claude"]
    codex_command = _manual_command("codex", codex_profile)
    claude_command = _manual_command("claude", claude_profile)
    codex_display = _manual_profile_display(codex_profile)
    claude_display = _manual_profile_display(claude_profile)
    return {
        "ok": bool(persisted.get("ok")),
        "launched": False,
        "fallback": True,
        "user_message": f"执行 {task_id} 任务",
        "manual_launch_instructions": "\n".join(
            (
                "自动创建独立 Worker 失败。请任选一个 Agent 启动新会话：",
                "",
                f"本次建议：Codex {codex_display}；Claude Code {claude_display}。",
                "",
                "Codex：",
                f"cd {shlex.quote(str(root.resolve()))}",
                codex_command,
                "",
                "Claude Code：",
                f"cd {shlex.quote(str(root.resolve()))}",
                claude_command,
                "",
                "新会话打开后输入：",
                f"执行 {task_id}",
                "",
                "需要改模型或推理强度时，只修改对应的启动命令参数；任务口令保持不变。",
            )
        ),
        "stop_after_action": True,
        "runtime_persisted": bool(persisted.get("ok")),
        "reason": reason,
    }


def prepare_codex_worker(
    root: Path,
    config: dict[str, Any],
    task_id: str,
    discussion_session_id: str,
    *,
    authorize_launch: Callable[[Path, dict[str, Any], str, str], dict[str, Any]],
    execution_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare an authorized native Codex spawn; never create an Agent from a Hook."""
    canonical = canonical_task_id(task_id)
    if not canonical:
        return {"ok": False, "error": "invalid_task_id"}
    authorized = authorize_launch(
        root, config, discussion_session_id, canonical
    )
    if not authorized.get("ok"):
        return authorized
    task = authorized["task"]
    task_path = str(task.get("task_path") or "")
    report_path = str(task.get("run_report") or "")
    allowed_scope = list(task.get("allowed_scope") or [])
    validation_plan = list(task.get("validation_plan") or [])
    requested_profile = (
        dict(execution_profile) if isinstance(execution_profile, dict) else {}
    )
    host_spawn_options = {
        key: value
        for key, value in (
            ("model", str(requested_profile.get("model") or "")),
            (
                "thinking",
                str(requested_profile.get("reasoning_effort") or ""),
            ),
        )
        if value
    }
    prompt = "\n".join(
        (
            f"执行 {canonical} 任务",
            "你是 Formal WishGraph Worker，不是 Discussion、Integration 或 Helper。",
            f"只读取 prompts/EXECUTION_AI.md、{task_path}、必要项目状态和按需 Reference。",
            f"允许范围：{json.dumps(allowed_scope, ensure_ascii=False)}",
            f"验证计划：{json.dumps(validation_plan, ensure_ascii=False)}",
            f"Run Report：{report_path}",
            f"执行配置：{json.dumps(requested_profile, ensure_ascii=False)}。"
            "仅当当前 Codex 宿主确实支持时才覆盖；否则保持当前宿主默认模型与推理强度。",
            "等宿主用真实 thread ID 注册 launch_context 后，再取得绑定当前 Task、branch、worktree 的 Claim。",
            "不得创建更多 Formal Worker；完成时写结构化终态、Run Report 并释放 Claim。",
        )
    )
    prepared = apply_session_runtime_patch(
        root,
        discussion_session_id,
        {
            "worker_runtime": {
                "agent_platform": "codex",
                "host_capability": "native_agent_thread",
                "active_task_id": canonical,
                "launch_status": "host_spawn_requested",
                "claim_id": "",
                "binding_status": "awaiting_thread_id",
                "worker_availability": "starting",
                "sync_status": "routing_worker",
                "requested_execution_profile": requested_profile,
                "last_observed_at": _utc_now(),
            }
        },
    )
    if not prepared.get("ok"):
        return _manual_codex_worker_fallback(
            root,
            discussion_session_id,
            canonical,
            "codex_spawn_preparation_persistence_failed",
        )
    return {
        "ok": True,
        "prepared": True,
        "task_id": canonical,
        "agent_name": "wishgraph-worker",
        "title": f"{canonical} · WG Worker",
        "prompt": prompt,
        "task_path": task_path,
        "run_report": report_path,
        "allowed_scope": allowed_scope,
        "validation_plan": validation_plan,
        "execution_mode": str(task.get("execution_mode") or "exclusive"),
        "requested_execution_profile": requested_profile,
        "host_spawn_options": host_spawn_options,
        "required_host_result": {
            "thread_or_session_id": "stable non-empty ID",
            "independent_context": True,
            "inspectable": True,
            "controllable": True,
        },
        "stop_after_action": True,
    }


def register_codex_worker(
    root: Path,
    config: dict[str, Any],
    task_id: str,
    discussion_session_id: str,
    thread_id: str,
    *,
    branch: str = "",
    worktree: str = "",
    inspectable: bool = False,
    controllable: bool = False,
    independent_context: bool = False,
    isolated_worktree: bool = False,
    model: str = "",
    reasoning_effort: str = "",
    authorize_launch: Callable[[Path, dict[str, Any], str, str], dict[str, Any]],
) -> dict[str, Any]:
    """Persist a Codex Worker only after the host returns a real inspectable ID."""
    canonical = canonical_task_id(task_id)
    thread_id = str(thread_id or "").strip()
    if not canonical:
        return {"ok": False, "error": "invalid_task_id"}
    if not re.fullmatch(r"[A-Za-z0-9._-]+", thread_id):
        return _manual_codex_worker_fallback(
            root, discussion_session_id, canonical, "codex_thread_id_missing_or_invalid"
        )
    if not (inspectable and controllable and independent_context):
        return _manual_codex_worker_fallback(
            root,
            discussion_session_id,
            canonical,
            "codex_thread_does_not_meet_formal_worker_contract",
        )
    authorized = authorize_launch(
        root, config, discussion_session_id, canonical
    )
    if not authorized.get("ok"):
        return authorized
    task = authorized["task"]
    bound_branch = branch or current_branch(root)
    bound_worktree = str(Path(worktree).resolve()) if worktree else str(root.resolve())
    if (
        task.get("execution_mode") == "competitive"
        and (not isolated_worktree or bound_worktree == str(root.resolve()))
    ):
        return _manual_codex_worker_fallback(
            root,
            discussion_session_id,
            canonical,
            "parallel_formal_worker_requires_independent_worktree",
        )
    now = _utc_now()
    resolved_profile = {
        key: value
        for key, value in (("model", model.strip()), ("reasoning_effort", reasoning_effort.strip()))
        if value
    }
    handle = {
        "host": "codex",
        "container_kind": CODEX_AGENT_THREAD,
        "thread_or_session_id": thread_id,
        "parent_discussion_id": discussion_session_id,
        "task_id": canonical,
        "claim_id": "",
        "branch": bound_branch,
        "worktree": bound_worktree,
        "inspectable": True,
        "controllable": True,
        "terminal_state": "starting",
        "last_observed_at": now,
    }
    worker_runtime = apply_session_runtime_patch(
        root,
        thread_id,
        {
            "session": {
                "session_id": thread_id,
                "role": "neutral",
                "host": "codex",
                "phase": "planning",
                "expected_transition": None,
            },
            "launch_context": {
                "discussion_session_id": discussion_session_id,
                "task_id": canonical,
                "agent_kind": "formal_worker",
                "container_kind": CODEX_AGENT_THREAD,
                "thread_or_session_id": thread_id,
                "branch": bound_branch,
                "worktree": bound_worktree,
                "inspectable": True,
                "controllable": True,
                "independent_context": True,
                "isolated_worktree": isolated_worktree,
                "execution_profile": {
                    "resolved": resolved_profile,
                    "source": "host_spawn_result" if resolved_profile else "current_host_default",
                },
            },
            "worker_runtime": {"worker_handle": handle},
        },
    )
    if not worker_runtime.get("ok"):
        return _manual_codex_worker_fallback(
            root,
            discussion_session_id,
            canonical,
            "codex_worker_session_runtime_persistence_failed",
        )
    persisted = apply_session_runtime_patch(
        root,
        discussion_session_id,
        {
            "session": {
                "phase": "waiting_for_worker",
                "expected_transition": {"kind": "wait_for_worker", "task_id": canonical},
            },
            "worker_runtime": {
                "agent_platform": "codex",
                "host_capability": "native_agent_thread",
                "active_task_id": canonical,
                "host_window_or_thread_id": thread_id,
                "worker_session_id": thread_id,
                "launch_status": "launched",
                "claim_id": "",
                "branch": bound_branch,
                "worktree": bound_worktree,
                "binding_status": "awaiting_claim",
                "worker_availability": "starting",
                "sync_status": "waiting_for_claim",
                "execution_profile": {
                    "resolved": resolved_profile,
                    "source": "host_spawn_result" if resolved_profile else "current_host_default",
                },
                "last_observed_at": now,
                "worker_handle": handle,
            },
        },
    )
    if not persisted.get("ok"):
        return _manual_codex_worker_fallback(
            root,
            discussion_session_id,
            canonical,
            "codex_discussion_runtime_persistence_failed",
        )
    return {
        "ok": True,
        "registered": True,
        "fallback": False,
        "task_id": canonical,
        "thread_or_session_id": thread_id,
        "worker_handle": handle,
        "claim_status": "worker_must_acquire_on_start",
        "stop_after_action": True,
    }


def observe_codex_worker(
    root: Path,
    config: dict[str, Any],
    discussion_session_id: str,
    thread_id: str,
    observed_state: str,
    *,
    resolve_task_record: Callable[[Path, dict[str, Any], str], dict[str, Any]],
) -> dict[str, Any]:
    """Refresh Codex from a structured host state plus durable closeout evidence."""
    runtime = read_session_runtime(root, discussion_session_id)
    if runtime is None:
        return {"ok": False, "error": "discussion_session_runtime_not_found"}
    session = runtime.get("session") if isinstance(runtime.get("session"), dict) else {}
    worker = (
        runtime.get("worker_runtime")
        if isinstance(runtime.get("worker_runtime"), dict)
        else {}
    )
    handle = worker.get("worker_handle") if isinstance(worker.get("worker_handle"), dict) else {}
    if session.get("role") != "discussion":
        return {"ok": False, "error": "discussion_session_required"}
    if (
        handle.get("host") != "codex"
        or handle.get("container_kind") != CODEX_AGENT_THREAD
        or handle.get("thread_or_session_id") != thread_id
        or handle.get("inspectable") is not True
        or handle.get("controllable") is not True
    ):
        return {"ok": False, "error": "codex_worker_handle_mismatch"}
    observed_state = str(observed_state or "").casefold()
    if observed_state not in CODEX_RUNNING_STATES | CODEX_TERMINAL_STATES:
        return {"ok": False, "error": "invalid_codex_structured_state"}
    task_id = canonical_task_id(handle.get("task_id") or worker.get("active_task_id"))
    if not task_id:
        return {"ok": False, "error": "active_codex_worker_not_found"}
    claims = [
        claim
        for claim in inspect_claims(root, task_id)
        if claim.get("agent_platform") == "codex"
        and thread_id
        in {
            str(claim.get("worker_id") or ""),
            str(claim.get("host_thread_ref") or ""),
        }
    ]
    claims.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    claim = claims[0] if claims else None
    resolved = resolve_task_record(root, config, task_id)
    task = resolved.get("task", {}) if resolved.get("ok") else {}
    task_status = str(task.get("status") or "")
    report_path_value = str(task.get("run_report") or "")
    report_exists = bool(report_path_value and (root / report_path_value).is_file())
    claim_released = bool(claim and claim.get("lease_status") == "released")
    durable_terminal = (
        task_status in {"completed", "blocked", "incomplete"}
        and report_exists
        and claim_released
    )
    if durable_terminal:
        phase = "integration_pending"
        expected = {"kind": "auto_integrate", "task_id": task_id}
        sync_status = "integration_pending"
        availability = "terminal"
        recovery_reason = ""
    elif observed_state in CODEX_RUNNING_STATES:
        phase = "waiting_for_worker"
        expected = {"kind": "wait_for_worker", "task_id": task_id}
        sync_status = "waiting_for_worker" if claim else "waiting_for_claim"
        availability = "busy" if claim else "starting"
        recovery_reason = ""
    else:
        phase = "waiting_for_worker"
        expected = {"kind": "wait_for_worker", "task_id": task_id}
        sync_status = "manual_intervention_required"
        availability = "failed" if observed_state == "failed" else "terminal"
        recovery_reason = "terminal_evidence_incomplete"
    now = _utc_now()
    handle_patch = {
        **handle,
        "claim_id": str((claim or {}).get("claim_id") or ""),
        "branch": str((claim or {}).get("branch") or handle.get("branch") or ""),
        "worktree": str((claim or {}).get("worktree") or handle.get("worktree") or ""),
        "terminal_state": observed_state,
        "last_observed_at": now,
    }
    patch: dict[str, Any] = {
        "session": {"phase": phase, "expected_transition": expected},
        "worker_runtime": {
            "claim_id": str((claim or {}).get("claim_id") or ""),
            "branch": handle_patch["branch"],
            "worktree": handle_patch["worktree"],
            "binding_status": str((claim or {}).get("lease_status") or "awaiting_claim"),
            "worker_availability": availability,
            "sync_status": sync_status,
            "recovery_reason": recovery_reason,
            "last_observed_at": now,
            "worker_handle": handle_patch,
        },
    }
    if task_status:
        patch["task"] = {
            "task_id": task_id,
            "lifecycle": task_status,
            "worker_authorized": True,
            "run_report": report_path_value,
        }
    persisted = apply_session_runtime_patch(root, discussion_session_id, patch)
    if not persisted.get("ok"):
        return {"ok": False, "error": "codex_worker_observation_persistence_failed"}
    return {
        "ok": True,
        "task_id": task_id,
        "thread_or_session_id": thread_id,
        "structured_state": observed_state,
        "sync_status": sync_status,
        "durable_terminal_evidence": durable_terminal,
        "phase": phase,
        "recovery_reason": recovery_reason,
    }


def codex_worker_main(
    args: argparse.Namespace,
    *,
    find_git_root_fn: Callable[[Path], Path | None],
    load_config_fn: Callable[[Path], dict[str, Any] | None],
    authorize_launch: Callable[[Path, dict[str, Any], str, str], dict[str, Any]],
    resolve_task_record: Callable[[Path, dict[str, Any], str], dict[str, Any]],
) -> int:
    root = find_git_root_fn(Path.cwd())
    if root is None:
        print(json.dumps({"ok": False, "error": "git_repository_required"}))
        return 2
    try:
        config = load_config_fn(root)
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": "invalid_config", "detail": str(exc)}))
        return 2
    if config is None or config.get("mode") == "off":
        print(json.dumps({"ok": False, "error": "wishgraph_not_active"}))
        return 2
    if args.codex_worker_action == "prepare":
        payload = prepare_codex_worker(
            root,
            config,
            args.task_id,
            args.discussion_session_id,
            authorize_launch=authorize_launch,
            execution_profile={
                key: value
                for key, value in {
                    "model": getattr(args, "model", ""),
                    "reasoning_effort": getattr(args, "reasoning_effort", ""),
                }.items()
                if value
            },
        )
    elif args.codex_worker_action == "register":
        payload = register_codex_worker(
            root,
            config,
            args.task_id,
            args.discussion_session_id,
            args.thread_id,
            branch=args.branch,
            worktree=args.worktree,
            inspectable=args.inspectable,
            controllable=args.controllable,
            independent_context=args.independent_context,
            isolated_worktree=args.isolated_worktree,
            model=getattr(args, "model", ""),
            reasoning_effort=getattr(args, "reasoning_effort", ""),
            authorize_launch=authorize_launch,
        )
    elif args.codex_worker_action == "observe":
        payload = observe_codex_worker(
            root,
            config,
            args.discussion_session_id,
            args.thread_id,
            args.state,
            resolve_task_record=resolve_task_record,
        )
    else:
        canonical = canonical_task_id(args.task_id)
        payload = (
            _manual_codex_worker_fallback(
                root,
                args.discussion_session_id,
                canonical,
                args.reason or "codex_native_agent_spawn_failed",
            )
            if canonical
            else {"ok": False, "error": "invalid_task_id"}
        )
    if payload.get("fallback"):
        print(payload["manual_launch_instructions"])
        return 0
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


def main(
    argv: list[str],
    *,
    find_git_root_fn: Callable[[Path], Path | None],
    load_config_fn: Callable[[Path], dict[str, Any] | None],
    authorize_launch: Callable[[Path, dict[str, Any], str, str], dict[str, Any]],
    resolve_task_record: Callable[[Path, dict[str, Any], str], dict[str, Any]],
) -> int:
    parser = argparse.ArgumentParser(description="WishGraph Codex Worker provider")
    subparsers = parser.add_subparsers(dest="codex_worker_action", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("task_id")
    prepare_parser.add_argument("--discussion-session-id", required=True)
    prepare_parser.add_argument("--model", default="")
    prepare_parser.add_argument("--reasoning-effort", default="")
    register_parser = subparsers.add_parser("register")
    register_parser.add_argument("task_id")
    register_parser.add_argument("--discussion-session-id", required=True)
    register_parser.add_argument("--thread-id", required=True)
    register_parser.add_argument("--branch", default="")
    register_parser.add_argument("--worktree", default="")
    register_parser.add_argument("--inspectable", action="store_true")
    register_parser.add_argument("--controllable", action="store_true")
    register_parser.add_argument("--independent-context", action="store_true")
    register_parser.add_argument("--isolated-worktree", action="store_true")
    register_parser.add_argument("--model", default="")
    register_parser.add_argument("--reasoning-effort", default="")
    observe_parser = subparsers.add_parser("observe")
    observe_parser.add_argument("--discussion-session-id", required=True)
    observe_parser.add_argument("--thread-id", required=True)
    observe_parser.add_argument(
        "--state",
        choices=tuple(sorted(CODEX_RUNNING_STATES | CODEX_TERMINAL_STATES)),
        required=True,
    )
    fail_parser = subparsers.add_parser("fail")
    fail_parser.add_argument("task_id")
    fail_parser.add_argument("--discussion-session-id", required=True)
    fail_parser.add_argument("--reason", default="")
    return codex_worker_main(
        parser.parse_args(argv),
        find_git_root_fn=find_git_root_fn,
        load_config_fn=load_config_fn,
        authorize_launch=authorize_launch,
        resolve_task_record=resolve_task_record,
    )
