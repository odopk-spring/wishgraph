from __future__ import annotations

import ast
import concurrent.futures
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from unittest import mock
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
HOOK_ASSETS = ROOT / "skills" / "wishgraph" / "assets" / "hooks"
INSTALLER = ROOT / "skills" / "wishgraph" / "scripts" / "install_project_hooks.py"
TOP_LEVEL_INSTALLER = ROOT / "scripts" / "install-wishgraph.sh"
POWERSHELL_INSTALLER = ROOT / "scripts" / "install-wishgraph.ps1"


def load_runtime_module():
    path = HOOK_ASSETS / "memory_sync.py"
    spec = importlib.util.spec_from_file_location("wishgraph_memory_sync", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_installer_module():
    spec = importlib.util.spec_from_file_location("wishgraph_installer", INSTALLER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


memory_sync = load_runtime_module()
installer_module = load_installer_module()


class RuntimeBoundaryTests(unittest.TestCase):
    def test_runtime_dependencies_follow_the_four_boundaries(self) -> None:
        local_modules = {
            "git_state",
            "workflow_state",
            "policy",
            "host_adapter",
            "codex_worker_provider",
        }
        public_boundaries = local_modules - {"codex_worker_provider"}
        expected = {
            "git_state.py": set(),
            "workflow_state.py": set(),
            "policy.py": {"git_state", "workflow_state"},
            "host_adapter.py": {
                "git_state",
                "policy",
                "workflow_state",
                "codex_worker_provider",
            },
            "codex_worker_provider.py": {"git_state", "workflow_state"},
            "memory_sync.py": public_boundaries,
        }

        for filename, expected_imports in expected.items():
            with self.subTest(runtime=filename):
                tree = ast.parse((HOOK_ASSETS / filename).read_text(encoding="utf-8"))
                imports: set[str] = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imports.update(alias.name.split(".", 1)[0] for alias in node.names)
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        imports.add(node.module.split(".", 1)[0])
                self.assertEqual(imports & local_modules, expected_imports)

    def test_host_hook_configs_install_write_and_build_gate_matchers(self) -> None:
        codex = json.loads((HOOK_ASSETS / "codex-hooks.json").read_text())
        claude = json.loads((HOOK_ASSETS / "claude-settings.json").read_text())
        for name, config in (("codex", codex), ("claude", claude)):
            with self.subTest(host=name):
                matcher = config["hooks"]["PreToolUse"][0]["matcher"]
                self.assertIn("Bash", matcher)
                self.assertIn("Write", matcher)
                self.assertIn("Edit", matcher)
                self.assertIn("mcp__", matcher)
                self.assertIn("UserPromptSubmit", config["hooks"])

    def test_claude_worker_agent_keeps_task_claim_and_read_boundaries(self) -> None:
        content = (
            ROOT
            / "skills"
            / "wishgraph"
            / "assets"
            / "claude-agents"
            / "wishgraph-worker.md"
        ).read_text(encoding="utf-8")
        self.assertIn("name: wishgraph-worker", content)
        self.assertIn("isolation: worktree", content)
        self.assertIn(memory_sync.CLAUDE_WORKER_AGENT_MARKER, content)
        self.assertIn("acquire a Worker Claim", content)
        self.assertIn("Do not read unrelated Tasks", content)
        self.assertIn("Write exactly one immutable Run Report", content)
        self.assertIn("Release the Claim", content)

    def test_codex_worker_agent_uses_current_project_custom_agent_format(self) -> None:
        content = (
            ROOT
            / "skills"
            / "wishgraph"
            / "assets"
            / "codex-agents"
            / "wishgraph-worker.toml"
        ).read_text(encoding="utf-8")
        self.assertIn('name = "wishgraph-worker"', content)
        self.assertIn('description = "', content)
        self.assertIn("developer_instructions =", content)
        self.assertIn("codex_agent_thread", content)
        self.assertIn("Do not scan unrelated Tasks", content)
        self.assertIn("must not acquire this Claim", content)

    def test_user_prompt_hook_routes_but_never_launches_claude_process(self) -> None:
        tree = ast.parse(
            (HOOK_ASSETS / "host_adapter.py").read_text(encoding="utf-8")
        )
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "user_prompt_submit_main"
        )
        calls = {
            node.func.id
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertNotIn("launch_claude_worker", calls)
        self.assertNotIn("_run_process", calls)

    def test_low_risk_prompt_parser_accepts_bounded_aliases_and_politeness(self) -> None:
        cases = {
            "开始讨论。\n": "start_discussion",
            "“开始讨论‘": "start_discussion",
            "进入讨论模式": "start_discussion",
            "回到 Discussion": "start_discussion",
            "请   回到   DISCUSSION，谢谢！": "start_discussion",
            "请问可以进入讨论模式吗？": "start_discussion",
            "Start   Discussion, please.": "start_discussion",
            "刷新项目状态！": "refresh_project_status",
            "麻烦帮我刷新一下项目状态，谢谢！": "refresh_project_status",
            "Please refresh PROJECT status.": "refresh_project_status",
        }
        for prompt, action in cases.items():
            with self.subTest(prompt=prompt):
                parsed = memory_sync.parse_user_prompt(prompt)
                self.assertIsNotNone(parsed)
                assert parsed is not None
                self.assertEqual(parsed["action"], action)
                self.assertFalse(parsed["authorizes_execution"])

    def test_low_risk_prompt_parser_accepts_english_discussion_entry_aliases(self) -> None:
        for prompt in (
            "begin discussion",
            "open discussion",
            "enter discussion mode",
            "continue discussion",
            "resume discussion mode",
        ):
            with self.subTest(prompt=prompt):
                self.assertEqual(
                    memory_sync.parse_user_prompt(prompt),
                    {"action": "start_discussion", "authorizes_execution": False},
                )

    def test_low_risk_prompt_parser_accepts_english_project_status_aliases(self) -> None:
        for prompt in (
            "check project status",
            "update project status",
            "reload project status",
        ):
            with self.subTest(prompt=prompt):
                self.assertEqual(
                    memory_sync.parse_user_prompt(prompt),
                    {
                        "action": "refresh_project_status",
                        "authorizes_execution": False,
                    },
                )

    def test_low_risk_prompt_parser_rejects_conversational_or_compound_text(self) -> None:
        for prompt in (
            "我们讨论一下颜色",
            "请讨论一下颜色",
            "进入讨论模式后执行 012",
            "刷新项目状态并执行 012",
            "回到 Discussion 看看",
        ):
            with self.subTest(prompt=prompt):
                self.assertIsNone(memory_sync.parse_user_prompt(prompt))

    def test_authority_bearing_task_commands_remain_strict(self) -> None:
        routed = memory_sync.parse_user_prompt("重新执行 012ba 号任务！")
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["action"], "retry")
        self.assertEqual(routed["task_id"], "012ba")
        self.assertTrue(routed["authorizes_execution"])

        for prompt in (
            "执行任务",
            "执行任务 012",
            "请执行 012 任务",
            "执行 012 任务吧",
            "执行 012 和 013 任务",
            "执行 12 任务",
            "我们执行 012 任务",
        ):
            with self.subTest(prompt=prompt):
                self.assertIsNone(memory_sync.parse_user_prompt(prompt))

    def test_entry_commands_require_explicit_project_activation(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)

            def submit(session_id: str, prompt: str) -> dict[str, object]:
                process = subprocess.run(
                    [
                        sys.executable,
                        str(HOOK_ASSETS / "memory_sync.py"),
                        "user-prompt-submit",
                        "--host",
                        "codex",
                    ],
                    cwd=root,
                    input=json.dumps(
                        {
                            "cwd": str(root),
                            "session_id": session_id,
                            "prompt": prompt,
                        }
                    ),
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                )
                return json.loads(process.stdout)

            prompts = (
                "开始讨论",
                "进入讨论模式",
                "回到 Discussion",
                "请刷新一下项目状态",
                "执行 012 任务",
            )
            for index, prompt in enumerate(prompts):
                with self.subTest(state="missing-config", prompt=prompt):
                    self.assertEqual(submit(f"missing-config-{index}", prompt), {})
            self.assertFalse((root / ".git" / "wishgraph" / "sessions").exists())

            config = json.loads((HOOK_ASSETS / "config.json").read_text())
            config["mode"] = "off"
            (root / ".wishgraph").mkdir()
            (root / ".wishgraph" / "config.json").write_text(
                json.dumps(config), encoding="utf-8"
            )
            for index, prompt in enumerate(prompts):
                with self.subTest(state="explicitly-off", prompt=prompt):
                    self.assertEqual(submit(f"explicitly-off-{index}", prompt), {})
            self.assertFalse((root / ".git" / "wishgraph" / "sessions").exists())

    def test_gate_recognizes_common_build_commands_and_mcp_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            config = json.loads((HOOK_ASSETS / "config.json").read_text())
            for command in (
                "swift test",
                "dotnet build",
                "cmake --build build",
                "bazel test //...",
                "uv run pytest",
                "bun run build",
            ):
                with self.subTest(command=command):
                    operation = memory_sync.classify_tool_operation(
                        root,
                        config,
                        {"tool_name": "Bash", "tool_input": {"command": command}},
                    )
                    self.assertEqual(operation[0], "build_test")
            mcp = memory_sync.classify_tool_operation(
                root,
                config,
                {
                    "tool_name": "mcp__filesystem__write_file",
                    "tool_input": {"path": "src/app.py"},
                },
            )
            self.assertEqual(mcp[0], "business_write")

    def test_skill_entrypoint_is_lean_and_routes_every_reference(self) -> None:
        skill_path = ROOT / "skills" / "wishgraph" / "SKILL.md"
        content = skill_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        self.assertLessEqual(len(lines), 100)
        self.assertLess(len(content.encode("utf-8")), 10 * 1024)

        routed = set(re.findall(r"`references/([^`]+\.md)`", content))
        actual = {
            path.name
            for path in (ROOT / "skills" / "wishgraph" / "references").glob("*.md")
        }
        self.assertEqual(routed, actual)
        for expected in (
            "Treat global Skill installation as availability, never project activation.",
            "missing config or `mode: off` means inactive",
            "Require a later explicit `开始讨论` / `Start discussion` event",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, content)

    def test_revision_fast_path_loads_one_reference_until_an_exception(self) -> None:
        skill = (ROOT / "skills" / "wishgraph" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        revision = (
            ROOT / "skills" / "wishgraph" / "references" / "task-revisions.md"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "Clear low-risk correction: read only `references/task-revisions.md`; "
            "expand only through its exception table.",
            skill,
        )
        for expected in (
            "Do not ask whether to create the Revision Worker",
            "worker_creation_authorized\": true",
            "Acquire a fresh Claim",
            "Runs only the targeted validation",
            "Every terminal Revision enters `integration_pending` automatically",
            "## Exception Routing",
            "Do not load exception references pre-emptively",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, revision)

    def test_non_commit_pretool_gate_never_enumerates_source_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            config = json.loads((HOOK_ASSETS / "config.json").read_text())
            memory_sync.write_session_runtime(
                root,
                "neutral-session",
                {
                    "session": {
                        "session_id": "neutral-session",
                        "role": "neutral",
                        "host": "codex",
                        "phase": "planning",
                        "expected_transition": None,
                    }
                },
            )
            claim = memory_sync.acquire_claim(
                root,
                "012",
                1,
                "worker-session",
                host_thread_ref="worker-session",
                allowed_scope=["src/**"],
                validation_plan=["python3 -m unittest"],
                require_clean=False,
            )
            self.assertTrue(claim["ok"], claim)
            memory_sync.write_session_runtime(
                root,
                "worker-session",
                {
                    "session": {
                        "session_id": "worker-session",
                        "role": "worker",
                        "host": "codex",
                        "phase": "waiting_for_worker",
                        "expected_transition": {
                            "kind": "wait_for_worker",
                            "task_id": "012",
                        },
                    },
                    "task": {
                        "task_id": "012",
                        "lifecycle": "running",
                        "worker_authorized": True,
                    },
                },
            )

            git_state_module = sys.modules["git_state"]
            original_run_git = git_state_module.run_git
            original_glob = Path.glob
            forbidden_git = {"status", "diff", "ls-files", "ls-tree", "for-each-ref"}

            def guarded_git(path: Path, *args: str, **kwargs: object):
                if args and args[0] in forbidden_git:
                    raise AssertionError(f"hot path enumerated Git source state: {args}")
                return original_run_git(path, *args, **kwargs)

            def guarded_glob(path: Path, pattern: str):
                if "**" in pattern:
                    raise AssertionError(f"hot path used recursive glob: {pattern}")
                return original_glob(path, pattern)

            neutral_payload = {
                "cwd": str(root),
                "session_id": "neutral-session",
                "host": "codex",
                "tool_name": "Write",
                "tool_input": {"file_path": str(root / "src" / "probe.py")},
            }
            worker_payload = {
                **neutral_payload,
                "session_id": "worker-session",
            }
            with (
                mock.patch.object(git_state_module, "run_git", side_effect=guarded_git),
                mock.patch.object(Path, "glob", new=guarded_glob),
                mock.patch.object(
                    Path,
                    "rglob",
                    side_effect=AssertionError("hot path used Path.rglob"),
                ),
                mock.patch.object(
                    os,
                    "walk",
                    side_effect=AssertionError("hot path used os.walk"),
                ),
            ):
                denied = memory_sync.orchestration_gate_plan(root, config, neutral_payload)
                allowed = memory_sync.orchestration_gate_plan(root, config, worker_payload)

            self.assertIsNotNone(denied)
            self.assertFalse(denied.accepted)
            self.assertIsNotNone(allowed)
            self.assertTrue(allowed.accepted)


class OrchestrationStateMachineTests(unittest.TestCase):
    def state(
        self,
        *,
        role: str = "discussion",
        phase: str = "awaiting_worker_authorization",
        task_id: str = "002",
        lifecycle: str = "draft",
        worker_authorized: bool = False,
        expected_kind: Optional[str] = "approve_worker_launch",
        candidates: tuple[str, ...] = (),
        worker_claim_id: str = "",
        integration_lease_id: str = "",
        integration_id: str = "",
        expected_task_id: str = "",
        expected_integration_id: str = "",
        pending_decision_id: str = "",
        active_task_id: str = "",
        previous_task_id: str = "",
        worker_window_id: str = "",
        worker_availability: str = "unknown",
        binding_status: str = "unbound",
        allowed_scope: tuple[str, ...] = (),
        validation_plan: tuple[str, ...] = (),
    ):
        expected = (
            memory_sync.ExpectedTransition(
                kind=expected_kind,
                task_id=expected_task_id or task_id,
                integration_id=expected_integration_id,
            )
            if expected_kind
            else None
        )
        return memory_sync.OrchestrationState(
            session=memory_sync.SessionFlowState(
                session_id="session-1",
                role=role,
                host="codex",
                phase=phase,
                expected_transition=expected,
            ),
            task=memory_sync.TaskFlowState(
                task_id=task_id,
                lifecycle=lifecycle,
                worker_authorized=worker_authorized,
                run_report=f"reports/runs/{task_id}-attempt-1.md",
            ),
            worker_runtime=memory_sync.WorkerRuntimeState(
                claim_id=worker_claim_id,
                active_task_id=active_task_id,
                previous_task_id=previous_task_id,
                host_window_or_thread_id=worker_window_id,
                worker_availability=worker_availability,
                binding_status=binding_status,
                allowed_scope=allowed_scope,
                validation_plan=validation_plan,
            ),
            integration_runtime=memory_sync.IntegrationRuntimeState(
                lease_id=integration_lease_id,
                integration_id=integration_id,
            ),
            pending_decision=memory_sync.PendingDecisionState(
                decision_id=pending_decision_id
            ),
            candidate_task_ids=candidates,
        )

    def event(self, kind: str, **data: object):
        return memory_sync.UserEvent(kind=kind, data=data)

    def capability(
        self,
        host: str = "codex",
        create_worker: bool = True,
        route_worker: bool = False,
        reuse_worker: bool = False,
    ):
        return memory_sync.HostCapability(
            host=host,
            can_spawn_execution_thread=create_worker,
            can_inspect_execution_thread=create_worker or route_worker or reuse_worker,
            can_bind_thread_id=create_worker or route_worker or reuse_worker,
            can_stop_or_steer_thread=create_worker or route_worker or reuse_worker,
            can_isolate_worktree=host == "claude",
            can_observe_terminal_result=create_worker or reuse_worker,
            can_gate_writes=True,
            can_gate_builds=True,
            can_gate_reads=False,
            can_deliver_result_to_discussion=create_worker,
        )

    def test_osm_01_contextual_approval_routes_worker_without_discussion_execution(self) -> None:
        plan = memory_sync.reduce_orchestration(
            self.state(),
            self.event("user_message", text="执行吧"),
            self.capability(),
        )
        self.assertTrue(plan.accepted)
        self.assertEqual(plan.next_action, "launch_worker")
        self.assertEqual(plan.state_patch["session"]["phase"], "routing_worker")
        self.assertEqual(plan.state_patch["task"]["lifecycle"], "approved")
        self.assertTrue(plan.state_patch["task"]["worker_authorized"])
        self.assertNotEqual(plan.next_action, "discussion_window_implements_business_code")

    def test_osm_02_neutral_explicit_execute_enters_worker_with_claim_requirement(self) -> None:
        plan = memory_sync.reduce_orchestration(
            self.state(
                role="neutral",
                phase="planning",
                lifecycle="approved",
                worker_authorized=True,
                expected_kind=None,
            ),
            self.event("user_message", text="执行 002 任务"),
            self.capability(),
        )
        self.assertEqual(plan.next_action, "enter_worker")
        self.assertTrue(plan.required_claim)
        self.assertEqual(plan.state_patch["session"]["role"], "worker")
        self.assertEqual(plan.state_patch["task"]["lifecycle"], "running")

    def test_osm_03_claude_launch_routes_to_host_adapter_and_stops_discussion(self) -> None:
        plan = memory_sync.reduce_orchestration(
            self.state(),
            self.event("user_message", text="可以"),
            self.capability(host="claude", create_worker=True),
        )
        action = memory_sync.map_flow_plan_to_host(
            plan, self.capability(host="claude", create_worker=True)
        )
        self.assertEqual(action.action, "launch_claude_background_worker")
        self.assertEqual(action.user_message, "")
        self.assertTrue(action.stop_after_action)
        self.assertTrue(action.creates_inspectable_thread)
        self.assertEqual(action.state_patch["session"]["phase"], "routing_worker")
        self.assertEqual(action.work_payload["task_id"], "002")

    def test_osm_03b_codex_launch_routes_to_native_inspectable_agent_thread(self) -> None:
        plan = memory_sync.reduce_orchestration(
            self.state(),
            self.event("user_message", text="可以"),
            self.capability(host="codex", create_worker=True),
        )
        action = memory_sync.map_flow_plan_to_host(
            plan, self.capability(host="codex", create_worker=True)
        )
        self.assertEqual(action.action, "launch_codex_agent_worker")
        self.assertTrue(action.creates_inspectable_thread)
        self.assertEqual(action.work_payload["agent_name"], "wishgraph-worker")
        self.assertTrue(action.work_payload["requires_real_thread_id"])

    def test_osm_04_codex_launch_failure_uses_same_one_line_fallback(self) -> None:
        plan = memory_sync.reduce_orchestration(
            self.state(phase="routing_worker", lifecycle="approved", worker_authorized=True),
            self.event("host_worker_launch_failed", reason="creation_failed"),
            self.capability(),
        )
        self.assertEqual(plan.next_action, "show_manual_worker_command")
        self.assertEqual(plan.user_message, "执行 002 任务")
        self.assertTrue(plan.stop_after_action)
        self.assertEqual(plan.state_patch["session"]["phase"], "waiting_for_user_launch")

    def test_osm_04b_unknown_host_uses_manual_one_line_fallback(self) -> None:
        plan = memory_sync.reduce_orchestration(
            self.state(),
            self.event("user_message", text="可以"),
            self.capability(host="unknown", create_worker=False),
        )
        action = memory_sync.map_flow_plan_to_host(
            plan, self.capability(host="unknown", create_worker=False)
        )
        self.assertEqual(action.action, "show_manual_worker_command")
        self.assertEqual(action.user_message, "执行 002 任务")
        self.assertTrue(action.stop_after_action)
        self.assertFalse(action.creates_inspectable_thread)

    def test_osm_05_safe_worker_terminal_auto_enters_local_integration(self) -> None:
        pending = memory_sync.reduce_orchestration(
            self.state(
                phase="waiting_for_worker",
                lifecycle="running",
                worker_authorized=True,
                expected_kind="wait_for_worker",
                worker_claim_id="claim-1",
            ),
            self.event(
                "worker_terminal",
                task_status="completed",
                report_id="reports/runs/002-attempt-1.md",
                claim_released=True,
            ),
            self.capability(),
        )
        self.assertEqual(pending.next_action, "evaluate_integration")
        self.assertEqual(pending.state_patch["session"]["phase"], "integration_pending")
        integrating = memory_sync.reduce_orchestration(
            self.state(
                phase="integration_pending",
                lifecycle="completed",
                worker_authorized=True,
                expected_kind="auto_integrate",
            ),
            self.event("integration_evaluated", outcome="safe"),
            self.capability(),
        )
        self.assertEqual(integrating.next_action, "enter_discussion_local_integration")
        self.assertTrue(integrating.required_integration_lease)
        self.assertEqual(integrating.state_patch["session"]["phase"], "integrating")
        self.assertFalse(integrating.user_message)

    def test_osm_06_integration_host_action_stays_in_discussion_window(self) -> None:
        plan = memory_sync.FlowPlan(
            accepted=True,
            next_action="enter_discussion_local_integration",
            required_integration_lease=True,
        )
        action = memory_sync.map_flow_plan_to_host(plan, self.capability())
        self.assertEqual(action.action, "enter_discussion_local_integration")
        self.assertFalse(action.creates_inspectable_thread)

    def test_osm_07_high_risk_asks_material_decision_not_integration_permission(self) -> None:
        plan = memory_sync.reduce_orchestration(
            self.state(
                phase="integration_pending",
                lifecycle="completed",
                worker_authorized=True,
                expected_kind="auto_integrate",
            ),
            self.event(
                "integration_evaluated",
                outcome="decision_required",
                decision_id="public-api-compat",
                question="002 修改了公共 API，是否采用兼容方案 A？",
            ),
            self.capability(),
        )
        self.assertEqual(plan.next_action, "ask_material_decision")
        self.assertEqual(plan.state_patch["session"]["phase"], "decision_required")
        self.assertIn("公共 API", plan.user_message)
        self.assertNotIn("是否集成", plan.user_message)

    def test_osm_08_discussion_business_write_and_build_are_denied(self) -> None:
        for operation in ("business_write", "build_test"):
            with self.subTest(operation=operation):
                plan = memory_sync.reduce_orchestration(
                    self.state(
                        phase="planning",
                        lifecycle="approved",
                        worker_authorized=True,
                        expected_kind=None,
                    ),
                    self.event("operation_requested", operation=operation),
                    self.capability(),
                )
                self.assertEqual(plan.next_action, "deny_role_violation")
                self.assertFalse(plan.accepted)
                self.assertIn("Claim", plan.denial_reason)

    def test_osm_09_contextual_approval_cannot_choose_between_two_tasks(self) -> None:
        plan = memory_sync.reduce_orchestration(
            self.state(expected_kind=None, candidates=("002", "003")),
            self.event("user_message", text="可以"),
            self.capability(),
        )
        self.assertEqual(plan.next_action, "ask_task_choice")
        self.assertIn("002", plan.user_message)
        self.assertIn("003", plan.user_message)

    def test_osm_10_task_ids_are_always_exact(self) -> None:
        for text, expected in (
            ("执行 002 任务", "002"),
            ("执行 002b 任务", "002b"),
            ("执行 002ba 任务", "002ba"),
        ):
            with self.subTest(text=text):
                command = memory_sync.parse_task_command(text)
                assert command is not None
                self.assertEqual(command["task_id"], expected)

    def test_osm_11_launch_success_is_not_committed_before_runtime_persists(self) -> None:
        plan = memory_sync.reduce_orchestration(
            self.state(phase="routing_worker", lifecycle="approved", worker_authorized=True),
            self.event(
                "host_worker_launch_succeeded",
                thread_id="real-thread-1",
                runtime_persisted=False,
            ),
            self.capability(),
        )
        self.assertEqual(plan.next_action, "retry_runtime_persistence")
        self.assertNotEqual(
            plan.state_patch.get("session", {}).get("phase"), "waiting_for_worker"
        )

    def test_osm_12_integration_lease_is_exclusive(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            first = memory_sync.acquire_integration_lease(
                root,
                session_id="discussion-1",
                integration_id="integration-1",
                task_ids=["002"],
                reports=["reports/runs/002-attempt-1.md"],
                require_clean=False,
            )
            second = memory_sync.acquire_integration_lease(
                root,
                session_id="discussion-2",
                integration_id="integration-2",
                task_ids=["003"],
                reports=["reports/runs/003-attempt-1.md"],
                require_clean=False,
            )
            self.assertTrue(first["ok"])
            self.assertFalse(second["ok"])
            self.assertEqual(second["error"], "active_integration_lease_exists")

    def test_osm_13_invalid_completed_report_is_normalized_to_blocked(self) -> None:
        plan = memory_sync.reduce_orchestration(
            self.state(
                phase="integration_pending",
                lifecycle="completed",
                worker_authorized=True,
                expected_kind="auto_integrate",
            ),
            self.event("integration_evaluated", outcome="blocked", reason="validation_failed"),
            self.capability(),
        )
        self.assertEqual(plan.next_action, "repair_worker_closeout")
        self.assertEqual(plan.state_patch["task"]["lifecycle"], "blocked")
        self.assertEqual(plan.state_patch["session"]["phase"], "waiting_for_worker")

    def test_osm_14_refresh_does_not_consume_expected_transition(self) -> None:
        current = self.state()
        plan = memory_sync.reduce_orchestration(
            current, self.event("refresh"), self.capability()
        )
        self.assertEqual(plan.next_action, "read_status")
        self.assertEqual(plan.state_patch, {})
        self.assertEqual(current.session.expected_transition.kind, "approve_worker_launch")

    def test_osm_15_direct_edit_request_never_authorizes_discussion_implementation(self) -> None:
        plan = memory_sync.reduce_orchestration(
            self.state(),
            self.event("user_message", text="就在当前窗口直接修改"),
            self.capability(),
        )
        self.assertEqual(plan.next_action, "ask_for_worker_authorization")
        self.assertNotEqual(plan.next_action, "discussion_window_implements_business_code")
        self.assertIn("Worker", plan.denial_reason)

    def test_integration_completion_presents_then_accepts_result(self) -> None:
        completed = memory_sync.reduce_orchestration(
            self.state(
                phase="integrating",
                lifecycle="completed",
                expected_kind=None,
                integration_lease_id="lease-1",
                integration_id="integration-002",
            ),
            self.event("integration_completed", integration_id="integration-002"),
            self.capability(),
        )
        self.assertEqual(completed.next_action, "present_result")
        self.assertEqual(completed.state_patch["task"]["lifecycle"], "integrated")
        self.assertEqual(
            completed.state_patch["session"]["phase"], "presenting_result"
        )
        accepted = memory_sync.reduce_orchestration(
            self.state(
                phase="presenting_result",
                lifecycle="integrated",
                expected_kind="accept_result",
                expected_integration_id="integration-002",
            ),
            self.event("user_message", text="可以"),
            self.capability(),
        )
        self.assertEqual(accepted.next_action, "accept_result")
        self.assertEqual(accepted.state_patch["task"]["lifecycle"], "reviewed")

    def test_decision_resolution_must_match_pending_decision(self) -> None:
        stale = memory_sync.reduce_orchestration(
            self.state(
                phase="decision_required",
                lifecycle="completed",
                expected_kind="resolve_conflict",
                pending_decision_id="decision-a",
            ),
            self.event("decision_resolved", decision_id="decision-b", option="A"),
            self.capability(),
        )
        self.assertFalse(stale.accepted)
        resolved = memory_sync.reduce_orchestration(
            self.state(
                phase="decision_required",
                lifecycle="completed",
                expected_kind="resolve_conflict",
                pending_decision_id="decision-a",
            ),
            self.event("decision_resolved", decision_id="decision-a", option="A"),
            self.capability(),
        )
        self.assertEqual(resolved.next_action, "evaluate_integration")
        self.assertEqual(resolved.state_patch["session"]["phase"], "integration_pending")

    def test_stale_contextual_transition_cannot_launch_or_review_another_task(self) -> None:
        launch = memory_sync.reduce_orchestration(
            self.state(expected_task_id="003"),
            self.event("user_message", text="执行吧"),
            self.capability(),
        )
        self.assertFalse(launch.accepted)
        self.assertEqual(launch.next_action, "ask_task_choice")
        review = memory_sync.reduce_orchestration(
            self.state(
                phase="presenting_result",
                lifecycle="draft",
                expected_kind="accept_result",
                expected_integration_id="integration-002",
            ),
            self.event("user_message", text="可以"),
            self.capability(),
        )
        self.assertFalse(review.accepted)
        self.assertEqual(review.denial_reason, "result_acceptance_transition_is_stale")

    def test_safe_integration_cannot_absorb_non_completed_task(self) -> None:
        plan = memory_sync.reduce_orchestration(
            self.state(
                phase="integration_pending",
                lifecycle="blocked",
                expected_kind="auto_integrate",
            ),
            self.event("integration_evaluated", outcome="safe"),
            self.capability(),
        )
        self.assertFalse(plan.accepted)
        self.assertEqual(plan.next_action, "repair_worker_closeout")


class WorkerReuseRevisionSpecTests(unittest.TestCase):
    state = OrchestrationStateMachineTests.state
    event = OrchestrationStateMachineTests.event
    capability = OrchestrationStateMachineTests.capability

    def revision_data(self, **overrides: object) -> dict[str, object]:
        data: dict[str, object] = {
            "parent_task_id": "012",
            "user_request": "蓝色深一点",
            "request_is_clear": True,
            "belongs_to_parent_task": True,
            "small_scope": True,
            "independently_revertible": True,
            "allowed_scope": ["ui/ReaderTheme.swift"],
            "validation_plan": ["Reader preview"],
            "public_api_change": False,
            "schema_change": False,
            "persistence_change": False,
            "migration_change": False,
            "dependency_change": False,
            "permission_change": False,
            "security_impact": False,
            "privacy_impact": False,
            "new_product_decision": False,
        }
        data.update(overrides)
        return data

    def test_reuse_01_terminal_worker_can_rebind_012_to_013(self) -> None:
        plan = memory_sync.reduce_orchestration(
            self.state(
                role="worker",
                task_id="012",
                lifecycle="completed",
                expected_kind=None,
                worker_claim_id="claim-012",
                active_task_id="012",
                binding_status="active",
            ),
            self.event(
                "task_rebind_requested",
                next_task_id="013",
                current_task_terminal=True,
                old_claim_released=True,
                allowed_scope=["src/013/**"],
                validation_plan=["test 013"],
            ),
            self.capability(reuse_worker=True),
        )
        self.assertEqual(plan.next_action, "rebind_worker")
        self.assertEqual(plan.state_patch["worker_runtime"]["active_task_id"], "013")

    def test_reuse_02_running_worker_cannot_rebind(self) -> None:
        plan = memory_sync.reduce_orchestration(
            self.state(
                role="worker",
                task_id="012",
                lifecycle="running",
                expected_kind=None,
                worker_claim_id="claim-012",
                active_task_id="012",
                binding_status="active",
            ),
            self.event(
                "task_rebind_requested",
                next_task_id="013",
                current_task_terminal=False,
                old_claim_released=False,
                allowed_scope=["src/013/**"],
                validation_plan=["test 013"],
            ),
            self.capability(reuse_worker=True),
        )
        self.assertFalse(plan.accepted)
        self.assertEqual(plan.next_action, "deny_worker_rebind")

    def test_reuse_03_rebind_releases_old_claim_and_acquires_new(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            old = memory_sync.acquire_claim(
                root,
                "012",
                1,
                "worker-1",
                allowed_scope=["src/012/**"],
                validation_plan=["test 012"],
                require_clean=False,
            )
            result = memory_sync.rebind_worker_claim(
                root,
                session_id="worker-1",
                old_claim_id=old["claim"]["claim_id"],
                old_task_status="completed",
                next_task_id="013",
                attempt=1,
                worker_id="worker-1",
                allowed_scope=["src/013/**"],
                validation_plan=["test 013"],
                require_clean=False,
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["old_claim"]["lease_status"], "released")
            self.assertEqual(result["claim"]["task_id"], "013")

    def test_reuse_04_rebind_resets_scope_and_validation(self) -> None:
        plan = memory_sync.reduce_orchestration(
            self.state(
                role="worker",
                task_id="012",
                lifecycle="completed",
                expected_kind=None,
                allowed_scope=("src/012/**",),
                validation_plan=("test 012",),
            ),
            self.event(
                "task_rebind_requested",
                next_task_id="013",
                current_task_terminal=True,
                old_claim_released=True,
                allowed_scope=["src/013/**"],
                validation_plan=["test 013"],
            ),
            self.capability(reuse_worker=True),
        )
        runtime = plan.state_patch["worker_runtime"]
        self.assertEqual(runtime["allowed_scope"], ["src/013/**"])
        self.assertEqual(runtime["validation_plan"], ["test 013"])
        self.assertNotIn("src/012/**", runtime["allowed_scope"])

    def test_reuse_task_spec_reads_table_scope_and_clean_validation_items(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            task_path = root / "tasks/build/012-table-scope.md"
            task_path.parent.mkdir(parents=True)
            task_path.write_text(
                (ROOT / "templates/tasks/build/EXAMPLE-good-task.md").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            config = json.loads((HOOK_ASSETS / "config.json").read_text())

            specs = memory_sync.task_specs(root, config)

            self.assertEqual(
                specs[0]["allowed_scope"],
                [
                    "src/dashboard/DashboardPage.tsx",
                    "src/auth/sessionStore.ts",
                    "tests/dashboard-loading.test.tsx",
                ],
            )
            self.assertIn("npm test -- dashboard", specs[0]["validation_plan"])
            self.assertTrue(
                all(not item.startswith("[ ]") for item in specs[0]["validation_plan"])
            )

    def test_revision_05_worker_appends_feedback_to_running_task(self) -> None:
        plan = memory_sync.reduce_orchestration(
            self.state(
                role="worker",
                task_id="012",
                lifecycle="running",
                expected_kind=None,
                worker_claim_id="claim-012",
                active_task_id="012",
                binding_status="active",
            ),
            self.event("worker_feedback_received", **self.revision_data()),
            self.capability(),
        )
        self.assertEqual(plan.next_action, "append_feedback_to_active_task")
        self.assertFalse(plan.revision_id)

    def test_revision_06_discussion_routes_feedback_to_active_worker(self) -> None:
        plan = memory_sync.reduce_orchestration(
            self.state(
                task_id="012",
                lifecycle="running",
                expected_kind=None,
                active_task_id="012",
                worker_window_id="worker-window-012",
                binding_status="active",
            ),
            self.event("user_requested_revision", **self.revision_data()),
            self.capability(route_worker=True),
        )
        self.assertEqual(plan.next_action, "route_to_active_worker")
        self.assertEqual(plan.target_worker_id, "worker-window-012")

    def test_revision_07_completed_task_creates_lightweight_record(self) -> None:
        plan = memory_sync.reduce_orchestration(
            self.state(task_id="012", lifecycle="completed", expected_kind=None),
            self.event(
                "user_requested_revision", **self.revision_data(next_revision_number=1)
            ),
            self.capability(create_worker=True),
        )
        self.assertEqual(plan.next_action, "create_lightweight_revision")
        self.assertEqual(plan.revision_id, "012-r1")
        self.assertNotIn("change_set", plan.state_patch["revision"])
        self.assertTrue(plan.state_patch["revision"]["worker_creation_authorized"])
        self.assertEqual(
            plan.state_patch["revision"]["run_report"],
            "reports/runs/012-r1-attempt-1.md",
        )
        self.assertTrue(plan.work_payload["worker_creation_authorized"])
        self.assertEqual(
            plan.work_payload["run_report"],
            "reports/runs/012-r1-attempt-1.md",
        )
        stored = memory_sync.parse_revision_state(
            "tasks/revisions/012-r1.md",
            (HOOK_ASSETS.parent / "templates" / "TASK_REVISION.md").read_text(
                encoding="utf-8"
            ),
        )
        self.assertEqual(stored.revision_id, "012-r1")
        self.assertEqual(stored.parent_task_id, "012")
        self.assertLessEqual(len(stored.allowed_scope), 3)

    def test_revision_reuses_only_the_exact_parent_worker(self) -> None:
        exact = memory_sync.reduce_orchestration(
            self.state(
                task_id="012",
                lifecycle="completed",
                expected_kind=None,
                previous_task_id="012",
                worker_window_id="worker-window-012",
                worker_availability="idle",
                binding_status="released",
            ),
            self.event("user_requested_revision", **self.revision_data()),
            self.capability(route_worker=True, reuse_worker=True),
        )
        unbound_history = memory_sync.reduce_orchestration(
            self.state(
                task_id="012",
                lifecycle="completed",
                expected_kind=None,
                previous_task_id="",
                worker_window_id="worker-window-unknown",
                worker_availability="idle",
                binding_status="released",
            ),
            self.event("user_requested_revision", **self.revision_data()),
            self.capability(route_worker=True, reuse_worker=True),
        )

        self.assertEqual(exact.next_action, "route_to_previous_worker")
        self.assertEqual(exact.target_worker_id, "worker-window-012")
        self.assertEqual(unbound_history.next_action, "create_lightweight_revision")

    def test_revision_08_completion_enters_automatic_integration(self) -> None:
        plan = memory_sync.reduce_orchestration(
            self.state(task_id="012", lifecycle="completed", expected_kind=None),
            self.event(
                "revision_completed",
                revision_id="012-r1",
                report_id="reports/runs/012-r1-attempt-1.md",
            ),
            self.capability(),
        )
        self.assertEqual(plan.next_action, "evaluate_integration")
        self.assertEqual(plan.state_patch["session"]["phase"], "integration_pending")
        self.assertFalse(plan.user_message)

    def test_revision_09_theme_redesign_becomes_formal_followup(self) -> None:
        plan = memory_sync.reduce_orchestration(
            self.state(task_id="012", lifecycle="completed", expected_kind=None),
            self.event(
                "user_requested_revision",
                **self.revision_data(small_scope=False, new_product_decision=True),
            ),
            self.capability(),
        )
        self.assertEqual(plan.next_action, "request_formal_followup_task")

    def test_revision_10_missing_worker_falls_back_without_discussion_edit(self) -> None:
        plan = memory_sync.reduce_orchestration(
            self.state(task_id="012", lifecycle="completed", expected_kind=None),
            self.event(
                "user_requested_revision", **self.revision_data(revision_id="012-r1")
            ),
            self.capability(host="claude", create_worker=False),
        )
        self.assertEqual(plan.next_action, "fallback_manual_worker_command")
        self.assertEqual(
            plan.user_message, "在任务 012 的执行窗口执行修订 012-r1"
        )
        self.assertNotEqual(plan.next_action, "discussion_window_implements_business_code")

    def test_revision_11_ambiguous_parent_is_not_guessed(self) -> None:
        plan = memory_sync.reduce_orchestration(
            self.state(task_id="012", lifecycle="completed", expected_kind=None),
            self.event(
                "user_requested_revision",
                **self.revision_data(candidate_parent_task_ids=["012", "013"]),
            ),
            self.capability(),
        )
        self.assertEqual(plan.next_action, "ask_task_choice")

    def test_revision_12_unrelated_busy_worker_is_not_reused(self) -> None:
        plan = memory_sync.reduce_orchestration(
            self.state(
                task_id="012",
                lifecycle="running",
                expected_kind=None,
                active_task_id="020",
                worker_window_id="worker-window-020",
                binding_status="active",
            ),
            self.event("user_requested_revision", **self.revision_data()),
            self.capability(route_worker=True, reuse_worker=True),
        )
        self.assertNotIn(plan.next_action, {"route_to_active_worker", "route_to_previous_worker"})

    def test_revision_13_risk_flags_force_formal_task(self) -> None:
        for flag in (
            "public_api_change",
            "schema_change",
            "dependency_change",
            "migration_change",
        ):
            with self.subTest(flag=flag):
                plan = memory_sync.reduce_orchestration(
                    self.state(task_id="012", lifecycle="completed", expected_kind=None),
                    self.event(
                        "user_requested_revision", **self.revision_data(**{flag: True})
                    ),
                    self.capability(),
                )
                self.assertEqual(plan.next_action, "request_formal_followup_task")

    def test_revision_14_revision_ids_are_exact(self) -> None:
        for value in ("012-r1", "012-r10"):
            self.assertEqual(memory_sync.canonical_revision_id(value), value)
        self.assertEqual(memory_sync.canonical_revision_id("012-r1-extra"), "")
        self.assertNotEqual(
            memory_sync.canonical_revision_id("012-r1"),
            memory_sync.canonical_revision_id("012-r10"),
        )

    def test_revision_15_safe_integration_updates_revision_and_project_state(self) -> None:
        plan = memory_sync.reduce_orchestration(
            self.state(
                task_id="012",
                lifecycle="completed",
                phase="integrating",
                expected_kind=None,
                integration_lease_id="lease-1",
                integration_id="integration-012-r1",
            ),
            self.event(
                "integration_completed",
                integration_id="integration-012-r1",
                revision_id="012-r1",
                report_id="reports/runs/012-r1-attempt-1.md",
                project_status_updated=True,
            ),
            self.capability(),
        )
        self.assertEqual(plan.state_patch["revision"]["status"], "integrated")
        self.assertTrue(plan.state_patch["revision"]["project_status_updated"])
        self.assertNotIn("是否开始集成", plan.user_message)

    def test_revision_integration_preserves_reviewed_parent_lifecycle(self) -> None:
        evaluating = memory_sync.reduce_orchestration(
            self.state(
                task_id="012",
                lifecycle="reviewed",
                phase="integration_pending",
                expected_kind="auto_integrate",
            ),
            self.event(
                "integration_evaluated", outcome="safe", revision_id="012-r1"
            ),
            self.capability(),
        )
        self.assertTrue(evaluating.accepted)
        self.assertEqual(evaluating.revision_id, "012-r1")
        self.assertEqual(
            evaluating.state_patch["integration_runtime"]["revision_id"], "012-r1"
        )

        completed = memory_sync.reduce_orchestration(
            self.state(
                task_id="012",
                lifecycle="reviewed",
                phase="integrating",
                expected_kind=None,
                integration_lease_id="lease-1",
                integration_id="integration-012-r1",
            ),
            self.event(
                "integration_completed",
                integration_id="integration-012-r1",
                revision_id="012-r1",
            ),
            self.capability(),
        )
        self.assertTrue(completed.accepted)
        self.assertEqual(completed.state_patch["task"]["lifecycle"], "reviewed")
        self.assertEqual(completed.state_patch["revision"]["status"], "integrated")

    def test_revision_host_route_finds_reusable_worker_or_uses_exact_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            (root / ".wishgraph").mkdir()
            shutil.copy2(HOOK_ASSETS / "config.json", root / ".wishgraph/config.json")
            task_path = root / "tasks/build/012-parent.md"
            task_path.parent.mkdir(parents=True)
            task_path.write_text(
                "<!-- wishgraph:task-state:start -->\n```json\n"
                + json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "task",
                        "task_id": "012",
                        "parent_task_id": None,
                        "dependencies": [],
                        "status": "completed",
                        "work_type": "sequential",
                        "batch_id": None,
                        "attempt": 1,
                        "execution_mode": "exclusive",
                        "comparison_group": None,
                        "run_report": "reports/runs/012-attempt-1.md",
                        "worker_creation_authorized": True,
                        "integration_policy": "inherited_task_approval",
                    },
                    indent=2,
                )
                + "\n```\n<!-- wishgraph:task-state:end -->\n",
                encoding="utf-8",
            )
            revision_path = root / "tasks/revisions/012-r1.md"
            revision_path.parent.mkdir(parents=True)
            revision_path.write_text(
                (HOOK_ASSETS.parent / "templates" / "TASK_REVISION.md").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            claim = memory_sync.acquire_claim(
                root,
                "012",
                1,
                "worker-012",
                host_thread_ref="visible-worker-012",
                agent_platform="codex",
                require_clean=False,
            )
            memory_sync.update_claim(root, claim["claim"]["claim_id"], "release")

            codex = subprocess.run(
                [
                    sys.executable,
                    str(HOOK_ASSETS / "memory_sync.py"),
                    "revision",
                    "route",
                    "012-r1",
                    "--host",
                    "codex",
                ],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                check=True,
            )
            self.assertEqual(
                json.loads(codex.stdout)["host_action"]["target_worker_id"],
                "visible-worker-012",
            )

            busy = memory_sync.acquire_claim(
                root,
                "013",
                1,
                "worker-013",
                host_thread_ref="visible-worker-012",
                agent_platform="codex",
                require_clean=False,
            )
            self.assertTrue(busy["ok"], busy)
            rerouted = subprocess.run(
                [
                    sys.executable,
                    str(HOOK_ASSETS / "memory_sync.py"),
                    "revision",
                    "route",
                    "012-r1",
                    "--host",
                    "codex",
                ],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                check=True,
            )
            self.assertEqual(
                json.loads(rerouted.stdout)["host_action"]["action"],
                "launch_codex_revision_worker",
            )
            claude = subprocess.run(
                [
                    sys.executable,
                    str(HOOK_ASSETS / "memory_sync.py"),
                    "revision",
                    "route",
                    "012-r1",
                    "--host",
                    "claude",
                ],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                check=True,
            )
            self.assertEqual(
                json.loads(claude.stdout)["host_action"]["user_message"],
                "在任务 012 的执行窗口执行修订 012-r1",
            )

    def test_revision_route_failure_creates_visible_codex_worker_or_manual_fallback(self) -> None:
        event = self.event(
            "host_revision_route_failed",
            parent_task_id="012",
            revision_id="012-r1",
        )
        codex = memory_sync.reduce_orchestration(
            self.state(task_id="012", lifecycle="completed", expected_kind=None),
            event,
            self.capability(host="codex", create_worker=True),
        )
        self.assertEqual(codex.next_action, "create_lightweight_revision")
        claude = memory_sync.reduce_orchestration(
            self.state(task_id="012", lifecycle="completed", expected_kind=None),
            event,
            self.capability(host="claude", create_worker=False),
        )
        self.assertEqual(
            claude.user_message, "在任务 012 的执行窗口执行修订 012-r1"
        )


class UnbornRepositoryTests(unittest.TestCase):
    def test_session_start_accepts_repository_without_first_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            hooks = root / ".wishgraph" / "hooks"
            hooks.mkdir(parents=True)
            shutil.copy2(HOOK_ASSETS / "config.json", root / ".wishgraph" / "config.json")
            for runtime_name in (
                "memory_sync.py",
                "git_state.py",
                "workflow_state.py",
                "policy.py",
                "host_adapter.py",
                "codex_worker_provider.py",
            ):
                shutil.copy2(HOOK_ASSETS / runtime_name, hooks / runtime_name)

            process = subprocess.run(
                [sys.executable, str(hooks / "memory_sync.py"), "session-start"],
                cwd=root,
                input=json.dumps({"cwd": str(root)}),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )

            payload = json.loads(process.stdout)
            self.assertIn("hookSpecificOutput", payload)
            self.assertIn(
                "project memory is not initialized",
                payload["hookSpecificOutput"]["additionalContext"],
            )


class MemorySyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "WishGraph Tests")

        (self.root / ".wishgraph" / "hooks").mkdir(parents=True)
        shutil.copy2(HOOK_ASSETS / "config.json", self.root / ".wishgraph" / "config.json")
        for runtime_name in (
            "memory_sync.py",
            "git_state.py",
            "workflow_state.py",
            "policy.py",
            "host_adapter.py",
            "codex_worker_provider.py",
        ):
            shutil.copy2(
                HOOK_ASSETS / runtime_name,
                self.root / ".wishgraph" / "hooks" / runtime_name,
            )
        self.write("PRD.md", "# PRD\n")
        self.write("ARCHITECTURE.md", "# Architecture\n")
        self.write("CODEMAP.md", "# Codemap\n")
        self.write("CONVENTIONS.md", "# Conventions\n")
        self.write("prompts/DISCUSSION_AI.md", self.discussion("bootstrap"))
        self.write("prompts/EXECUTION_AI.md", "# Execution\n")
        self.write("prompts/INTEGRATION_AI.md", "# Integration\n")
        self.write("reports/runs/000-bootstrap.md", self.run_report("000-bootstrap"))
        self.write(
            "reports/PROJECT_STATUS.md",
            self.overview(["reports/runs/000-bootstrap.md"]),
        )
        self.write("src/app.py", "print('baseline')\n")
        self.git("add", ".")
        self.git("commit", "-qm", "baseline")
        self.config = memory_sync.load_config(self.root)
        assert self.config is not None

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.root), *args],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def write(self, relative: str, content: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def update_config(self, **values: object) -> None:
        path = self.root / ".wishgraph" / "config.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        config.update(values)
        path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    def impact_table(
        self,
        defaults: tuple[str, str],
        overrides: Optional[dict[str, tuple[str, str]]] = None,
    ) -> str:
        rows = {
            "PRD.md": defaults,
            "ARCHITECTURE.md": defaults,
            "CODEMAP.md": defaults,
            "CONVENTIONS.md": defaults,
            "prompts/DISCUSSION_AI.md": defaults,
            "prompts/EXECUTION_AI.md": defaults,
            "prompts/INTEGRATION_AI.md": defaults,
        }
        rows.update(overrides or {})
        return "\n".join(
            f"| `{path}` | {status} | {reason} |"
            for path, (status, reason) in rows.items()
        )

    def run_report(
        self,
        unit: str,
        overrides: Optional[dict[str, tuple[str, str]]] = None,
        *,
        work_type: str = "sequential",
        batch_id: str = "N/A",
        status: str = "Completed",
        readiness: str = "Ready",
        validation: str = "Pass",
        scope_check: str = "Pass",
        conflict_status: str = "None",
        new_decision: str = "No",
    ) -> str:
        table = self.impact_table(
            ("N/A", "Shared project truth did not change"), overrides
        )
        return (
            "# Run Report\n\n"
            "## Work Unit\n\n"
            f"- Unit: {unit}\n"
            f"- Status: {status}\n"
            f"- Work type: {work_type}\n"
            f"- Batch ID: {batch_id}\n"
            "- Integration authorization: "
            + (
                "Requires explicit user confirmation\n"
                if work_type in {"parallel_batch", "high_risk"}
                else "Inherited task approval\n"
            )
            + f"- Integration readiness: {readiness}\n"
            + f"- Scope check: {scope_check}\n"
            + f"- Conflict status: {conflict_status}\n"
            + f"- New product / architecture / data decision: {new_decision}\n\n"
            "## Validation\n\n"
            "| Check | Command / Scenario | Result | Evidence |\n"
            "|---|---|---|---|\n"
            f"| Tests | test | {validation} | evidence |\n\n"
            "## Shared Memory Impact Proposal\n\n"
            "| File | Result | Reason |\n"
            "|---|---|---|\n"
            f"{table}\n"
        )

    def structured_run_report(
        self,
        unit: str,
        *,
        work_type: str = "sequential",
        batch_id: Optional[str] = None,
        status: str = "completed",
        readiness: str = "ready",
        validation: str = "pass",
        execution_mode: str = "exclusive",
        changed_paths: Optional[list[str]] = None,
        public_api_change: bool = False,
        schema_change: bool = False,
        persistence_change: bool = False,
        security_impact: bool = False,
        privacy_impact: bool = False,
        permission_change: bool = False,
        billing_impact: bool = False,
        deletion_change: bool = False,
        migration_change: bool = False,
        dependency_change: bool = False,
        cross_module_contract_change: bool = False,
        task_id: Optional[str] = None,
        revision_id: Optional[str] = None,
        change_class: str = "formal",
        candidate_score: Optional[float] = None,
        selection_requires_judgment: bool = False,
    ) -> str:
        legacy = self.run_report(
            unit,
            work_type=work_type,
            batch_id=batch_id or "N/A",
            status="Blocked",
            readiness="Blocked",
            validation="Fail",
        )
        state = {
            "schema_version": 1,
            "kind": "run",
            "task_id": task_id,
            "revision_id": revision_id,
            "unit": unit,
            "status": status,
            "work_type": work_type,
            "execution_mode": execution_mode,
            "batch_id": batch_id,
            "changed_paths": changed_paths or [],
            "public_api_change": public_api_change,
            "schema_change": schema_change,
            "persistence_change": persistence_change,
            "security_impact": security_impact,
            "privacy_impact": privacy_impact,
            "permission_change": permission_change,
            "billing_impact": billing_impact,
            "deletion_change": deletion_change,
            "migration_change": migration_change,
            "dependency_change": dependency_change,
            "cross_module_contract_change": cross_module_contract_change,
            "change_class": change_class,
            "candidate_score": candidate_score,
            "selection_requires_judgment": selection_requires_judgment,
            "integration_authorization": (
                "explicit_user_confirmation"
                if work_type in {"parallel_batch", "high_risk"}
                else "inherited_task_approval"
            ),
            "integration_readiness": readiness,
            "scope_check": "pass",
            "conflict_status": "none",
            "new_decision": False,
            "validation": {"tests": validation},
        }
        block = (
            "<!-- wishgraph:run-state:start -->\n```json\n"
            + json.dumps(state, ensure_ascii=False, indent=2)
            + "\n```\n<!-- wishgraph:run-state:end -->\n\n"
        )
        return legacy.replace("## Work Unit\n\n", "## Work Unit\n\n" + block, 1)

    def structured_task(
        self,
        task_id: str,
        *,
        status: str = "draft",
        work_type: str = "sequential",
        batch_id: Optional[str] = None,
        worker_authorized: bool = False,
        integration_policy: str = "inherited_task_approval",
        parent_task_id: Optional[str] = None,
        dependencies: Optional[list[str]] = None,
        attempt: int = 1,
        run_report: Optional[str] = None,
        execution_mode: str = "exclusive",
        comparison_group: Optional[str] = None,
    ) -> str:
        match = re.match(r"\d{3,}[a-z]*", task_id)
        structured_id = match.group(0) if match else task_id
        state = {
            "schema_version": 1,
            "kind": "task",
            "task_id": structured_id,
            "parent_task_id": parent_task_id,
            "dependencies": dependencies or [],
            "status": status,
            "work_type": work_type,
            "batch_id": batch_id,
            "attempt": attempt,
            "execution_mode": execution_mode,
            "comparison_group": comparison_group,
            "run_report": run_report or f"reports/runs/{task_id}.md",
            "worker_creation_authorized": worker_authorized,
            "integration_policy": integration_policy,
        }
        return (
            f"# {task_id}\n\n"
            "Spec source: approved requirement\n\n"
            "<!-- wishgraph:task-state:start -->\n```json\n"
            + json.dumps(state, ensure_ascii=False, indent=2)
            + "\n```\n<!-- wishgraph:task-state:end -->\n\n"
            "## Intent\n\nImplement the bounded task.\n"
        )

    def execution_ready_task(self, task_id: str, **kwargs: object) -> str:
        return self.structured_task(task_id, **kwargs) + (
            "\n## Change Set\n\n- Change only the assigned implementation.\n"
            "\n## Do Not Do\n\n- Do not expand scope.\n"
            "\n## Validation\n\n- Run the focused tests.\n"
            "\n## Rollback / Recovery\n\n- Revert the atomic commit.\n"
        )

    def prepare_claude_worker_task(
        self, task_id: str, discussion_session_id: str, host: str = "claude"
    ) -> None:
        task_path = f"tasks/build/{task_id}-{host}-worker.md"
        self.write(
            task_path,
            self.execution_ready_task(
                task_id,
                status="approved",
                worker_authorized=True,
                run_report=f"reports/runs/{task_id}-attempt-1.md",
            ),
        )
        self.git("add", task_path)
        self.git("commit", "-qm", f"prepare {task_id}")
        persisted = memory_sync.write_session_runtime(
            self.root,
            discussion_session_id,
            {
                "session": {
                    "session_id": discussion_session_id,
                    "role": "discussion",
                    "host": host,
                    "phase": "routing_worker",
                    "expected_transition": {
                        "kind": "wait_for_worker",
                        "task_id": task_id,
                    },
                },
                "task": {
                    "task_id": task_id,
                    "lifecycle": "approved",
                    "worker_authorized": True,
                    "run_report": f"reports/runs/{task_id}-attempt-1.md",
                },
            },
        )
        self.assertTrue(persisted["ok"], persisted)

    def overview(
        self,
        reports: list[str],
        overrides: Optional[dict[str, tuple[str, str]]] = None,
        *,
        integration_kind: Optional[str] = None,
        authorization: Optional[str] = None,
    ) -> str:
        rows = {
            "prompts/DISCUSSION_AI.md": (
                "Updated",
                "Integrated results were added to the discussion handoff",
            )
        }
        rows.update(overrides or {})
        table = self.impact_table(("N/A", "Integrated project truth did not change"), rows)
        report_list = "\n".join(f"- `{path}`" for path in reports)
        kind = integration_kind or ("parallel_batch" if len(reports) > 1 else "sequential")
        auth = authorization or (
            "Explicit user confirmation"
            if kind in {"parallel_batch", "high_risk"}
            else "Inherited task approval"
        )
        return (
            "# Project Status\n\n"
            "## Current Integration\n\n"
            "- Integration ID: integration/test\n"
            "- Date: 2026-07-13\n"
            "- Status: Completed\n"
            "- Commit: pending\n"
            f"- Integration kind: {kind}\n"
            f"- Authorization: {auth}\n\n"
            "## Run Reports Absorbed This Integration\n\n"
            f"{report_list}\n\n"
            "## Current Project Status\n\n"
            "- Completed: latest worker results integrated\n"
            "- User-visible result: current behavior verified\n"
            "- Current important facts: integrated snapshot is current\n\n"
            "## Validation\n\n"
            "- Build: Pass\n- Tests: Pass\n- Manual: Pass\n\n"
            "## Unresolved Items\n\n"
            "- Risks: None\n- Conflicts: None\n- Pending user decisions: None\n\n"
            "## Worker Status\n\n"
            "- Completed: current workers\n- Waiting: None\n- Blocked: None\n\n"
            "## Next Step\n\n"
            "- Recommended task: review the status\n- Reason: confirm result\n\n"
            "## Discussion Handoff\n\n"
            "- Current focus: review\n- Results to present: integrated result\n"
            "- Detailed evidence: reports/PROJECT_STATUS.md\n\n"
            "## Shared Memory Impact\n\n"
            "| File | Result | Reason |\n"
            "|---|---|---|\n"
            f"{table}\n"
        )

    def discussion(self, unit: str) -> str:
        return (
            "# Discussion\n\n"
            "<!-- wishgraph:state:start -->\n\n"
            "## Current Discussion Handoff\n\n"
            f"- Latest integration ID: {unit}\n"
            "- Current discussion focus: review\n"
            "- Results to present: integrated result\n"
            "- Pending user decisions: none\n"
            "- Next recommended action: next\n"
            "- Details: `reports/PROJECT_STATUS.md`\n\n"
            "<!-- wishgraph:state:end -->\n"
        )

    def prepare_integration(self, unit: str) -> tuple[str, str]:
        report_path = f"reports/runs/{unit}.md"
        self.write("src/integration.py", f"print('{unit}')\n")
        self.write(report_path, self.run_report(unit))
        self.write("prompts/DISCUSSION_AI.md", self.discussion(f"integration/{unit}"))
        status = self.overview([report_path])
        self.write("reports/PROJECT_STATUS.md", status)
        return report_path, status

    def test_clean_repo_passes(self) -> None:
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertTrue(result.ok, result.errors)

    def test_chinese_report_status_is_machine_readable(self) -> None:
        self.assertEqual(memory_sync.parse_report_status("- 状态：Completed\n"), "completed")

    def test_structured_run_state_is_canonical_over_legacy_labels(self) -> None:
        content = self.structured_run_report("structured-001")
        state = memory_sync.report_state("reports/runs/structured-001.md", content)
        self.assertEqual(state.state_source, "structured")
        self.assertEqual(state.status, "completed")
        self.assertEqual(state.readiness, "ready")
        self.assertEqual(state.safety_errors, [])

    def test_task_id_suffixes_are_unbounded_excel_style_sequences(self) -> None:
        self.assertEqual(memory_sync.task_id_parts("012"), ("012", ""))
        self.assertEqual(memory_sync.task_id_parts("012a"), ("012", "a"))
        self.assertEqual(memory_sync.suffix_index("z"), 26)
        self.assertEqual(memory_sync.suffix_index("aa"), 27)
        self.assertEqual(memory_sync.suffix_for_index(27), "aa")
        self.assertEqual(memory_sync.followup_task_id("012", 52), "012az")
        self.assertEqual(memory_sync.canonical_task_id("012AA"), "012aa")
        self.assertEqual(memory_sync.canonical_task_id("12a"), "")

    def test_natural_language_task_commands_preserve_authorization_boundary(self) -> None:
        execute = memory_sync.parse_task_command("执行012号任务")
        compact_execute = memory_sync.parse_task_command("执行012b")
        inspect = memory_sync.parse_task_command("查看012号任务")
        family = memory_sync.parse_task_command("查看012系列任务")
        assert (
            execute is not None
            and compact_execute is not None
            and inspect is not None
            and family is not None
        )
        self.assertEqual(execute["action"], "execute")
        self.assertTrue(execute["authorizes_execution"])
        self.assertEqual(compact_execute["action"], "execute")
        self.assertEqual(compact_execute["task_id"], "012b")
        self.assertTrue(compact_execute["authorizes_execution"])
        self.assertEqual(inspect["action"], "inspect")
        self.assertFalse(inspect["authorizes_execution"])
        self.assertEqual(family["action"], "family")
        self.assertIsNone(memory_sync.parse_task_command("随便看看012"))

    def test_compact_execution_command_resolves_exact_suffixed_task(self) -> None:
        self.write(
            "tasks/build/012b-follow-up.md",
            self.structured_task("012b-follow-up", parent_task_id="012"),
        )
        self.write(
            "tasks/build/012ba-later.md",
            self.structured_task("012ba-later", parent_task_id="012b"),
        )
        process = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "task",
                "route",
                "执行012b",
            ],
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        payload = json.loads(process.stdout)
        self.assertEqual(payload["task"]["task_id"], "012b")
        self.assertEqual(
            payload["task"]["task_path"], "tasks/build/012b-follow-up.md"
        )
        self.assertTrue(payload["command"]["authorizes_execution"])

    def test_task_resolver_matches_exact_structured_id(self) -> None:
        self.write("tasks/build/012-main.md", self.structured_task("012-main"))
        self.write(
            "tasks/build/012a-follow-up.md",
            self.structured_task("012a-follow-up", parent_task_id="012"),
        )
        process = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "task",
                "route",
                "执行012号任务",
            ],
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        payload = json.loads(process.stdout)
        self.assertEqual(payload["task"]["task_id"], "012")
        self.assertEqual(payload["task"]["task_path"], "tasks/build/012-main.md")
        self.assertTrue(payload["command"]["authorizes_execution"])

    def test_task_resolver_reports_duplicate_structured_id(self) -> None:
        self.write("tasks/build/012-one.md", self.structured_task("012-one"))
        self.write("tasks/build/012-two.md", self.structured_task("012-two"))
        process = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "task",
                "resolve",
                "012",
            ],
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(process.returncode, 1)
        payload = json.loads(process.stdout)
        self.assertEqual(payload["error"], "duplicate_task_id")
        self.assertEqual(len(payload["matches"]), 2)

    def test_task_parent_dependencies_and_attempt_are_parsed(self) -> None:
        state = memory_sync.parse_task_state(
            "tasks/build/012a-follow-up.md",
            self.structured_task(
                "012a-follow-up",
                parent_task_id="012",
                dependencies=["012"],
                attempt=2,
                run_report="reports/runs/012a-attempt-2.md",
            ),
        )
        self.assertEqual(state.task_id, "012a")
        self.assertEqual(state.parent_task_id, "012")
        self.assertEqual(state.dependencies, ["012"])
        self.assertEqual(state.attempt, 2)

    def test_exclusive_worker_claim_acquisition_is_atomic(self) -> None:
        def acquire(worker: str) -> dict[str, object]:
            return memory_sync.acquire_claim(
                self.root, "028", 1, worker, require_clean=True
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(acquire, ("worker-a", "worker-b")))
        self.assertEqual(sum(bool(result["ok"]) for result in results), 1)
        loser = next(result for result in results if not result["ok"])
        self.assertIn(
            loser["error"], {"active_claim_exists", "claim_operation_in_progress"}
        )
        winner = next(result for result in results if result["ok"])
        released = memory_sync.update_claim(
            self.root, winner["claim"]["claim_id"], "release"
        )
        self.assertTrue(released["ok"], released)
        retried = memory_sync.acquire_claim(
            self.root, "028", 2, "worker-retry", require_clean=True
        )
        self.assertTrue(retried["ok"], retried)

    def test_claim_cleanliness_ignores_generated_runtime_cache_only(self) -> None:
        self.write(".wishgraph/hooks/__pycache__/runtime.pyc", "cache")
        self.assertTrue(memory_sync.worktree_is_clean(self.root))
        self.write("src/unrelated.py", "print('dirty')\n")
        self.assertFalse(memory_sync.worktree_is_clean(self.root))

    def test_claim_stale_detection_uses_heartbeat_timestamp(self) -> None:
        acquired = memory_sync.acquire_claim(
            self.root, "028a", 1, "worker-stale", require_clean=True
        )
        self.assertTrue(acquired["ok"], acquired)
        claim_id = acquired["claim"]["claim_id"]
        path = memory_sync.claim_root(self.root) / "028a" / f"{claim_id}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["updated_at"] = "2000-01-01T00:00:00Z"
        path.write_text(json.dumps(record), encoding="utf-8")
        claim = memory_sync.inspect_claims(
            self.root, "028a", stale_after_seconds=1
        )[0]
        self.assertTrue(claim["stale"])
        self.assertEqual(claim["effective_lease_status"], "stale")
        blocked = memory_sync.acquire_claim(
            self.root,
            "028a",
            2,
            "worker-replacement",
            stale_after_seconds=1,
            require_clean=True,
        )
        self.assertEqual(blocked["error"], "stale_claim_requires_explicit_revoke")
        revoked = memory_sync.update_claim(self.root, claim_id, "revoke")
        self.assertTrue(revoked["ok"], revoked)
        replacement = memory_sync.acquire_claim(
            self.root,
            "028a",
            2,
            "worker-replacement",
            stale_after_seconds=1,
            require_clean=True,
        )
        self.assertTrue(replacement["ok"], replacement)

    def test_status_uses_active_claim_as_running_evidence(self) -> None:
        task_path = "tasks/build/028b-running.md"
        self.write(
            task_path,
            self.structured_task(
                "028b-running", status="approved", worker_authorized=True
            ),
        )
        self.git("add", task_path)
        self.git("commit", "-qm", "running claim fixture")
        acquired = memory_sync.acquire_claim(
            self.root, "028b", 1, "worker-running", require_clean=True
        )
        self.assertTrue(acquired["ok"], acquired)
        state = memory_sync.integration_state(self.root, self.config).as_dict()
        unit = next(item for item in state["work_units"] if item["task_id"] == "028b")
        self.assertEqual(unit["lifecycle_status"], "running")
        self.assertEqual(unit["active_claims"][0]["worker_id"], "worker-running")

    def test_claim_is_shared_across_worktrees_and_enforces_binding(self) -> None:
        other = self.root.parent / f"{self.root.name}-worker-two"
        self.git("worktree", "add", "-q", "-b", "worker-two", str(other))
        try:
            acquired = memory_sync.acquire_claim(
                self.root, "029", 1, "worker-main", require_clean=True
            )
            self.assertTrue(acquired["ok"], acquired)
            claim_id = acquired["claim"]["claim_id"]
            visible = memory_sync.inspect_claims(other, "029")
            self.assertEqual([claim["claim_id"] for claim in visible], [claim_id])
            mismatch = memory_sync.update_claim(
                other,
                claim_id,
                "heartbeat",
                branch="worker-two",
                worktree=str(other),
            )
            self.assertFalse(mismatch["ok"])
            self.assertIn(mismatch["error"], {"claim_branch_mismatch", "claim_worktree_mismatch"})
            released = memory_sync.update_claim(
                self.root,
                claim_id,
                "release",
                branch=acquired["claim"]["branch"],
                worktree=str(self.root),
            )
            self.assertTrue(released["ok"], released)
        finally:
            self.git("worktree", "remove", "--force", str(other))
            self.git("branch", "-D", "worker-two")

    def test_worker_notification_is_idempotent_and_bound_discussion_consumes_it(self) -> None:
        values = {
            "task_id": "029a",
            "work_unit_id": "029a",
            "attempt": 1,
            "terminal_event": "completed",
            "task_lifecycle": "completed",
            "run_report": "reports/runs/029a-attempt-1.md",
            "claim_id": "claim-029a",
            "worker_session_id": "worker-029a",
            "discussion_session_id": "discussion-codex-029a",
            "agent_platform": "codex",
            "next_action": "auto_integrate",
            "reason": "safe_terminal_result_ready",
        }
        first = memory_sync.enqueue_worker_notification(self.root, **values)
        duplicate = memory_sync.enqueue_worker_notification(self.root, **values)
        self.assertTrue(first["created"])
        self.assertFalse(duplicate["created"])
        self.assertEqual(
            first["notification"]["notification_id"],
            duplicate["notification"]["notification_id"],
        )
        wrong_discussion = memory_sync.consume_worker_notifications(
            self.root, "discussion-claude-029a"
        )
        self.assertEqual(wrong_discussion["notifications"], [])
        consumed = memory_sync.consume_worker_notifications(
            self.root, "discussion-codex-029a"
        )
        self.assertEqual(len(consumed["notifications"]), 1)
        self.assertEqual(consumed["notifications"][0]["status"], "read")
        inbox = memory_sync.inspect_worker_notifications(self.root)
        self.assertEqual(len(inbox), 1)
        self.assertEqual(inbox[0]["read_by_session_id"], "discussion-codex-029a")
        self.assertEqual(
            list(memory_sync.worker_notification_root(self.root).glob("*.json")),
            [memory_sync.worker_notification_root(self.root) / "inbox.json"],
        )

    def test_explicit_discussion_entry_can_adopt_cross_host_pending_notification(self) -> None:
        created = memory_sync.enqueue_worker_notification(
            self.root,
            task_id="029b",
            work_unit_id="029b",
            attempt=1,
            terminal_event="failed",
            task_lifecycle="blocked",
            run_report="reports/runs/029b-attempt-1.md",
            claim_id="claim-029b",
            worker_session_id="worker-claude-029b",
            discussion_session_id="discussion-codex-029b",
            agent_platform="claude",
            next_action="resolve_worker_failure",
            reason="worker_blocked",
        )
        self.assertTrue(created["ok"])
        process = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "user-prompt-submit",
                "--host",
                "claude",
            ],
            cwd=self.root,
            input=json.dumps(
                {
                    "cwd": str(self.root),
                    "session_id": "discussion-claude-029b",
                    "prompt": "开始讨论",
                }
            ),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        context = json.loads(process.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Worker notifications", context)
        self.assertIn("029b", context)
        self.assertIn("failed", context)
        notification = memory_sync.inspect_worker_notifications(self.root)[0]
        self.assertEqual(notification["status"], "read")
        self.assertEqual(
            notification["read_by_session_id"], "discussion-claude-029b"
        )

    def test_existing_discussion_session_consumes_notification_on_session_start(self) -> None:
        discussion_id = "discussion-session-start-029b"
        memory_sync.write_session_runtime(
            self.root,
            discussion_id,
            {
                "session": {
                    "session_id": discussion_id,
                    "role": "discussion",
                    "host": "codex",
                    "phase": "waiting_for_worker",
                    "expected_transition": {
                        "kind": "wait_for_worker",
                        "task_id": "029b",
                    },
                }
            },
        )
        memory_sync.enqueue_worker_notification(
            self.root,
            task_id="029b",
            work_unit_id="029b",
            attempt=1,
            terminal_event="completed",
            task_lifecycle="completed",
            run_report="reports/runs/029b-attempt-1.md",
            claim_id="claim-session-start-029b",
            discussion_session_id=discussion_id,
            next_action="auto_integrate",
        )
        process = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "session-start",
                "--host",
                "codex",
            ],
            cwd=self.root,
            input=json.dumps({"cwd": str(self.root), "session_id": discussion_id}),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        context = json.loads(process.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Worker notifications", context)
        self.assertIn("auto_integrate", context)
        self.assertEqual(
            memory_sync.inspect_worker_notifications(self.root, "pending"), []
        )

    def test_terminal_claim_classifies_completed_failed_and_decision_events(self) -> None:
        cases = (
            ("029c", "completed", "sequential", "completed", {}),
            ("029d", "blocked", "sequential", "failed", {}),
            ("029e", "completed", "high_risk", "decision_required", {}),
            (
                "029h",
                "completed",
                "sequential",
                "decision_required",
                {"public_api_change": True},
            ),
        )
        for task_id, lifecycle, work_type, expected_event, report_options in cases:
            with self.subTest(task_id=task_id):
                report_path = f"reports/runs/{task_id}-attempt-1.md"
                self.write(
                    f"tasks/build/{task_id}-notification.md",
                    self.structured_task(
                        task_id,
                        status=lifecycle,
                        work_type=work_type,
                        worker_authorized=True,
                        integration_policy=(
                            "requires_explicit_user_confirmation"
                            if work_type == "high_risk"
                            else "inherited_task_approval"
                        ),
                        run_report=report_path,
                    ),
                )
                self.write(
                    report_path,
                    self.structured_run_report(
                        f"{task_id}-attempt-1",
                        task_id=task_id,
                        status=("blocked" if lifecycle == "blocked" else "completed"),
                        readiness=("blocked" if lifecycle == "blocked" else "ready"),
                        validation=("fail" if lifecycle == "blocked" else "pass"),
                        work_type=work_type,
                        **report_options,
                    ),
                )
                claim = {
                    "claim_id": f"claim-{task_id}",
                    "task_id": task_id,
                    "revision_id": None,
                    "attempt": 1,
                    "lease_status": "released",
                    "worker_id": f"worker-{task_id}",
                    "host_thread_ref": f"worker-{task_id}",
                    "discussion_session_id": "discussion-terminal",
                    "agent_platform": "codex",
                }
                notification = memory_sync.enqueue_terminal_notification_from_claim(
                    self.root, self.config, claim
                )
                self.assertTrue(notification["ok"], notification)
                self.assertEqual(
                    notification["notification"]["terminal_event"], expected_event
                )

    def test_notification_runtime_does_not_start_processes_or_scan_source_tree(self) -> None:
        git_tree = ast.parse(
            (HOOK_ASSETS / "git_state.py").read_text(encoding="utf-8")
        )
        functions = {
            node.name: node
            for node in git_tree.body
            if isinstance(node, ast.FunctionDef)
            and "worker_notification" in node.name
        }
        source = "\n".join(ast.unparse(node) for node in functions.values())
        self.assertNotIn("subprocess", source)
        self.assertNotIn("socket", source)
        self.assertNotIn("sleep", source)
        self.assertNotIn("rglob", source)
        self.assertNotIn("glob(", source)

    def test_claim_release_writes_one_pending_notification_for_discussion(self) -> None:
        task_id = "029f"
        task_path = f"tasks/build/{task_id}-notification.md"
        report_path = f"reports/runs/{task_id}-attempt-1.md"
        self.write(
            task_path,
            self.execution_ready_task(
                task_id,
                status="approved",
                worker_authorized=True,
                run_report=report_path,
            ),
        )
        self.git("add", task_path)
        self.git("commit", "-qm", "notification task")
        acquired = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "claim",
                "acquire",
                task_id,
                "--worker-id",
                "worker-029f",
                "--session-id",
                "worker-029f",
                "--discussion-session-id",
                "discussion-029f",
                "--host",
                "codex",
            ],
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        claim_id = json.loads(acquired.stdout)["claim"]["claim_id"]
        self.write(
            task_path,
            self.execution_ready_task(
                task_id,
                status="completed",
                worker_authorized=True,
                run_report=report_path,
            ),
        )
        self.write(
            report_path,
            self.structured_run_report(
                f"{task_id}-attempt-1", task_id=task_id
            ),
        )
        self.git("add", task_path, report_path)
        self.git("commit", "-qm", "complete notification task")
        released = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "claim",
                "release",
                claim_id,
                "--session-id",
                "worker-029f",
            ],
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        payload = json.loads(released.stdout)
        self.assertTrue(payload["notification"]["created"])
        pending = memory_sync.inspect_worker_notifications(self.root, "pending")
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["discussion_session_id"], "discussion-029f")
        self.assertEqual(pending[0]["next_action"], "auto_integrate")

    def test_claim_release_keeps_claim_active_when_terminal_signal_is_not_ready(self) -> None:
        acquired = memory_sync.acquire_claim(
            self.root,
            "029g",
            1,
            "worker-029g",
            discussion_session_id="discussion-029g",
            require_clean=True,
        )
        self.assertTrue(acquired["ok"], acquired)
        claim_id = acquired["claim"]["claim_id"]
        released = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "claim",
                "release",
                claim_id,
            ],
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(released.returncode, 1)
        payload = json.loads(released.stdout)
        self.assertEqual(payload["error"], "terminal_notification_preflight_failed")
        claim = memory_sync.inspect_claims(self.root, "029g")[0]
        self.assertEqual(claim["lease_status"], "active")
        self.assertEqual(memory_sync.inspect_worker_notifications(self.root), [])

    def test_stop_hook_blocks_worker_until_active_claim_is_closed_out(self) -> None:
        acquired = memory_sync.acquire_claim(
            self.root,
            "029i",
            1,
            "worker-029i",
            host_thread_ref="worker-session-029i",
            discussion_session_id="discussion-029i",
            require_clean=True,
        )
        self.assertTrue(acquired["ok"], acquired)
        process = subprocess.run(
            [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "stop"],
            cwd=self.root,
            input=json.dumps(
                {"cwd": str(self.root), "session_id": "worker-session-029i"}
            ),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        payload = json.loads(process.stdout)
        self.assertEqual(payload["decision"], "block")
        self.assertIn("cannot stop with an active Claim", payload["reason"])
        self.assertEqual(memory_sync.inspect_worker_notifications(self.root), [])

    def test_claim_cli_runs_execution_preflight_and_blocks_duplicate_worker(self) -> None:
        task_path = "tasks/build/030-claim.md"
        self.write(task_path, self.execution_ready_task("030-claim"))
        self.git("add", task_path)
        self.git("commit", "-qm", "claim task fixture")
        command = [
            sys.executable,
            str(HOOK_ASSETS / "memory_sync.py"),
            "claim",
            "acquire",
            "030",
            "--worker-id",
            "worker-one",
            "--session-id",
            "worker-session-030",
            "--host",
            "codex",
        ]
        first = subprocess.run(
            command,
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        first_payload = json.loads(first.stdout)
        self.assertEqual(first_payload["claim"]["task_id"], "030")
        self.assertEqual(first_payload["claim"]["worktree"], str(self.root.resolve()))
        runtime = memory_sync.read_session_runtime(self.root, "worker-session-030")
        assert runtime is not None
        self.assertEqual(runtime["session"]["role"], "worker")
        self.assertEqual(
            runtime["worker_runtime"]["claim_id"], first_payload["claim"]["claim_id"]
        )

        second_command = list(command)
        second_command[second_command.index("worker-one")] = "worker-two"
        second = subprocess.run(
            second_command,
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(second.returncode, 1)
        self.assertEqual(json.loads(second.stdout)["error"], "active_claim_exists")

    def test_claude_worker_capability_levels_use_only_native_host_facts(self) -> None:
        host_adapter_module = sys.modules["host_adapter"]
        agent_path = self.root / ".claude" / "agents" / "wishgraph-worker.md"
        agent_path.parent.mkdir(parents=True)
        agent_path.write_text(
            "---\nname: wishgraph-worker\n---\n"
            + memory_sync.CLAUDE_WORKER_AGENT_MARKER
            + "\n",
            encoding="utf-8",
        )
        (self.root / ".claude" / "settings.json").write_text(
            json.dumps(
                {
                    "worktree": {
                        "baseRef": "head",
                        "symlinkDirectories": [".wishgraph"],
                    }
                }
            ),
            encoding="utf-8",
        )
        main_help = subprocess.CompletedProcess(
            ["claude", "--help"],
            0,
            stdout="--bg --fork-session\nCommands:\n  agents [options]\n",
            stderr="",
        )
        agents_help = subprocess.CompletedProcess(
            ["claude", "agents", "--help"],
            0,
            stdout="--json --all --cwd",
            stderr="",
        )
        isolated_env = {"CLAUDE_CONFIG_DIR": str(self.root / "claude-config")}
        with (
            mock.patch.dict(os.environ, isolated_env),
            mock.patch.object(host_adapter_module.shutil, "which", return_value="/bin/claude"),
            mock.patch.object(
                host_adapter_module,
                "_run_process",
                side_effect=[main_help, agents_help],
            ),
        ):
            background = memory_sync.detect_claude_worker_capability(self.root)
        self.assertEqual(background.tier, "background_session")

        agent_path.unlink()
        with (
            mock.patch.dict(os.environ, isolated_env),
            mock.patch.object(host_adapter_module.shutil, "which", return_value="/bin/claude"),
            mock.patch.object(
                host_adapter_module,
                "_run_process",
                side_effect=[main_help, agents_help],
            ),
        ):
            forked = memory_sync.detect_claude_worker_capability(self.root)
        self.assertEqual(forked.tier, "forked_subagent")

        manual_help = subprocess.CompletedProcess(
            ["claude", "--help"], 0, stdout="Claude Code", stderr=""
        )
        with (
            mock.patch.dict(os.environ, isolated_env),
            mock.patch.object(host_adapter_module.shutil, "which", return_value="/bin/claude"),
            mock.patch.object(
                host_adapter_module, "_run_process", return_value=manual_help
            ),
        ):
            manual = memory_sync.detect_claude_worker_capability(self.root)
        self.assertEqual(manual.tier, "manual_command_only")

    def test_codex_native_worker_requires_real_registered_thread_before_waiting(self) -> None:
        task_id = "041"
        discussion_id = "discussion-041"
        thread_id = "codex-thread-041"
        self.prepare_claude_worker_task(task_id, discussion_id, host="codex")
        prepared = memory_sync.prepare_codex_worker(
            self.root, self.config, task_id, discussion_id
        )
        self.assertTrue(prepared["ok"], prepared)
        self.assertEqual(prepared["agent_name"], "wishgraph-worker")
        self.assertIn(f"执行 {task_id} 任务", prepared["prompt"])
        runtime = memory_sync.read_session_runtime(self.root, discussion_id)
        assert runtime is not None
        self.assertEqual(runtime["session"]["phase"], "routing_worker")
        self.assertNotIn("worker_handle", runtime["worker_runtime"])

        invalid = memory_sync.register_codex_worker(
            self.root,
            self.config,
            task_id,
            discussion_id,
            "",
            inspectable=True,
            controllable=True,
            independent_context=True,
        )
        self.assertTrue(invalid["fallback"])
        self.assertEqual(invalid["user_message"], f"执行 {task_id} 任务")
        invalid_runtime = memory_sync.read_session_runtime(self.root, discussion_id)
        assert invalid_runtime is not None
        self.assertEqual(invalid_runtime["session"]["phase"], "waiting_for_user_launch")

        registered = memory_sync.register_codex_worker(
            self.root,
            self.config,
            task_id,
            discussion_id,
            thread_id,
            inspectable=True,
            controllable=True,
            independent_context=True,
        )
        self.assertTrue(registered["ok"], registered)
        runtime = memory_sync.read_session_runtime(self.root, discussion_id)
        assert runtime is not None
        self.assertEqual(runtime["session"]["phase"], "waiting_for_worker")
        handle = runtime["worker_runtime"]["worker_handle"]
        self.assertEqual(handle["container_kind"], "codex_agent_thread")
        self.assertEqual(handle["thread_or_session_id"], thread_id)
        self.assertTrue(handle["inspectable"])
        self.assertTrue(handle["controllable"])

    def test_codex_prepare_does_not_create_authority_for_an_unapproved_task(self) -> None:
        task_id = "042"
        discussion_id = "discussion-042"
        self.prepare_claude_worker_task(task_id, discussion_id, host="codex")
        memory_sync.apply_session_runtime_patch(
            self.root,
            discussion_id,
            {"task": {"lifecycle": "draft", "worker_authorized": False}},
        )
        denied = memory_sync.prepare_codex_worker(
            self.root, self.config, task_id, discussion_id
        )
        self.assertFalse(denied["ok"])
        self.assertEqual(denied["error"], "worker_launch_not_authorized")

    def test_codex_spawn_failure_cli_outputs_only_manual_command(self) -> None:
        task_id = "043"
        discussion_id = "discussion-043"
        self.prepare_claude_worker_task(task_id, discussion_id, host="codex")
        host_adapter_module = sys.modules["host_adapter"]
        args = mock.Mock(
            codex_worker_action="fail",
            task_id=task_id,
            discussion_session_id=discussion_id,
            reason="native_spawn_failed",
        )
        with (
            mock.patch.object(host_adapter_module, "find_git_root", return_value=self.root),
            mock.patch.object(host_adapter_module, "load_config", return_value=self.config),
            mock.patch("builtins.print") as printed,
        ):
            exit_code = host_adapter_module.codex_worker_main(args)
        self.assertEqual(exit_code, 0)
        printed.assert_called_once_with(f"执行 {task_id} 任务")

    def test_helper_and_hidden_agents_cannot_acquire_formal_worker_claim(self) -> None:
        for agent_kind, container_kind in (
            ("helper", "helper_subagent"),
            ("hidden_internal", "hidden_internal_agent"),
        ):
            with self.subTest(agent_kind=agent_kind):
                denied = memory_sync.acquire_claim(
                    self.root,
                    "044",
                    1,
                    f"{agent_kind}-044",
                    agent_platform="codex",
                    container_kind=container_kind,
                    agent_kind=agent_kind,
                    require_clean=True,
                )
                self.assertFalse(denied["ok"])
                self.assertEqual(
                    denied["error"], "helper_agent_cannot_acquire_worker_claim"
                )

    def test_codex_structured_terminal_state_still_requires_report_and_released_claim(self) -> None:
        task_id = "045"
        discussion_id = "discussion-045"
        thread_id = "codex-thread-045"
        task_path = f"tasks/build/{task_id}-codex-worker.md"
        report_path = f"reports/runs/{task_id}-attempt-1.md"
        self.prepare_claude_worker_task(task_id, discussion_id, host="codex")
        registered = memory_sync.register_codex_worker(
            self.root,
            self.config,
            task_id,
            discussion_id,
            thread_id,
            inspectable=True,
            controllable=True,
            independent_context=True,
        )
        self.assertTrue(registered["ok"], registered)
        claim_process = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "claim",
                "acquire",
                task_id,
                "--worker-id",
                thread_id,
                "--session-id",
                thread_id,
                "--host-thread-ref",
                thread_id,
                "--host",
                "codex",
                "--container-kind",
                "codex_agent_thread",
                "--agent-kind",
                "formal_worker",
            ],
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(claim_process.returncode, 0, claim_process.stderr)
        claim = json.loads(claim_process.stdout)["claim"]
        incomplete = memory_sync.observe_codex_worker(
            self.root, self.config, discussion_id, thread_id, "completed"
        )
        self.assertFalse(incomplete["durable_terminal_evidence"])
        self.assertEqual(incomplete["sync_status"], "manual_intervention_required")

        self.write(
            task_path,
            self.execution_ready_task(
                task_id,
                status="completed",
                worker_authorized=True,
                run_report=report_path,
            ),
        )
        self.write(
            report_path,
            self.structured_run_report(
                f"{task_id}-attempt-1", task_id=task_id, status="completed"
            ),
        )
        self.git("add", task_path, report_path)
        self.git("commit", "-qm", f"complete {task_id}")
        released = memory_sync.update_claim(
            self.root,
            claim["claim_id"],
            "release",
            branch=claim["branch"],
            worktree=claim["worktree"],
        )
        self.assertTrue(released["ok"], released)
        notification = memory_sync.enqueue_terminal_notification_from_claim(
            self.root, self.config, released["claim"]
        )
        self.assertTrue(notification["ok"], notification)
        completed = memory_sync.observe_codex_worker(
            self.root, self.config, discussion_id, thread_id, "completed"
        )
        self.assertTrue(completed["durable_terminal_evidence"])
        self.assertEqual(completed["sync_status"], "integration_pending")
        consumed = memory_sync.consume_worker_notifications(self.root, discussion_id)
        self.assertEqual(len(consumed["notifications"]), 1)
        self.assertEqual(
            consumed["notifications"][0]["worker_session_id"], thread_id
        )

    def test_claude_background_worker_launch_records_real_session_before_claim(self) -> None:
        task_id = "036"
        discussion_id = "discussion-036"
        worker_id = "12345678-1234-1234-1234-123456789abc"
        self.prepare_claude_worker_task(task_id, discussion_id)
        host_adapter_module = sys.modules["host_adapter"]
        capability = memory_sync.ClaudeWorkerCapability(
            tier="background_session",
            claude_executable="/bin/claude",
            agent_definition=str(self.root / ".claude/agents/wishgraph-worker.md"),
            supports_background=True,
            supports_agents_json=True,
            supports_fork=True,
            reason="native_background_session_available",
        )
        before = {"ok": True, "sessions": []}
        after = {
            "ok": True,
            "sessions": [
                {
                    "id": "12345678",
                    "sessionId": worker_id,
                    "cwd": str(self.root),
                    "state": "working",
                }
            ],
        }
        launched_process = subprocess.CompletedProcess(
            [],
            0,
            stdout=(
                "backgrounded · 12345678\n"
                "  claude agents             list sessions\n"
            ),
            stderr="",
        )
        with (
            mock.patch.object(
                host_adapter_module,
                "detect_claude_worker_capability",
                return_value=capability,
            ),
            mock.patch.object(
                host_adapter_module,
                "_query_claude_agents",
                side_effect=[before, after],
            ),
            mock.patch.object(
                host_adapter_module, "_run_process", return_value=launched_process
            ) as run_process,
        ):
            payload = memory_sync.launch_claude_worker(
                self.root, self.config, task_id, discussion_id
            )
        self.assertTrue(payload["ok"], payload)
        self.assertTrue(payload["launched"])
        self.assertEqual(payload["claude_session_id"], worker_id)
        self.assertEqual(
            run_process.call_args.args[0],
            [
                "/bin/claude",
                "--bg",
                "--agent",
                "wishgraph-worker",
                "执行 036 任务",
            ],
        )
        runtime = memory_sync.read_session_runtime(self.root, discussion_id)
        assert runtime is not None
        self.assertEqual(runtime["session"]["phase"], "waiting_for_worker")
        self.assertEqual(runtime["worker_runtime"]["claude_session_id"], worker_id)
        self.assertEqual(runtime["worker_runtime"]["active_task_id"], task_id)
        self.assertEqual(runtime["worker_runtime"]["claim_id"], "")
        self.assertEqual(runtime["worker_runtime"]["binding_status"], "awaiting_claim")
        handle = runtime["worker_runtime"]["worker_handle"]
        self.assertEqual(handle["container_kind"], "claude_background_session")
        self.assertEqual(handle["thread_or_session_id"], worker_id)
        worker_runtime = memory_sync.read_session_runtime(self.root, worker_id)
        assert worker_runtime is not None
        self.assertEqual(
            worker_runtime["launch_context"]["agent_kind"], "formal_worker"
        )
        claim_process = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "claim",
                "acquire",
                task_id,
                "--worker-id",
                worker_id,
                "--session-id",
                worker_id,
                "--host-thread-ref",
                worker_id,
                "--host",
                "claude",
                "--container-kind",
                "claude_background_session",
                "--agent-kind",
                "formal_worker",
            ],
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(claim_process.returncode, 0, claim_process.stderr)
        self.assertEqual(
            json.loads(claim_process.stdout)["claim"]["container_kind"],
            "claude_background_session",
        )

    def test_claude_launch_failure_cli_outputs_only_manual_command(self) -> None:
        task_id = "037"
        discussion_id = "discussion-037"
        self.prepare_claude_worker_task(task_id, discussion_id)
        host_adapter_module = sys.modules["host_adapter"]
        capability = memory_sync.ClaudeWorkerCapability(
            tier="background_session",
            claude_executable="/bin/claude",
            agent_definition="managed-agent",
            supports_background=True,
            supports_agents_json=True,
            supports_fork=True,
            reason="native_background_session_available",
        )
        failed_process = subprocess.CompletedProcess(
            [], 1, stdout="", stderr="launch failed"
        )
        with (
            mock.patch.object(
                host_adapter_module,
                "detect_claude_worker_capability",
                return_value=capability,
            ),
            mock.patch.object(
                host_adapter_module,
                "_query_claude_agents",
                return_value={"ok": True, "sessions": []},
            ),
            mock.patch.object(
                host_adapter_module, "_run_process", return_value=failed_process
            ),
        ):
            payload = memory_sync.launch_claude_worker(
                self.root, self.config, task_id, discussion_id
            )
        self.assertTrue(payload["fallback"])
        self.assertEqual(payload["user_message"], "执行 037 任务")
        runtime = memory_sync.read_session_runtime(self.root, discussion_id)
        assert runtime is not None
        self.assertEqual(runtime["session"]["phase"], "waiting_for_user_launch")
        self.assertEqual(runtime["worker_runtime"]["launch_status"], "manual_required")

        args = mock.Mock(
            claude_worker_action="launch",
            claude_executable="claude",
            task_id=task_id,
            discussion_session_id=discussion_id,
        )
        with (
            mock.patch.object(host_adapter_module, "find_git_root", return_value=self.root),
            mock.patch.object(host_adapter_module, "load_config", return_value=self.config),
            mock.patch.object(
                host_adapter_module, "launch_claude_worker", return_value=payload
            ),
            mock.patch("builtins.print") as printed,
        ):
            exit_code = host_adapter_module.claude_worker_main(args)
        self.assertEqual(exit_code, 0)
        printed.assert_called_once_with("执行 037 任务")

    def test_claude_forked_subagent_never_launches_formal_business_worker(self) -> None:
        task_id = "039"
        discussion_id = "discussion-039"
        self.prepare_claude_worker_task(task_id, discussion_id)
        host_adapter_module = sys.modules["host_adapter"]
        capability = memory_sync.ClaudeWorkerCapability(
            tier="forked_subagent",
            claude_executable="/bin/claude",
            supports_background=False,
            supports_agents_json=False,
            supports_fork=True,
            reason="managed_worker_agent_or_background_session_unavailable",
        )
        with (
            mock.patch.object(
                host_adapter_module,
                "detect_claude_worker_capability",
                return_value=capability,
            ),
            mock.patch.object(
                host_adapter_module,
                "_run_process",
                side_effect=AssertionError("formal Worker must not use a fork"),
            ),
        ):
            payload = memory_sync.launch_claude_worker(
                self.root, self.config, task_id, discussion_id
            )
        self.assertTrue(payload["fallback"])
        self.assertEqual(payload["capability"]["tier"], "forked_subagent")
        self.assertEqual(payload["user_message"], "执行 039 任务")

    def test_claude_refresh_binds_claim_and_syncs_completed_worker(self) -> None:
        task_id = "038"
        discussion_id = "discussion-038"
        worker_id = "87654321-1234-1234-1234-123456789abc"
        self.prepare_claude_worker_task(task_id, discussion_id)
        claimed = memory_sync.acquire_claim(
            self.root,
            task_id,
            1,
            worker_id,
            host_thread_ref=worker_id,
            agent_platform="claude",
            allowed_scope=["Change only the assigned implementation."],
            validation_plan=["Run the focused tests."],
            require_clean=True,
        )
        self.assertTrue(claimed["ok"], claimed)
        memory_sync.apply_session_runtime_patch(
            self.root,
            discussion_id,
            {
                "session": {
                    "phase": "waiting_for_worker",
                    "expected_transition": {"kind": "wait_for_worker", "task_id": task_id},
                },
                "worker_runtime": {
                    "agent_platform": "claude",
                    "active_task_id": task_id,
                    "claude_session_id": worker_id,
                    "claude_full_session_id": worker_id,
                    "claude_short_id": "87654321",
                    "binding_status": "awaiting_claim",
                },
            },
        )
        host_adapter_module = sys.modules["host_adapter"]
        capability = memory_sync.ClaudeWorkerCapability(
            tier="background_session",
            claude_executable="/bin/claude",
            agent_definition="managed-agent",
            supports_background=True,
            supports_agents_json=True,
            supports_fork=True,
            reason="native_background_session_available",
        )
        working = {
            "ok": True,
            "sessions": [
                {"id": "87654321", "sessionId": worker_id, "state": "working"}
            ],
        }
        with (
            mock.patch.object(
                host_adapter_module,
                "detect_claude_worker_capability",
                return_value=capability,
            ),
            mock.patch.object(
                host_adapter_module, "_query_claude_agents", return_value=working
            ),
        ):
            active = memory_sync.refresh_claude_worker(
                self.root, self.config, discussion_id
            )
        self.assertEqual(active["sync_status"], "waiting_for_worker")
        active_runtime = memory_sync.read_session_runtime(self.root, discussion_id)
        assert active_runtime is not None
        self.assertEqual(
            active_runtime["worker_runtime"]["claim_id"],
            claimed["claim"]["claim_id"],
        )
        self.assertEqual(
            active_runtime["worker_runtime"]["branch"], claimed["claim"]["branch"]
        )
        self.assertEqual(
            active_runtime["worker_runtime"]["worktree"], claimed["claim"]["worktree"]
        )

        task_path = f"tasks/build/{task_id}-claude-worker.md"
        self.write(
            task_path,
            self.execution_ready_task(
                task_id,
                status="completed",
                worker_authorized=True,
                run_report=f"reports/runs/{task_id}-attempt-1.md",
            ),
        )
        self.write(f"reports/runs/{task_id}-attempt-1.md", "# Completed\n")
        self.git("add", task_path, f"reports/runs/{task_id}-attempt-1.md")
        self.git("commit", "-qm", f"complete {task_id}")
        released = memory_sync.update_claim(
            self.root,
            claimed["claim"]["claim_id"],
            "release",
            branch=claimed["claim"]["branch"],
            worktree=claimed["claim"]["worktree"],
        )
        self.assertTrue(released["ok"], released)
        completed = {
            "ok": True,
            "sessions": [
                {"id": "87654321", "sessionId": worker_id, "state": "done"}
            ],
        }
        with (
            mock.patch.object(
                host_adapter_module,
                "detect_claude_worker_capability",
                return_value=capability,
            ),
            mock.patch.object(
                host_adapter_module, "_query_claude_agents", return_value=completed
            ),
        ):
            terminal = memory_sync.refresh_claude_worker(
                self.root, self.config, discussion_id
            )
        self.assertTrue(terminal["durable_terminal_evidence"])
        self.assertEqual(terminal["sync_status"], "integration_pending")
        terminal_runtime = memory_sync.read_session_runtime(self.root, discussion_id)
        assert terminal_runtime is not None
        self.assertEqual(terminal_runtime["session"]["phase"], "integration_pending")
        self.assertEqual(
            terminal_runtime["session"]["expected_transition"]["kind"],
            "auto_integrate",
        )
        self.assertEqual(terminal_runtime["task"]["lifecycle"], "completed")

    def test_claude_refresh_missing_session_requires_manual_evidence_repair(self) -> None:
        task_id = "040"
        discussion_id = "discussion-040"
        self.prepare_claude_worker_task(task_id, discussion_id)
        memory_sync.apply_session_runtime_patch(
            self.root,
            discussion_id,
            {
                "session": {
                    "phase": "waiting_for_worker",
                    "expected_transition": {"kind": "wait_for_worker", "task_id": task_id},
                },
                "worker_runtime": {
                    "agent_platform": "claude",
                    "active_task_id": task_id,
                    "claude_session_id": "missing-session-id",
                    "claude_short_id": "missing1",
                },
            },
        )
        host_adapter_module = sys.modules["host_adapter"]
        capability = memory_sync.ClaudeWorkerCapability(
            tier="background_session",
            claude_executable="/bin/claude",
            agent_definition="managed-agent",
            supports_background=True,
            supports_agents_json=True,
            supports_fork=True,
            reason="native_background_session_available",
        )
        with (
            mock.patch.object(
                host_adapter_module,
                "detect_claude_worker_capability",
                return_value=capability,
            ),
            mock.patch.object(
                host_adapter_module,
                "_query_claude_agents",
                return_value={"ok": True, "sessions": []},
            ),
        ):
            payload = memory_sync.refresh_claude_worker(
                self.root, self.config, discussion_id
            )
        self.assertFalse(payload["durable_terminal_evidence"])
        self.assertEqual(payload["sync_status"], "manual_intervention_required")
        runtime = memory_sync.read_session_runtime(self.root, discussion_id)
        assert runtime is not None
        self.assertEqual(runtime["session"]["phase"], "waiting_for_worker")
        self.assertEqual(
            runtime["worker_runtime"]["recovery_reason"],
            "claude_session_missing_or_unknown",
        )

    def test_claim_revoke_requires_explicit_user_authorization(self) -> None:
        acquired = memory_sync.acquire_claim(
            self.root, "030a", 1, "worker-revoke", require_clean=True
        )
        self.assertTrue(acquired["ok"], acquired)
        claim_id = acquired["claim"]["claim_id"]
        base = [
            sys.executable,
            str(HOOK_ASSETS / "memory_sync.py"),
            "claim",
            "revoke",
            claim_id,
        ]
        denied = subprocess.run(
            base,
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(denied.returncode, 1)
        self.assertEqual(
            json.loads(denied.stdout)["error"], "explicit_user_authorization_required"
        )
        allowed = subprocess.run(
            base + ["--authorized-by-user"],
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        self.assertEqual(json.loads(allowed.stdout)["claim"]["lease_status"], "revoked")

    def test_competitive_natural_language_and_candidate_plan(self) -> None:
        command = memory_sync.parse_task_command(
            "让两个 Agent 分别执行012，最后比较谁做得好"
        )
        assert command is not None
        self.assertEqual(command["action"], "competitive")
        self.assertTrue(command["authorizes_execution"])
        self.write("tasks/build/012-root.md", self.structured_task("012-root"))
        process = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "competitive-plan",
                "012",
                "--candidates",
                "2",
            ],
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        payload = json.loads(process.stdout)
        self.assertEqual(
            [item["task_id"] for item in payload["candidates"]], ["012a", "012b"]
        )
        self.assertTrue(payload["rules"]["integrate_exactly_one_winner"])

    def test_competitive_claims_allow_distinct_worktrees(self) -> None:
        other = self.root.parent / f"{self.root.name}-competitive"
        self.git("worktree", "add", "-q", "-b", "competitive-worker", str(other))
        try:
            first = memory_sync.acquire_claim(
                self.root,
                "040a",
                1,
                "candidate-a",
                execution_mode="competitive",
                require_clean=True,
            )
            second = memory_sync.acquire_claim(
                other,
                "040b",
                1,
                "candidate-b",
                execution_mode="competitive",
                require_clean=True,
            )
            self.assertTrue(first["ok"], first)
            self.assertTrue(second["ok"], second)
            self.assertNotEqual(
                first["claim"]["worktree"], second["claim"]["worktree"]
            )
        finally:
            self.git("worktree", "remove", "--force", str(other))
            self.git("branch", "-D", "competitive-worker")

    def test_invalid_structured_run_state_blocks_closeout(self) -> None:
        self.write("src/app.py", "print('structured')\n")
        content = self.run_report("structured-invalid").replace(
            "## Work Unit\n\n",
            "## Work Unit\n\n<!-- wishgraph:run-state:start -->\n"
            "```json\n{not-json}\n```\n<!-- wishgraph:run-state:end -->\n\n",
            1,
        )
        self.write("reports/runs/structured-invalid.md", content)
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertFalse(result.ok)
        self.assertTrue(any("invalid JSON" in error for error in result.errors))

    def test_new_structured_draft_task_is_a_valid_planning_change(self) -> None:
        self.write("tasks/build/020-planned.md", self.structured_task("020-planned"))
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertTrue(result.ok, result.errors)

    def test_lightweight_revision_record_is_valid_without_full_task_sections(self) -> None:
        self.write(
            "tasks/build/012-parent.md",
            self.structured_task(
                "012-parent",
                status="completed",
                worker_authorized=True,
                run_report="reports/runs/000-bootstrap.md",
            ),
        )
        self.git("add", "tasks/build/012-parent.md")
        self.git("commit", "-qm", "parent task fixture")
        self.write(
            "tasks/revisions/012-r1.md",
            (HOOK_ASSETS.parent / "templates" / "TASK_REVISION.md").read_text(
                encoding="utf-8"
            ),
        )
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertTrue(result.ok, result.errors)
        allocated = memory_sync.next_revision_id(self.root, self.config, "012")
        self.assertEqual(allocated["revision_id"], "012-r1")
        self.assertTrue(allocated["reuse_open_revision"])

    def test_revision_closeout_uses_revision_report_and_is_auto_eligible(self) -> None:
        self.write(
            "tasks/build/012-parent.md",
            self.structured_task(
                "012-parent",
                status="completed",
                worker_authorized=True,
                run_report="reports/runs/000-bootstrap.md",
            ),
        )
        self.git("add", "tasks/build/012-parent.md")
        self.git("commit", "-qm", "parent task fixture")
        report_path = "reports/runs/012-r1-attempt-1.md"
        revision_state = {
            "schema_version": 1,
            "kind": "revision",
            "revision_id": "012-r1",
            "parent_task_id": "012",
            "status": "completed",
            "user_request": "蓝色深一点",
            "allowed_scope": ["src/app.py"],
            "validation_plan": ["tests"],
            "run_report": report_path,
            "worker_creation_authorized": True,
        }
        self.write(
            "tasks/revisions/012-r1.md",
            "<!-- wishgraph:revision-state:start -->\n```json\n"
            + json.dumps(revision_state, ensure_ascii=False, indent=2)
            + "\n```\n<!-- wishgraph:revision-state:end -->\n",
        )
        self.write("src/app.py", "print('dark blue')\n")
        self.write(
            report_path,
            self.structured_run_report(
                "012-r1-attempt-1",
                task_id="012",
                revision_id="012-r1",
                change_class="revision",
                changed_paths=["src/app.py"],
            ),
        )
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertTrue(result.ok, result.errors)
        status = memory_sync.integration_state(self.root, self.config).as_dict()
        self.assertTrue(status["auto_integration_eligible"])
        revision_units = [
            unit for unit in status["work_units"] if unit.get("revision_id") == "012-r1"
        ]
        self.assertEqual(revision_units[0]["lifecycle_status"], "completed")
        status = memory_sync.integration_state(self.root, self.config).as_dict()
        self.assertNotIn("reports/runs/020-planned.md", status["waiting_reports"])

    def test_draft_task_can_be_refined_before_worker_authorization(self) -> None:
        task_id = "020b-refine"
        path = f"tasks/build/{task_id}.md"
        self.write(path, self.structured_task(task_id))
        self.git("add", path)
        self.git("commit", "-qm", "draft task fixture")
        refined = self.structured_task(
            task_id,
            work_type="parallel_batch",
            batch_id="batch-refined",
            integration_policy="requires_explicit_user_confirmation",
        ).replace("Implement the bounded task.", "Implement the refined bounded task.")
        self.write(path, refined)
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertTrue(result.ok, result.errors)

    def test_task_approval_requires_explicit_worker_creation_authorization(self) -> None:
        path = "tasks/build/021-authorize.md"
        self.write(path, self.structured_task("021-authorize"))
        self.git("add", path)
        self.git("commit", "-qm", "plan structured task")

        self.write(
            path,
            self.structured_task("021-authorize", status="approved"),
        )
        denied = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertFalse(denied.ok)
        self.assertTrue(any("Worker creation authorization" in error for error in denied.errors))

        self.write(
            path,
            self.structured_task(
                "021-authorize", status="approved", worker_authorized=True
            ),
        )
        approved = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertTrue(approved.ok, approved.errors)

    def test_task_approval_cannot_silently_change_execution_identity(self) -> None:
        task_id = "021b-immutable"
        path = f"tasks/build/{task_id}.md"
        self.write(path, self.structured_task(task_id))
        self.git("add", path)
        self.git("commit", "-qm", "plan immutable task")
        changed = json.loads(
            json.dumps(
                {
                    "schema_version": 1,
                    "kind": "task",
                    "task_id": task_id,
                    "status": "approved",
                    "work_type": "sequential",
                    "batch_id": None,
                    "run_report": "reports/runs/changed-identity.md",
                    "worker_creation_authorized": True,
                    "integration_policy": "inherited_task_approval",
                }
            )
        )
        content = self.structured_task(
            task_id, status="approved", worker_authorized=True
        )
        block, errors = memory_sync.parse_workflow_block(content, "task")
        self.assertEqual(errors, [])
        assert block is not None
        content = content.replace(
            json.dumps(block.data, ensure_ascii=False, indent=2),
            json.dumps(changed, ensure_ascii=False, indent=2),
        )
        self.write(path, content)
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertFalse(result.ok)
        self.assertTrue(any("task_id is immutable" in error for error in result.errors))
        self.assertTrue(any("run_report may change only" in error for error in result.errors))

    def test_task_rejects_invalid_draft_to_completed_transition(self) -> None:
        path = "tasks/build/022-transition.md"
        self.write(path, self.structured_task("022-transition"))
        self.git("add", path)
        self.git("commit", "-qm", "plan transition task")
        self.write(
            path,
            self.structured_task(
                "022-transition", status="completed", worker_authorized=True
            ),
        )
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertFalse(result.ok)
        self.assertTrue(any("invalid task transition" in error for error in result.errors))

    def test_blocked_task_retry_keeps_id_and_increments_attempt(self) -> None:
        task_path = "tasks/build/026-retry.md"
        first_report = "reports/runs/026-attempt-1.md"
        self.write(first_report, self.structured_run_report("026-attempt-1", status="blocked", readiness="blocked"))
        self.write(
            task_path,
            self.structured_task(
                "026-retry",
                status="blocked",
                worker_authorized=True,
                run_report=first_report,
            ),
        )
        self.git("add", task_path, first_report)
        self.git("commit", "-qm", "blocked retry fixture")

        self.write(
            task_path,
            self.structured_task(
                "026-retry",
                status="approved",
                worker_authorized=True,
                attempt=2,
                run_report="reports/runs/026-attempt-2.md",
            ),
        )
        valid_retry = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertTrue(valid_retry.ok, valid_retry.errors)

        self.write(
            task_path,
            self.structured_task(
                "026-retry",
                status="approved",
                worker_authorized=True,
                attempt=1,
                run_report="reports/runs/026-attempt-2.md",
            ),
        )
        invalid_retry = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertFalse(invalid_retry.ok)
        self.assertTrue(any("increment attempt" in error for error in invalid_retry.errors))

    def test_approved_task_filename_cannot_be_renamed(self) -> None:
        old_path = "tasks/build/027-original.md"
        new_path = "tasks/build/027-renamed.md"
        self.write(
            old_path,
            self.structured_task(
                "027-original", status="approved", worker_authorized=True
            ),
        )
        self.git("add", old_path)
        self.git("commit", "-qm", "approved filename fixture")
        self.git("mv", old_path, new_path)
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertFalse(result.ok)
        self.assertTrue(any("filename is immutable" in error for error in result.errors))

    def test_allocated_task_id_cannot_be_reused_by_deleting_spec(self) -> None:
        path = "tasks/build/027a-allocated.md"
        self.write(path, self.structured_task("027a-allocated"))
        self.git("add", path)
        self.git("commit", "-qm", "allocated task fixture")
        (self.root / path).unlink()
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertFalse(result.ok)
        self.assertTrue(any("cannot be deleted" in error for error in result.errors))

    def test_running_task_is_not_a_valid_closeout_without_report(self) -> None:
        task_id = "022a-running"
        task_path = f"tasks/build/{task_id}.md"
        self.write(
            task_path,
            self.structured_task(
                task_id, status="approved", worker_authorized=True
            ),
        )
        self.git("add", task_path)
        self.git("commit", "-qm", "approve running fixture")
        self.write(
            task_path,
            self.structured_task(
                task_id, status="running", worker_authorized=True
            ),
        )
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertFalse(result.ok)
        self.assertTrue(any("requires exactly one" in error for error in result.errors))

    def test_integrated_task_can_move_to_reviewed_without_worker_closeout(self) -> None:
        task_id = "022b-reviewed"
        task_path = f"tasks/build/{task_id}.md"
        report_path = f"reports/runs/{task_id}.md"
        self.write(report_path, self.structured_run_report(task_id))
        self.write(
            task_path,
            self.structured_task(
                task_id, status="integrated", worker_authorized=True
            ),
        )
        self.git("add", task_path, report_path)
        self.git("commit", "-qm", "integrate reviewed fixture")
        self.write(
            task_path,
            self.structured_task(
                task_id, status="reviewed", worker_authorized=True
            ),
        )
        self.write(
            "prompts/DISCUSSION_AI.md",
            self.discussion("reviewed/022b-reviewed"),
        )
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertTrue(result.ok, result.errors)

    def test_code_change_without_closeout_fails(self) -> None:
        self.write("src/app.py", "print('changed')\n")
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertFalse(result.ok)
        self.assertTrue(any("reports/runs" in error for error in result.errors))

    def test_ad_hoc_change_with_task_scoped_report_passes(self) -> None:
        self.write("src/app.py", "print('changed')\n")
        self.write(
            "reports/runs/ad-hoc-001.md",
            self.run_report(
                "ad-hoc-001",
                {
                    "prompts/DISCUSSION_AI.md": (
                        "Integrate",
                        "Expose the completed ad-hoc result after integration",
                    )
                },
            ),
        )
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertTrue(result.ok, result.errors)

    def test_worker_closeout_requires_structured_task_completion(self) -> None:
        task_id = "023-worker-state"
        task_path = f"tasks/build/{task_id}.md"
        report_path = f"reports/runs/{task_id}.md"
        self.write(
            task_path,
            self.structured_task(
                task_id, status="approved", worker_authorized=True
            ),
        )
        self.git("add", task_path)
        self.git("commit", "-qm", "approve structured worker")
        self.write("src/worker_state.py", "print('done')\n")
        self.write(report_path, self.structured_run_report(task_id))

        stale = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertFalse(stale.ok)
        self.assertTrue(any("must set task status to completed" in error for error in stale.errors))

        self.write(
            task_path,
            self.structured_task(
                task_id, status="completed", worker_authorized=True
            ),
        )
        completed = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertTrue(completed.ok, completed.errors)

    def test_staged_commit_requires_staged_run_report(self) -> None:
        self.write("src/app.py", "print('changed')\n")
        self.write(
            "reports/runs/001-staged.md",
            self.run_report("001-staged"),
        )
        self.git("add", "src/app.py")
        failed = memory_sync.check_sync(self.root, self.config, "staged")
        self.assertFalse(failed.ok)
        self.assertTrue(any("reports/runs" in error for error in failed.errors))
        self.git("add", "reports/runs/001-staged.md")
        passed = memory_sync.check_sync(self.root, self.config, "staged")
        self.assertTrue(passed.ok, passed.errors)

    def test_worker_report_rejects_updated_status(self) -> None:
        self.write("README.md", "documentation change\n")
        self.write(
            "reports/runs/002-docs.md",
            self.run_report("002-docs", {"PRD.md": ("Updated", "Scope changed")}),
        )
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertFalse(result.ok)
        self.assertTrue(any("must be Integrate or N/A" in error for error in result.errors))

    def test_worker_cannot_edit_shared_discussion_state(self) -> None:
        self.write("src/app.py", "print('changed')\n")
        self.write(
            "prompts/DISCUSSION_AI.md",
            self.discussion("worker-should-not-write"),
        )
        self.write(
            "reports/runs/003-worker.md",
            self.run_report("003-worker"),
        )
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertFalse(result.ok)
        self.assertTrue(any("must not update shared memory" in error for error in result.errors))

    def test_worker_cannot_edit_project_status(self) -> None:
        self.write(
            "reports/PROJECT_STATUS.md",
            self.overview(["reports/runs/000-bootstrap.md"]) + "\nworker edit\n",
        )
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertFalse(result.ok)
        self.assertTrue(
            any("at least one new reports/runs/*.md" in error for error in result.errors)
        )

    def test_docs_only_change_uses_worker_report(self) -> None:
        self.write("README.md", "documentation change\n")
        self.write(
            "reports/runs/ad-hoc-docs-copy-fix.md",
            self.run_report("ad-hoc-docs-copy-fix"),
        )
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertTrue(result.ok, result.errors)

    def test_pre_tool_use_blocks_unsynced_commit(self) -> None:
        self.write("src/app.py", "print('changed')\n")
        self.git("add", "src/app.py")
        process = subprocess.run(
            [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "pre-tool-use"],
            cwd=self.root,
            input=json.dumps(
                {
                    "cwd": str(self.root),
                    "tool_name": "Bash",
                    "tool_input": {"command": "git commit -m test"},
                }
            ),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        payload = json.loads(process.stdout)
        self.assertEqual(
            payload["hookSpecificOutput"]["permissionDecision"],
            "deny",
        )

    def test_pre_tool_use_blocks_implicit_staging_commit(self) -> None:
        process = subprocess.run(
            [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "pre-tool-use"],
            cwd=self.root,
            input=json.dumps(
                {
                    "cwd": str(self.root),
                    "tool_name": "Bash",
                    "tool_input": {"command": "git commit -am 'shortcut'"},
                }
            ),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        payload = json.loads(process.stdout)
        self.assertEqual(payload["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("stage implicitly", payload["hookSpecificOutput"]["permissionDecisionReason"])

    def test_session_runtime_round_trip_stays_outside_worktree(self) -> None:
        result = memory_sync.write_session_runtime(
            self.root,
            "discussion-1",
            {
                "session": {
                    "session_id": "discussion-1",
                    "role": "discussion",
                    "host": "codex",
                    "phase": "planning",
                    "expected_transition": None,
                }
            },
        )
        self.assertTrue(result["ok"])
        runtime = memory_sync.read_session_runtime(self.root, "discussion-1")
        assert runtime is not None
        self.assertEqual(runtime["session"]["role"], "discussion")
        self.assertEqual(self.git("status", "--porcelain").stdout, "")

    def test_session_runtime_apply_deep_merges_reducer_patch(self) -> None:
        memory_sync.write_session_runtime(
            self.root,
            "discussion-apply",
            {
                "session": {
                    "session_id": "discussion-apply",
                    "role": "discussion",
                    "host": "codex",
                    "phase": "awaiting_worker_authorization",
                    "expected_transition": {
                        "kind": "approve_worker_launch",
                        "task_id": "002",
                    },
                },
                "task": {
                    "task_id": "002",
                    "lifecycle": "draft",
                    "worker_authorized": False,
                },
            },
        )
        process = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "session",
                "apply",
                "discussion-apply",
            ],
            cwd=self.root,
            input=json.dumps(
                {
                    "session": {
                        "phase": "routing_worker",
                        "expected_transition": None,
                    },
                    "task": {
                        "lifecycle": "approved",
                        "worker_authorized": True,
                    },
                }
            ),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        payload = json.loads(process.stdout)
        self.assertTrue(payload["ok"])
        runtime = payload["runtime"]
        self.assertEqual(runtime["session"]["role"], "discussion")
        self.assertEqual(runtime["session"]["phase"], "routing_worker")
        self.assertIsNone(runtime["session"]["expected_transition"])
        self.assertEqual(runtime["task"]["task_id"], "002")
        self.assertEqual(runtime["task"]["lifecycle"], "approved")

    def test_pre_tool_use_denies_discussion_build_without_claim(self) -> None:
        memory_sync.write_session_runtime(
            self.root,
            "discussion-1",
            {
                "session": {
                    "session_id": "discussion-1",
                    "role": "discussion",
                    "host": "codex",
                    "phase": "planning",
                    "expected_transition": None,
                }
            },
        )
        process = subprocess.run(
            [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "pre-tool-use"],
            cwd=self.root,
            input=json.dumps(
                {
                    "cwd": str(self.root),
                    "session_id": "discussion-1",
                    "tool_name": "Bash",
                    "tool_input": {"command": "python3 -m unittest"},
                }
            ),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        payload = json.loads(process.stdout)
        self.assertEqual(payload["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("Claim", payload["hookSpecificOutput"]["permissionDecisionReason"])

    def test_pre_tool_use_denies_discussion_business_file_write(self) -> None:
        memory_sync.write_session_runtime(
            self.root,
            "discussion-1",
            {
                "session": {
                    "session_id": "discussion-1",
                    "role": "discussion",
                    "host": "codex",
                    "phase": "planning",
                    "expected_transition": None,
                }
            },
        )
        process = subprocess.run(
            [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "pre-tool-use"],
            cwd=self.root,
            input=json.dumps(
                {
                    "cwd": str(self.root),
                    "session_id": "discussion-1",
                    "tool_name": "Write",
                    "tool_input": {"file_path": str(self.root / "src" / "app.py")},
                }
            ),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        payload = json.loads(process.stdout)
        self.assertEqual(payload["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_pre_tool_use_allows_bound_worker_build(self) -> None:
        acquired = memory_sync.acquire_claim(
            self.root,
            "002",
            1,
            "worker-session-1",
            branch=self.git("branch", "--show-current").stdout.strip(),
            worktree=str(self.root),
        )
        self.assertTrue(acquired["ok"])
        memory_sync.write_session_runtime(
            self.root,
            "worker-session-1",
            {
                "session": {
                    "session_id": "worker-session-1",
                    "role": "worker",
                    "host": "codex",
                    "phase": "waiting_for_worker",
                    "expected_transition": None,
                },
                "task": {
                    "task_id": "002",
                    "lifecycle": "running",
                    "worker_authorized": True,
                },
            },
        )
        process = subprocess.run(
            [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "pre-tool-use"],
            cwd=self.root,
            input=json.dumps(
                {
                    "cwd": str(self.root),
                    "session_id": "worker-session-1",
                    "tool_name": "Bash",
                    "tool_input": {"command": "python3 -m unittest"},
                }
            ),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        self.assertEqual(json.loads(process.stdout), {})

    def test_worker_apply_patch_is_bounded_to_claim_scope(self) -> None:
        acquired = memory_sync.acquire_claim(
            self.root,
            "044",
            1,
            "worker-scope",
            allowed_scope=["src/**"],
            validation_plan=["python3 -m unittest"],
        )
        self.assertTrue(acquired["ok"], acquired)
        memory_sync.write_session_runtime(
            self.root,
            "worker-scope",
            {
                "session": {
                    "session_id": "worker-scope",
                    "role": "worker",
                    "host": "codex",
                    "phase": "waiting_for_worker",
                    "expected_transition": None,
                },
                "task": {
                    "task_id": "044",
                    "lifecycle": "running",
                    "worker_authorized": True,
                },
            },
        )

        def invoke(patch: str, tool_name: str = "apply_patch") -> dict[str, object]:
            process = subprocess.run(
                [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "pre-tool-use"],
                cwd=self.root,
                input=json.dumps(
                    {
                        "cwd": str(self.root),
                        "session_id": "worker-scope",
                        "tool_name": tool_name,
                        "tool_input": {"command": patch},
                    }
                ),
                text=True,
                stdout=subprocess.PIPE,
                check=True,
            )
            return json.loads(process.stdout)

        allowed = invoke("*** Begin Patch\n*** Update File: src/app.py\n*** End Patch")
        self.assertEqual(allowed, {})
        outside = invoke("*** Begin Patch\n*** Update File: ../outside.py\n*** End Patch")
        self.assertEqual(
            outside["hookSpecificOutput"]["permissionDecision"], "deny"
        )
        inside_shell = invoke("touch src/generated.py", tool_name="Bash")
        self.assertEqual(inside_shell, {})
        opaque_shell = invoke("touch ../outside.py", tool_name="Bash")
        self.assertEqual(
            opaque_shell["hookSpecificOutput"]["permissionDecision"], "deny"
        )

    def test_pre_tool_use_rejects_forged_worker_runtime_without_live_claim(self) -> None:
        memory_sync.write_session_runtime(
            self.root,
            "worker-forged",
            {
                "session": {
                    "session_id": "worker-forged",
                    "role": "worker",
                    "host": "codex",
                    "phase": "waiting_for_worker",
                    "expected_transition": None,
                },
                "task": {
                    "task_id": "002",
                    "lifecycle": "running",
                    "worker_authorized": True,
                },
                "worker_runtime": {
                    "claim_id": "forged-claim",
                    "branch": self.git("branch", "--show-current").stdout.strip(),
                    "worktree": str(self.root),
                },
            },
        )
        process = subprocess.run(
            [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "pre-tool-use"],
            cwd=self.root,
            input=json.dumps(
                {
                    "cwd": str(self.root),
                    "session_id": "worker-forged",
                    "tool_name": "Bash",
                    "tool_input": {"command": "python3 -m unittest"},
                }
            ),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        payload = json.loads(process.stdout)
        self.assertEqual(payload["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_pre_tool_use_worker_may_update_only_its_own_task_state(self) -> None:
        own_task = "tasks/build/033-worker-state.md"
        other_task = "tasks/build/034-other-state.md"
        self.write(own_task, self.execution_ready_task("033-worker-state"))
        self.write(other_task, self.execution_ready_task("034-other-state"))
        self.git("add", own_task, other_task)
        self.git("commit", "-qm", "worker task state fixture")
        acquired = memory_sync.acquire_claim(
            self.root,
            "033",
            1,
            "worker-state-session",
            branch=self.git("branch", "--show-current").stdout.strip(),
            worktree=str(self.root),
        )
        self.assertTrue(acquired["ok"])
        memory_sync.write_session_runtime(
            self.root,
            "worker-state-session",
            {
                "session": {
                    "session_id": "worker-state-session",
                    "role": "worker",
                    "host": "codex",
                    "phase": "waiting_for_worker",
                    "expected_transition": None,
                },
                "task": {
                    "task_id": "033",
                    "lifecycle": "running",
                    "worker_authorized": True,
                },
            },
        )

        def invoke(path: str) -> dict[str, object]:
            process = subprocess.run(
                [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "pre-tool-use"],
                cwd=self.root,
                input=json.dumps(
                    {
                        "cwd": str(self.root),
                        "session_id": "worker-state-session",
                        "tool_name": "Edit",
                        "tool_input": {"file_path": str(self.root / path)},
                    }
                ),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            return json.loads(process.stdout)

        self.assertEqual(invoke(own_task), {})
        denied = invoke(other_task)
        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_integration_lease_cli_requires_discussion_integrating_runtime(self) -> None:
        memory_sync.write_session_runtime(
            self.root,
            "discussion-cli",
            {
                "session": {
                    "session_id": "discussion-cli",
                    "role": "discussion",
                    "host": "codex",
                    "phase": "integrating",
                    "expected_transition": {
                        "kind": "auto_integrate",
                        "task_id": "002",
                    },
                },
                "task": {
                    "task_id": "002",
                    "lifecycle": "completed",
                    "worker_authorized": True,
                },
            },
        )
        process = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "integration-lease",
                "acquire",
                "--session-id",
                "discussion-cli",
                "--integration-id",
                "integration-cli",
                "--task-id",
                "002",
                "--report",
                "reports/runs/002-attempt-1.md",
            ],
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        payload = json.loads(process.stdout)
        runtime = memory_sync.read_session_runtime(self.root, "discussion-cli")
        assert runtime is not None
        self.assertTrue(payload["ok"])
        self.assertEqual(
            runtime["integration_runtime"]["lease_id"], payload["lease"]["lease_id"]
        )

    def test_pre_tool_use_allows_discussion_local_integration_merge_with_lease(self) -> None:
        acquired = memory_sync.acquire_integration_lease(
            self.root,
            session_id="discussion-1",
            integration_id="integration-1",
            task_ids=["002"],
            reports=["reports/runs/002-attempt-1.md"],
            require_clean=False,
        )
        self.assertTrue(acquired["ok"])
        memory_sync.write_session_runtime(
            self.root,
            "discussion-1",
            {
                "session": {
                    "session_id": "discussion-1",
                    "role": "discussion",
                    "host": "codex",
                    "phase": "integrating",
                    "expected_transition": None,
                },
                "task": {
                    "task_id": "002",
                    "lifecycle": "completed",
                    "worker_authorized": True,
                },
            },
        )
        process = subprocess.run(
            [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "pre-tool-use"],
            cwd=self.root,
            input=json.dumps(
                {
                    "cwd": str(self.root),
                    "session_id": "discussion-1",
                    "tool_name": "Bash",
                    "tool_input": {"command": "git merge --no-commit worker-002"},
                }
            ),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        self.assertEqual(json.loads(process.stdout), {})

    def test_integration_lease_allows_closeout_but_not_new_business_implementation(self) -> None:
        acquired = memory_sync.acquire_integration_lease(
            self.root,
            session_id="discussion-closeout",
            integration_id="integration-closeout",
            task_ids=["002"],
            reports=["reports/runs/002-attempt-1.md"],
            require_clean=False,
        )
        self.assertTrue(acquired["ok"])
        memory_sync.write_session_runtime(
            self.root,
            "discussion-closeout",
            {
                "session": {
                    "session_id": "discussion-closeout",
                    "role": "discussion",
                    "host": "codex",
                    "phase": "integrating",
                    "expected_transition": None,
                },
                "task": {
                    "task_id": "002",
                    "lifecycle": "completed",
                    "worker_authorized": True,
                },
            },
        )

        def invoke(tool_name: str, tool_input: dict[str, str]) -> dict[str, object]:
            process = subprocess.run(
                [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "pre-tool-use"],
                cwd=self.root,
                input=json.dumps(
                    {
                        "cwd": str(self.root),
                        "session_id": "discussion-closeout",
                        "tool_name": tool_name,
                        "tool_input": tool_input,
                    }
                ),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            return json.loads(process.stdout)

        self.assertEqual(
            invoke("Edit", {"file_path": str(self.root / "CODEMAP.md")}), {}
        )
        self.assertEqual(
            invoke("Bash", {"command": "python3 -m unittest"}), {}
        )
        denied = invoke(
            "Edit", {"file_path": str(self.root / "src" / "new_feature.py")}
        )
        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_stop_hook_continues_agent_until_closeout(self) -> None:
        self.write("src/app.py", "print('changed')\n")
        process = subprocess.run(
            [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "stop"],
            cwd=self.root,
            input=json.dumps({"cwd": str(self.root), "stop_hook_active": False}),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        payload = json.loads(process.stdout)
        self.assertEqual(payload["decision"], "block")
        self.assertIn("reports/runs", payload["reason"])

    def test_task_completed_uses_blocking_exit_code(self) -> None:
        self.write("src/app.py", "print('changed')\n")
        process = subprocess.run(
            [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "task-completed"],
            cwd=self.root,
            input=json.dumps({"cwd": str(self.root)}),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(process.returncode, 2)
        self.assertIn("reports/runs", process.stderr)

    def test_integration_absorbs_multiple_worker_reports_and_updates_discussion(self) -> None:
        report_paths = ["reports/runs/003-a.md", "reports/runs/004-b.md"]
        self.write("src/a.py", "print('a')\n")
        self.write("src/b.py", "print('b')\n")
        for path in report_paths:
            self.write(path, self.run_report(Path(path).stem))
        self.write("CODEMAP.md", "# Codemap\n\n- src/a.py\n- src/b.py\n")
        self.write("prompts/DISCUSSION_AI.md", self.discussion("integration/003-004"))
        self.write(
            "reports/PROJECT_STATUS.md",
            self.overview(
                report_paths,
                {"CODEMAP.md": ("Updated", "Integrated new source anchors")},
            ),
        )
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertTrue(result.ok, result.errors)

    def test_structured_integration_state_is_canonical_over_legacy_labels(self) -> None:
        report_path = "reports/runs/structured-parallel.md"
        self.write("src/parallel.py", "print('parallel')\n")
        self.write(
            report_path,
            self.structured_run_report(
                "structured-parallel",
                work_type="parallel_batch",
                batch_id="batch-structured",
            ),
        )
        self.write(
            "prompts/DISCUSSION_AI.md",
            self.discussion("integration/structured-parallel"),
        )
        legacy_overview = self.overview(
            [report_path],
            integration_kind="sequential",
            authorization="Inherited task approval",
        )
        integration_state = {
            "schema_version": 1,
            "kind": "integration",
            "integration_id": "integration/structured-parallel",
            "status": "completed",
            "integration_kind": "parallel_batch",
            "authorization": "explicit_user_confirmation",
            "reports": [report_path],
        }
        block = (
            "<!-- wishgraph:integration-state:start -->\n```json\n"
            + json.dumps(integration_state, indent=2)
            + "\n```\n<!-- wishgraph:integration-state:end -->\n\n"
        )
        self.write(
            "reports/PROJECT_STATUS.md",
            legacy_overview.replace(
                "## Current Integration\n\n",
                "## Current Integration\n\n" + block,
                1,
            ),
        )
        task_path = "tasks/build/structured-parallel.md"
        self.write(
            task_path,
            self.structured_task(
                "025-structured-parallel",
                status="completed",
                work_type="parallel_batch",
                batch_id="batch-structured",
                worker_authorized=True,
                integration_policy="requires_explicit_user_confirmation",
                run_report=report_path,
            ),
        )
        stale_task = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertFalse(stale_task.ok)
        self.assertTrue(any("must move task status to integrated" in error for error in stale_task.errors))
        self.write(
            task_path,
            self.structured_task(
                "025-structured-parallel",
                status="integrated",
                work_type="parallel_batch",
                batch_id="batch-structured",
                worker_authorized=True,
                integration_policy="requires_explicit_user_confirmation",
                run_report=report_path,
            ),
        )
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertTrue(result.ok, result.errors)

    def test_integration_requires_discussion_state_update(self) -> None:
        report_path = "reports/runs/005-no-discussion.md"
        self.write("src/new.py", "print('new')\n")
        self.write(report_path, self.run_report("005-no-discussion"))
        self.write("reports/PROJECT_STATUS.md", self.overview([report_path]))
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertFalse(result.ok)
        self.assertTrue(any("discussion" in error.lower() for error in result.errors))

    def test_integration_requires_project_status_update(self) -> None:
        report_path = "reports/runs/005b-no-status.md"
        self.write("src/no_status.py", "print('new')\n")
        self.write(report_path, self.run_report("005b-no-status"))
        self.write("prompts/DISCUSSION_AI.md", self.discussion("integration/005b"))
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertFalse(result.ok)
        self.assertTrue(
            any(
                "must not update shared memory prompts/DISCUSSION_AI.md" in error
                for error in result.errors
            )
        )

    def test_project_status_line_limit_warns_but_enforce_blocks(self) -> None:
        _, status = self.prepare_integration("005c-long-lines")
        self.write(
            "reports/PROJECT_STATUS.md",
            status + "\n" + "\n".join("- historical detail" for _ in range(170)),
        )
        config_path = self.root / ".wishgraph" / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["mode"] = "warn"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        warned = subprocess.run(
            [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "stop"],
            cwd=self.root,
            input=json.dumps({"cwd": str(self.root)}),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        warned_payload = json.loads(warned.stdout)
        self.assertIn("systemMessage", warned_payload)
        self.assertNotIn("decision", warned_payload)
        self.assertIn("reports/runs/*.md", warned_payload["systemMessage"])

        warned_check = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "check",
                "--scope",
                "worktree",
            ],
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        self.assertIn("warn mode does not block", warned_check.stderr)

        config["mode"] = "enforce"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        blocked = subprocess.run(
            [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "stop"],
            cwd=self.root,
            input=json.dumps({"cwd": str(self.root)}),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        blocked_payload = json.loads(blocked.stdout)
        self.assertEqual(blocked_payload["decision"], "block")
        self.assertIn("Do not remove unresolved risks", blocked_payload["reason"])

    def test_project_status_character_limit_is_enforced(self) -> None:
        self.prepare_integration("005d-long-chars")
        config = json.loads(json.dumps(self.config))
        config["project_status_max_chars"] = 100
        result = memory_sync.check_sync(self.root, config, "worktree")
        self.assertFalse(result.ok)
        self.assertTrue(any("characters; limit is 100" in error for error in result.errors))

    def test_discussion_dynamic_block_line_limit_is_enforced(self) -> None:
        self.prepare_integration("005e-long-discussion")
        long_state = "\n".join(f"- line {index}: value" for index in range(31))
        self.write(
            "prompts/DISCUSSION_AI.md",
            "# Discussion\n\n<!-- wishgraph:state:start -->\n"
            + long_state
            + "\n<!-- wishgraph:state:end -->\n",
        )
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertFalse(result.ok)
        self.assertTrue(
            any("dynamic wishgraph:state block exceeds 30 lines" in error for error in result.errors)
        )

    def test_project_status_lists_only_current_integration_reports(self) -> None:
        report_path, _ = self.prepare_integration("005f-current-only")
        self.write(
            "reports/PROJECT_STATUS.md",
            self.overview(["reports/runs/000-bootstrap.md", report_path]),
        )
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertFalse(result.ok)
        self.assertTrue(any("must list only reports absorbed" in error for error in result.errors))

    def test_existing_run_report_is_immutable(self) -> None:
        self.write("reports/runs/000-bootstrap.md", self.run_report("rewritten"))
        self.write("src/app.py", "print('changed')\n")
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertFalse(result.ok)
        self.assertTrue(any("immutable" in error for error in result.errors))

    def test_clean_session_start_is_neutral_by_default(self) -> None:
        process = subprocess.run(
            [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "session-start"],
            cwd=self.root,
            input=json.dumps({"cwd": str(self.root)}),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        self.assertEqual(json.loads(process.stdout), {})

    def test_session_start_can_opt_in_to_discussion_summary(self) -> None:
        self.update_config(session_start_context_mode="discussion_summary")
        process = subprocess.run(
            [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "session-start"],
            cwd=self.root,
            input=json.dumps({"cwd": str(self.root)}),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        payload = json.loads(process.stdout)
        context = payload["hookSpecificOutput"]["additionalContext"]
        self.assertIn("latest worker results integrated", context)
        self.assertIn("Current Discussion Handoff", context)
        self.assertLessEqual(len(context), 2000)

    def test_legacy_dev_report_is_read_with_migration_reminder(self) -> None:
        self.git("mv", "reports/PROJECT_STATUS.md", "reports/DEV_REPORT.md")
        self.git("commit", "-qm", "legacy status fixture")
        config = memory_sync.load_config(self.root)
        assert config is not None
        result = memory_sync.check_sync(self.root, config, "worktree")
        self.assertTrue(result.ok, result.errors)
        self.assertTrue(any("Legacy status file" in warning for warning in result.warnings))

        process = subprocess.run(
            [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "session-start"],
            cwd=self.root,
            input=json.dumps({"cwd": str(self.root)}),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        context = json.loads(process.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Legacy status file reports/DEV_REPORT.md is still in use", context)
        self.assertNotIn("latest worker results integrated", context)
        self.assertIn("开始讨论", context)

    def test_legacy_session_start_boolean_maps_to_explicit_modes(self) -> None:
        path = self.root / ".wishgraph" / "config.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        config.pop("session_start_context_mode")
        config["inject_project_summary_on_session_start"] = True
        path.write_text(json.dumps(config), encoding="utf-8")
        loaded = memory_sync.load_config(self.root)
        assert loaded is not None
        self.assertEqual(loaded["session_start_context_mode"], "discussion_summary")

        config["inject_project_summary_on_session_start"] = False
        path.write_text(json.dumps(config), encoding="utf-8")
        loaded = memory_sync.load_config(self.root)
        assert loaded is not None
        self.assertEqual(loaded["session_start_context_mode"], "safety_only")

    def test_new_session_start_mode_takes_priority_over_legacy_boolean(self) -> None:
        path = self.root / ".wishgraph" / "config.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        config["session_start_context_mode"] = "safety_only"
        config["inject_project_summary_on_session_start"] = True
        path.write_text(json.dumps(config), encoding="utf-8")
        loaded = memory_sync.load_config(self.root)
        assert loaded is not None
        self.assertEqual(loaded["session_start_context_mode"], "safety_only")

    def test_invalid_session_start_context_mode_is_rejected(self) -> None:
        self.update_config(session_start_context_mode="surprise")
        with self.assertRaisesRegex(ValueError, "session_start_context_mode"):
            memory_sync.load_config(self.root)

    def test_both_project_status_files_create_source_conflict(self) -> None:
        old_content = (self.root / "reports" / "PROJECT_STATUS.md").read_text(
            encoding="utf-8"
        )
        self.write("reports/DEV_REPORT.md", old_content)
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertFalse(result.ok)
        self.assertTrue(any("Both reports/PROJECT_STATUS.md" in error for error in result.errors))

    def test_safe_sequential_result_needs_no_second_confirmation(self) -> None:
        self.write("src/app.py", "print('safe sequential')\n")
        report_path = "reports/runs/006-sequential.md"
        self.write(report_path, self.run_report("006-sequential"))
        state = memory_sync.integration_state(self.root, self.config).as_dict()
        self.assertTrue(state["pending_integration"])
        self.assertEqual(state["integration_kind"], "sequential")
        self.assertEqual(state["ready_reports"], [report_path])
        self.assertFalse(state["requires_user_confirmation"])
        self.assertTrue(state["auto_integration_eligible"])
        self.assertEqual(state["next_action"], "auto_integrate")

    def test_host_integration_plan_has_silent_fallback_levels(self) -> None:
        self.write("reports/runs/006a-sequential.md", self.run_report("006a-sequential"))
        expected = {
            "background": "enter_discussion_local_integration",
            "active_agent": "enter_discussion_local_integration",
            "inactive": "persist_integration_pending_until_discussion_resume",
        }
        for capability, action in expected.items():
            with self.subTest(capability=capability):
                process = subprocess.run(
                    [
                        sys.executable,
                        str(HOOK_ASSETS / "memory_sync.py"),
                        "integration-plan",
                        "--host-capability",
                        capability,
                    ],
                    cwd=self.root,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                )
                payload = json.loads(process.stdout)
                self.assertEqual(payload["visibility"], "silent_unless_blocked")
                self.assertEqual(payload["host_action"], action)
                self.assertFalse(payload["creates_visible_integration_window"])

    def test_failed_sequential_result_blocks_integration(self) -> None:
        report_path = "reports/runs/007-failed.md"
        self.write(
            report_path,
            self.run_report(
                "007-failed",
                status="Blocked",
                readiness="Blocked",
                validation="Fail",
                scope_check="Fail",
            ),
        )
        state = memory_sync.integration_state(self.root, self.config).as_dict()
        self.assertEqual(state["blocked_reports"], [report_path])
        self.assertTrue(state["requires_user_confirmation"])
        self.assertFalse(state["auto_integration_eligible"])
        self.assertEqual(state["next_action"], "discuss_blocker")
        self.assertIn("unsafe", state["reason"].lower())

    def test_sequential_safety_failures_block_auto_integration(self) -> None:
        cases = {
            "validation": {"validation": "Fail"},
            "scope": {"scope_check": "Fail"},
            "conflict": {"conflict_status": "Present"},
            "decision": {"new_decision": "Yes"},
        }
        for index, (name, overrides) in enumerate(cases.items(), start=20):
            with self.subTest(case=name):
                report_path = f"reports/runs/{index}-{name}.md"
                self.write(report_path, self.run_report(f"{index}-{name}", **overrides))
                state = memory_sync.integration_state(self.root, self.config).as_dict()
                self.assertIn(report_path, state["blocked_reports"])
                report_path_on_disk = self.root / report_path
                report_path_on_disk.unlink()

    def test_parallel_integration_requires_explicit_user_confirmation(self) -> None:
        report_path = "reports/runs/008-parallel.md"
        self.write("src/parallel.py", "print('parallel')\n")
        self.write(
            report_path,
            self.run_report(
                "008-parallel",
                work_type="parallel_batch",
                batch_id="batch-008",
            ),
        )
        self.write("prompts/DISCUSSION_AI.md", self.discussion("integration/008"))
        self.write(
            "reports/PROJECT_STATUS.md",
            self.overview(
                [report_path],
                integration_kind="parallel_batch",
                authorization="Inherited task approval",
            ),
        )
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertFalse(result.ok)
        self.assertTrue(
            any("explicit user confirmation" in error for error in result.errors)
        )

    def test_high_risk_result_is_ready_but_requires_explicit_integration(self) -> None:
        report_path = "reports/runs/008b-high-risk.md"
        self.write(
            report_path,
            self.structured_run_report(
                "008b-high-risk",
                work_type="high_risk",
            ),
        )
        state = memory_sync.integration_state(self.root, self.config).as_dict()
        self.assertEqual(state["integration_kind"], "high_risk")
        self.assertEqual(state["ready_reports"], [report_path])
        self.assertEqual(state["blocked_reports"], [])
        self.assertTrue(state["requires_user_confirmation"])
        self.assertFalse(state["auto_integration_eligible"])
        self.assertEqual(state["next_action"], "await_user_confirmation")

    def test_parallel_independent_results_can_auto_integrate_when_risk_is_clear(self) -> None:
        for task_id, changed_path in (("031", "src/one.py"), ("032", "src/two.py")):
            report_path = f"reports/runs/{task_id}-attempt-1.md"
            self.write(
                f"tasks/build/{task_id}-independent.md",
                self.structured_task(
                    f"{task_id}-independent",
                    status="completed",
                    work_type="parallel_batch",
                    batch_id="batch-independent",
                    worker_authorized=True,
                    execution_mode="parallel_independent",
                    run_report=report_path,
                ),
            )
            self.write(
                report_path,
                self.structured_run_report(
                    f"{task_id}-attempt-1",
                    work_type="parallel_batch",
                    batch_id="batch-independent",
                    execution_mode="parallel_independent",
                    changed_paths=[changed_path],
                ),
            )
        state = memory_sync.integration_state(self.root, self.config).as_dict()
        self.assertTrue(state["auto_integration_eligible"])
        self.assertEqual(state["next_action"], "auto_integrate")
        self.assertFalse(state["requires_user_confirmation"])

    def test_parallel_overlap_or_risk_returns_to_user(self) -> None:
        for task_id, security_impact in (("033", False), ("034", True)):
            report_path = f"reports/runs/{task_id}-attempt-1.md"
            self.write(
                f"tasks/build/{task_id}-parallel.md",
                self.structured_task(
                    f"{task_id}-parallel",
                    status="completed",
                    work_type="parallel_batch",
                    batch_id="batch-risk",
                    worker_authorized=True,
                    execution_mode="parallel_independent",
                    run_report=report_path,
                ),
            )
            self.write(
                report_path,
                self.structured_run_report(
                    f"{task_id}-attempt-1",
                    work_type="parallel_batch",
                    batch_id="batch-risk",
                    execution_mode="parallel_independent",
                    changed_paths=["src/shared.py"],
                    security_impact=security_impact,
                ),
            )
        state = memory_sync.integration_state(self.root, self.config).as_dict()
        self.assertFalse(state["auto_integration_eligible"])
        self.assertEqual(state["next_action"], "await_user_confirmation")
        self.assertTrue(state["requires_user_confirmation"])

    def test_safe_micro_change_is_auto_eligible_but_still_uses_run_report(self) -> None:
        report_path = "reports/runs/ad-hoc-20260714-copy.md"
        self.write(
            report_path,
            self.structured_run_report(
                "ad-hoc-20260714-copy",
                change_class="micro",
                changed_paths=["src/copy.py"],
            ),
        )
        state = memory_sync.integration_state(self.root, self.config).as_dict()
        self.assertEqual(state["ready_reports"], [report_path])
        self.assertTrue(state["auto_integration_eligible"])
        self.assertEqual(state["selected_reports"], [report_path])

    def test_micro_with_api_schema_security_or_dependency_change_is_blocked(self) -> None:
        flags = (
            "public_api_change",
            "schema_change",
            "security_impact",
            "dependency_change",
        )
        for flag in flags:
            with self.subTest(flag=flag):
                report_path = f"reports/runs/ad-hoc-{flag}.md"
                kwargs = {flag: True}
                self.write(
                    report_path,
                    self.structured_run_report(
                        f"ad-hoc-{flag}",
                        change_class="micro",
                        changed_paths=[f"src/{flag}.py"],
                        **kwargs,
                    ),
                )
                state = memory_sync.integration_state(self.root, self.config).as_dict()
                self.assertIn(report_path, state["blocked_reports"])
                self.assertFalse(state["auto_integration_eligible"])
                (self.root / report_path).unlink()

    def test_formal_task_cannot_hide_unrelated_ad_hoc_micro_report(self) -> None:
        task_path = "tasks/build/035-formal.md"
        report_path = "reports/runs/035-attempt-1.md"
        self.write(
            task_path,
            self.structured_task(
                "035-formal",
                status="completed",
                worker_authorized=True,
                run_report=report_path,
            ),
        )
        self.write(
            report_path,
            self.structured_run_report(
                "035-attempt-1",
                task_id="035",
                change_class="micro",
                changed_paths=["src/unrelated.py"],
            ),
        )
        state = memory_sync.integration_state(self.root, self.config).as_dict()
        self.assertIn(report_path, state["blocked_reports"])

    def test_objective_competitive_score_selects_exactly_one_winner(self) -> None:
        self.write("tasks/build/040-root.md", self.structured_task("040-root"))
        for task_id, score in (("040a", 91.0), ("040b", 87.0)):
            report_path = f"reports/runs/{task_id}-attempt-1.md"
            self.write(
                f"tasks/build/{task_id}-candidate.md",
                self.structured_task(
                    f"{task_id}-candidate",
                    parent_task_id="040",
                    status="completed",
                    work_type="parallel_batch",
                    batch_id="compare-040",
                    worker_authorized=True,
                    execution_mode="competitive",
                    comparison_group="040",
                    run_report=report_path,
                ),
            )
            self.write(
                report_path,
                self.structured_run_report(
                    f"{task_id}-attempt-1",
                    task_id=task_id,
                    work_type="parallel_batch",
                    batch_id="compare-040",
                    execution_mode="competitive",
                    changed_paths=[f"src/{task_id}.py"],
                    candidate_score=score,
                ),
            )
        state = memory_sync.integration_state(self.root, self.config).as_dict()
        self.assertTrue(state["auto_integration_eligible"])
        self.assertEqual(state["next_action"], "auto_integrate")
        self.assertEqual(state["selected_reports"], ["reports/runs/040a-attempt-1.md"])
        self.assertEqual(state["superseded_reports"], ["reports/runs/040b-attempt-1.md"])

    def test_subjective_competitive_choice_returns_to_discussion(self) -> None:
        self.write("tasks/build/041-root.md", self.structured_task("041-root"))
        for task_id in ("041a", "041b"):
            report_path = f"reports/runs/{task_id}-attempt-1.md"
            self.write(
                f"tasks/build/{task_id}-candidate.md",
                self.structured_task(
                    f"{task_id}-candidate",
                    parent_task_id="041",
                    status="completed",
                    work_type="parallel_batch",
                    batch_id="compare-041",
                    worker_authorized=True,
                    execution_mode="competitive",
                    comparison_group="041",
                    run_report=report_path,
                ),
            )
            self.write(
                report_path,
                self.structured_run_report(
                    f"{task_id}-attempt-1",
                    task_id=task_id,
                    work_type="parallel_batch",
                    batch_id="compare-041",
                    execution_mode="competitive",
                    changed_paths=[f"src/{task_id}.py"],
                    candidate_score=90.0,
                    selection_requires_judgment=True,
                ),
            )
        state = memory_sync.integration_state(self.root, self.config).as_dict()
        self.assertFalse(state["auto_integration_eligible"])
        self.assertEqual(state["next_action"], "compare_candidates")
        self.assertTrue(state["requires_user_confirmation"])

    def test_parallel_status_lists_ready_waiting_and_blocked(self) -> None:
        ready_path = "reports/runs/009-ready.md"
        blocked_path = "reports/runs/010-blocked.md"
        waiting_path = "reports/runs/011-waiting.md"
        self.write(
            ready_path,
            self.run_report(
                "009-ready", work_type="parallel_batch", batch_id="batch-009"
            ),
        )
        self.write(
            blocked_path,
            self.run_report(
                "010-blocked",
                work_type="parallel_batch",
                batch_id="batch-009",
                status="Blocked",
                readiness="Blocked",
                validation="Fail",
            ),
        )
        self.write(
            "tasks/build/011-waiting.md",
            "# 011\n\nStatus: Pending\n"
            f"Run report: `{waiting_path}`\n"
            "Work type: parallel_batch\nBatch ID: batch-009\n",
        )
        state = memory_sync.integration_state(self.root, self.config).as_dict()
        self.assertEqual(state["integration_kind"], "parallel_batch")
        self.assertEqual(state["ready_reports"], [ready_path])
        self.assertEqual(state["waiting_reports"], [waiting_path])
        self.assertEqual(state["blocked_reports"], [blocked_path])
        self.assertTrue(state["requires_user_confirmation"])

    def test_status_discovers_completed_worker_on_separate_branch(self) -> None:
        original_branch = self.git("branch", "--show-current").stdout.strip()
        report_path = "reports/runs/013-branch-worker.md"
        self.write(
            "tasks/build/013-branch-worker.md",
            "# 013\n\nStatus: Pending\n"
            f"Run report: `{report_path}`\n"
            "Work type: sequential\nBatch ID: N/A\n",
        )
        self.git("add", "tasks/build/013-branch-worker.md")
        self.git("commit", "-qm", "plan worker")
        self.git("checkout", "-qb", "worker-013")
        self.write(report_path, self.run_report("013-branch-worker"))
        self.git("add", report_path)
        self.git("commit", "-qm", "complete worker")
        self.git("checkout", "-q", original_branch)

        state = memory_sync.integration_state(self.root, self.config).as_dict()
        self.assertEqual(state["ready_reports"], [report_path])
        self.assertEqual(state["waiting_reports"], [])
        self.assertFalse(state["requires_user_confirmation"])

    def test_status_keeps_legacy_hidden_task_path_compatible(self) -> None:
        report_path = "reports/runs/014-legacy-waiting.md"
        self.write(
            ".tasks/build/014-legacy-waiting.md",
            "# 014\n\nStatus: Pending\n"
            f"Run report: `{report_path}`\n"
            "Work type: sequential\nBatch ID: N/A\n",
        )
        state = memory_sync.integration_state(self.root, self.config).as_dict()
        self.assertEqual(state["waiting_reports"], [report_path])

    def test_status_command_is_read_only(self) -> None:
        before = self.git("status", "--porcelain").stdout
        process = subprocess.run(
            [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "status"],
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        payload = json.loads(process.stdout)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["kind"], "integration_status")
        self.assertIn("pending_integration", payload)
        after = self.git("status", "--porcelain").stdout
        self.assertEqual(before, after)

    def test_status_joins_task_run_and_integration_lifecycle(self) -> None:
        task_id = "024-status-join"
        report_path = f"reports/runs/{task_id}.md"
        self.write(
            f"tasks/build/{task_id}.md",
            self.structured_task(
                task_id, status="approved", worker_authorized=True
            ),
        )
        planned = memory_sync.integration_state(self.root, self.config).as_dict()
        unit = next(item for item in planned["work_units"] if item["task_id"] == "024")
        self.assertEqual(unit["lifecycle_status"], "approved")
        self.assertEqual(unit["task_id"], "024")
        self.assertIn(report_path, planned["waiting_reports"])

        self.write(report_path, self.structured_run_report(task_id))
        completed = memory_sync.integration_state(self.root, self.config).as_dict()
        unit = next(item for item in completed["work_units"] if item["task_id"] == "024")
        self.assertEqual(unit["lifecycle_status"], "completed")

    def test_session_start_injects_pending_integration_status(self) -> None:
        self.write("src/app.py", "print('pending')\n")
        self.write("reports/runs/012-pending.md", self.run_report("012-pending"))
        self.update_config(session_start_context_mode="discussion_summary")
        process = subprocess.run(
            [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "session-start"],
            cwd=self.root,
            input=json.dumps({"cwd": str(self.root)}),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        context = json.loads(process.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn('"pending_integration":true', context)
        self.assertIn('"integration_kind":"sequential"', context)

    def test_user_prompt_submit_routes_discussion_refresh_and_exact_task(self) -> None:
        task_path = "tasks/build/012-route.md"
        self.write(
            task_path,
            self.execution_ready_task(
                "012-route", status="approved", worker_authorized=True
            ),
        )
        start = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "user-prompt-submit",
                "--host",
                "codex",
            ],
            cwd=self.root,
            input=json.dumps(
                {
                    "cwd": str(self.root),
                    "session_id": "discussion-route",
                    "prompt": "请进入讨论模式。",
                }
            ),
            text=True,
            stdout=subprocess.PIPE,
            check=True,
        )
        self.assertIn("WishGraph project update", json.loads(start.stdout)["hookSpecificOutput"]["additionalContext"])
        runtime = memory_sync.read_session_runtime(self.root, "discussion-route")
        self.assertEqual(runtime["session"]["role"], "discussion")

        route = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "user-prompt-submit",
                "--host",
                "codex",
            ],
            cwd=self.root,
            input=json.dumps(
                {"cwd": str(self.root), "session_id": "neutral-route", "prompt": "执行 012 号任务！"}
            ),
            text=True,
            stdout=subprocess.PIPE,
            check=True,
        )
        context = json.loads(route.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn('"host_action":"enter_current_window_as_worker"', context)
        self.assertIn('"task_id":"012"', context)

        memory_sync.apply_session_runtime_patch(
            self.root,
            "discussion-route",
            {
                "session": {
                    "expected_transition": {
                        "kind": "approve_worker_launch",
                        "task_id": "012",
                    }
                }
            },
        )
        subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "user-prompt-submit",
                "--host",
                "codex",
            ],
            cwd=self.root,
            input=json.dumps(
                {
                    "cwd": str(self.root),
                    "session_id": "discussion-route",
                    "prompt": "麻烦刷新一下项目状态，谢谢！",
                }
            ),
            text=True,
            stdout=subprocess.PIPE,
            check=True,
        )
        refreshed = memory_sync.read_session_runtime(self.root, "discussion-route")
        self.assertEqual(
            refreshed["session"]["expected_transition"]["kind"],
            "approve_worker_launch",
        )

    def test_active_status_is_compact_and_full_status_keeps_history(self) -> None:
        for task_id, status in (("041", "integrated"), ("042", "approved")):
            self.write(
                f"tasks/build/{task_id}-status.md",
                self.structured_task(
                    task_id,
                    status=status,
                    worker_authorized=True,
                ),
            )
        policy_module = sys.modules["policy"]
        with mock.patch.object(
            policy_module,
            "report_contents_across_refs",
            side_effect=AssertionError("active status scanned historical report trees"),
        ):
            active = memory_sync.integration_state(
                self.root, self.config, view="active"
            ).as_dict()
        self.assertEqual(active["view"], "active")
        self.assertEqual([unit["task_id"] for unit in active["work_units"]], ["042"])
        full = memory_sync.integration_state(
            self.root, self.config, view="full"
        ).as_dict()
        self.assertIn("041", [unit["task_id"] for unit in full["work_units"]])
        exact = memory_sync.integration_state(
            self.root, self.config, view="active", task_id="041"
        ).as_dict()
        self.assertEqual(exact["task_filter"], "041")
        self.assertEqual([unit["task_id"] for unit in exact["work_units"]], ["041"])
        cli_full = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "status",
                "--full",
            ],
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            check=True,
        )
        self.assertEqual(json.loads(cli_full.stdout)["view"], "full")
        cli_task = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "status",
                "--task",
                "041",
            ],
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            check=True,
        )
        self.assertEqual(json.loads(cli_task.stdout)["task_filter"], "041")

    def test_run_report_integrate_proposal_cannot_be_dropped_by_project_status(self) -> None:
        report_path = "reports/runs/043-semantic-sync.md"
        self.write("src/semantic.py", "print('detail changed')\n")
        self.write(
            report_path,
            self.run_report(
                "043-semantic-sync",
                {"PRD.md": ("Integrate", "The visible product decision changed")},
            ),
        )
        self.write("prompts/DISCUSSION_AI.md", self.discussion("integration/043"))
        self.write("reports/PROJECT_STATUS.md", self.overview([report_path]))
        rejected = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertFalse(rejected.ok)
        self.assertTrue(
            any("Run Report marked it Integrate" in error for error in rejected.errors),
            rejected.errors,
        )

        self.write("PRD.md", "# PRD\n\n- Decision: updated detail\n")
        self.write(
            "reports/PROJECT_STATUS.md",
            self.overview(
                [report_path],
                {"PRD.md": ("Updated", "Applied the changed product decision")},
            ),
        )
        accepted = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertTrue(accepted.ok, accepted.errors)

    def test_claim_platform_prevents_cross_host_worker_reuse(self) -> None:
        self.write(
            "tasks/build/012-parent.md",
            self.structured_task("012", status="completed", worker_authorized=True),
        )
        self.write(
            "tasks/revisions/012-r1.md",
            (HOOK_ASSETS.parent / "templates" / "TASK_REVISION.md").read_text(encoding="utf-8"),
        )
        claim = memory_sync.acquire_claim(
            self.root,
            "012",
            1,
            "claude-worker",
            host_thread_ref="claude-session-012",
            agent_platform="claude",
            require_clean=False,
        )
        self.assertEqual(claim["claim"]["agent_platform"], "claude")
        memory_sync.update_claim(self.root, claim["claim"]["claim_id"], "release")
        routed = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "revision",
                "route",
                "012-r1",
                "--host",
                "codex",
            ],
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            check=True,
        )
        action = json.loads(routed.stdout)["host_action"]
        self.assertEqual(action["action"], "launch_codex_revision_worker")
        self.assertNotIn("target_worker_id", action)

    def test_next_revision_reuses_one_open_record_before_allocating_another(self) -> None:
        self.write(
            "tasks/build/012-parent.md",
            self.structured_task("012", status="completed", worker_authorized=True),
        )
        template = (HOOK_ASSETS.parent / "templates" / "TASK_REVISION.md").read_text(encoding="utf-8")
        self.write("tasks/revisions/012-r1.md", template)
        reused = memory_sync.next_revision_id(self.root, self.config, "012")
        self.assertTrue(reused["reuse_open_revision"])
        self.assertEqual(reused["revision_id"], "012-r1")
        self.write(
            "tasks/revisions/012-r1.md",
            template.replace('"status": "pending"', '"status": "integrated"'),
        )
        allocated = memory_sync.next_revision_id(self.root, self.config, "012")
        self.assertFalse(allocated["reuse_open_revision"])
        self.assertEqual(allocated["revision_id"], "012-r2")


class InstallerTests(unittest.TestCase):
    def install_project_runtime(self, root: Path, *, mode: str = "warn") -> None:
        process = subprocess.run(
            [
                sys.executable,
                str(INSTALLER),
                "--target",
                str(root),
                "--host",
                "codex",
                "--mode",
                mode,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(process.returncode, 0, process.stderr)

    def mark_runtime_as_generated_version(self, root: Path, version: int) -> None:
        hook_dir = root / ".wishgraph" / "hooks"
        workflow = hook_dir / "workflow_state.py"
        workflow.write_text("# generated WishGraph runtime fixture\n", encoding="utf-8")
        files = {
            name: installer_module.sha256_file(hook_dir / name)
            for name in installer_module.RUNTIME_FILES
        }
        (hook_dir / "runtime-manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "runtime_version": version,
                    "files": files,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        config_path = root / ".wishgraph" / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["runtime_version"] = version
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    def test_doctor_is_read_only_for_an_unconfigured_project(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            before = subprocess.run(
                ["git", "-C", str(root), "status", "--porcelain"],
                text=True,
                stdout=subprocess.PIPE,
                check=True,
            ).stdout
            process = subprocess.run(
                [
                    sys.executable,
                    str(INSTALLER),
                    "--target",
                    str(root),
                    "--host",
                    "codex",
                    "--doctor",
                    "--json",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            payload = json.loads(process.stdout)
            self.assertEqual(payload["kind"], "wishgraph_doctor")
            self.assertEqual(payload["activation"]["state"], "missing")
            self.assertEqual(payload["runtime"]["state"], "missing")
            self.assertEqual(payload["host_adapters"]["codex"]["state"], "missing")
            self.assertEqual(payload["next_action"], "use_wishgraph")
            after = subprocess.run(
                ["git", "-C", str(root), "status", "--porcelain"],
                text=True,
                stdout=subprocess.PIPE,
                check=True,
            ).stdout
            self.assertEqual(after, before)
            self.assertFalse((root / ".wishgraph").exists())

    def test_runtime_manifest_accepts_windows_crlf_without_masking_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            asset_root = Path(tempdir) / "hooks"
            shutil.copytree(HOOK_ASSETS, asset_root)
            for name in installer_module.RUNTIME_FILES:
                path = asset_root / name
                lf_data = path.read_bytes().replace(b"\r\n", b"\n")
                path.write_bytes(lf_data.replace(b"\n", b"\r\n"))

            with mock.patch.object(installer_module, "ASSET_ROOT", asset_root):
                manifest = installer_module.bundled_runtime_manifest()
                self.assertEqual(manifest["runtime_version"], 16)

                policy_path = asset_root / "policy.py"
                policy_path.write_bytes(policy_path.read_bytes() + b"# changed\r\n")
                with self.assertRaisesRegex(
                    ValueError, "do not match runtime-manifest"
                ):
                    installer_module.bundled_runtime_manifest()

    def test_doctor_reports_a_current_installed_host(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            installed = subprocess.run(
                [
                    sys.executable,
                    str(INSTALLER),
                    "--target",
                    str(root),
                    "--host",
                    "codex",
                    "--mode",
                    "warn",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(installed.returncode, 0, installed.stderr)
            process = subprocess.run(
                [
                    sys.executable,
                    str(INSTALLER),
                    "--target",
                    str(root),
                    "--host",
                    "codex",
                    "--doctor",
                    "--json",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            payload = json.loads(process.stdout)
            self.assertTrue(payload["healthy"])
            self.assertEqual(payload["activation"]["state"], "active")
            self.assertEqual(payload["runtime"]["state"], "current")
            self.assertEqual(payload["python"]["state"], "available")
            self.assertEqual(payload["host_adapters"]["codex"]["state"], "current")
            self.assertEqual(
                payload["host_adapters"]["codex"]["execution"]["state"],
                "unverified",
            )
            self.assertFalse(payload["host_execution_confirmed"])
            self.assertEqual(payload["next_action"], "restart_agent_session")

    def test_doctor_confirms_a_recent_real_host_hook_invocation(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            self.install_project_runtime(root)
            hook = root / ".wishgraph" / "hooks" / "memory_sync.py"
            invoked = subprocess.run(
                [sys.executable, str(hook), "session-start", "--host", "codex"],
                cwd=root,
                input=json.dumps({"cwd": str(root), "session_id": "codex-live"}),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(invoked.returncode, 0, invoked.stderr)

            process = subprocess.run(
                [
                    sys.executable,
                    str(INSTALLER),
                    "--target",
                    str(root),
                    "--host",
                    "codex",
                    "--doctor",
                    "--json",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            payload = json.loads(process.stdout)
            execution = payload["host_adapters"]["codex"]["execution"]
            self.assertEqual(execution["state"], "confirmed_recently")
            self.assertEqual(execution["last_event"], "session-start")
            self.assertEqual(execution["observed_runtime_version"], 16)
            self.assertTrue(payload["host_execution_confirmed"])
            self.assertEqual(payload["next_action"], "bootstrap_project_memory")

    def test_doctor_routes_unverified_claude_cli_to_claude_doctor(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            installed = subprocess.run(
                [
                    sys.executable,
                    str(INSTALLER),
                    "--target",
                    str(root),
                    "--host",
                    "claude",
                    "--mode",
                    "warn",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(installed.returncode, 0, installed.stderr)

            payload = installer_module.doctor_report(root, "claude")
            execution = payload["host_adapters"]["claude"]["execution"]
            self.assertEqual(
                payload["host_adapters"]["claude"]["worker_agent"]["state"],
                "current",
            )
            self.assertTrue(
                (root / ".claude" / "agents" / "wishgraph-worker.md").is_file()
            )
            claude_settings = json.loads(
                (root / ".claude" / "settings.json").read_text(encoding="utf-8")
            )
            self.assertIn(
                ".wishgraph",
                claude_settings["worktree"]["symlinkDirectories"],
            )
            self.assertEqual(execution["state"], "unverified")
            self.assertEqual(execution["troubleshooting"], "claude doctor")
            self.assertEqual(payload["next_action"], "restart_agent_session")

    def test_doctor_marks_observation_stale_after_host_adapter_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            self.install_project_runtime(root)
            hook = root / ".wishgraph" / "hooks" / "memory_sync.py"
            subprocess.run(
                [
                    sys.executable,
                    str(hook),
                    "user-prompt-submit",
                    "--host",
                    "codex",
                ],
                cwd=root,
                input=json.dumps(
                    {
                        "cwd": str(root),
                        "session_id": "codex-live",
                        "prompt": "检查 WishGraph 状态",
                    }
                ),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            adapter_path = root / ".codex" / "hooks.json"
            future = datetime.now().timestamp() + 10
            os.utime(adapter_path, (future, future))

            payload = installer_module.doctor_report(root, "codex")
            execution = payload["host_adapters"]["codex"]["execution"]
            self.assertEqual(execution["state"], "stale")
            self.assertFalse(payload["host_execution_confirmed"])
            self.assertEqual(payload["next_action"], "restart_agent_session")

    def test_pre_tool_use_does_not_write_host_observation(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            self.install_project_runtime(root)
            hook = root / ".wishgraph" / "hooks" / "memory_sync.py"
            process = subprocess.run(
                [sys.executable, str(hook), "pre-tool-use", "--host", "codex"],
                cwd=root,
                input=json.dumps(
                    {
                        "cwd": str(root),
                        "session_id": "codex-live",
                        "tool_name": "Bash",
                        "tool_input": {"command": "pwd"},
                    }
                ),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            common_dir = Path(
                subprocess.run(
                    ["git", "-C", str(root), "rev-parse", "--git-common-dir"],
                    text=True,
                    stdout=subprocess.PIPE,
                    check=True,
                ).stdout.strip()
            )
            if not common_dir.is_absolute():
                common_dir = root / common_dir
            self.assertFalse(
                (common_dir / "wishgraph" / "host-observations").exists()
            )

    def test_safe_upgrade_repairs_current_runtime_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            self.install_project_runtime(root, mode="enforce")
            (root / ".wishgraph" / "hooks" / "runtime-manifest.json").unlink()
            config_path = root / ".wishgraph" / "config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["runtime_version"] = 11
            config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

            before = subprocess.run(
                [
                    sys.executable,
                    str(INSTALLER),
                    "--target",
                    str(root),
                    "--host",
                    "codex",
                    "--doctor",
                    "--json",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            before_payload = json.loads(before.stdout)
            self.assertEqual(before_payload["runtime"]["state"], "metadata_missing")
            self.assertTrue(before_payload["runtime"]["safe_to_upgrade"])

            upgraded = subprocess.run(
                [
                    sys.executable,
                    str(INSTALLER),
                    "--target",
                    str(root),
                    "--upgrade",
                    "--json",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(upgraded.returncode, 0, upgraded.stderr)
            payload = json.loads(upgraded.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["after"]["state"], "current")
            self.assertEqual(payload["after"]["installed_runtime_version"], 16)
            config = json.loads(
                (root / ".wishgraph" / "config.json").read_text(encoding="utf-8")
            )
            self.assertEqual(config["mode"], "enforce")
            self.assertEqual(config["runtime_version"], 16)

    def test_safe_upgrade_replaces_only_a_bundled_known_old_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            self.install_project_runtime(root)
            self.mark_runtime_as_generated_version(root, 11)
            untrusted = installer_module.runtime_diagnosis(root)
            self.assertEqual(untrusted["state"], "modified")
            self.assertFalse(untrusted["safe_to_upgrade"])
            actual = installer_module.installed_runtime_hashes(root)
            manifest = json.loads(
                json.dumps(installer_module.bundled_runtime_manifest())
            )
            manifest.setdefault("known_versions", {})["11"] = actual

            with mock.patch.object(
                installer_module,
                "bundled_runtime_manifest",
                return_value=manifest,
            ):
                before = installer_module.runtime_diagnosis(root)
                self.assertEqual(before["state"], "upgrade_available")
                self.assertTrue(before["safe_to_upgrade"])
                installer_module.install_runtime(root, "warn", False, upgrade=True)

            self.assertEqual(installer_module.runtime_diagnosis(root)["state"], "current")

    def test_upgrade_preserves_a_locally_modified_runtime_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            self.install_project_runtime(root)
            policy_path = root / ".wishgraph" / "hooks" / "policy.py"
            policy_path.write_text(
                policy_path.read_text(encoding="utf-8") + "# local customization\n",
                encoding="utf-8",
            )
            before = policy_path.read_bytes()

            process = subprocess.run(
                [
                    sys.executable,
                    str(INSTALLER),
                    "--target",
                    str(root),
                    "--upgrade",
                    "--json",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(process.returncode, 4)
            payload = json.loads(process.stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["before"]["state"], "modified")
            self.assertEqual(policy_path.read_bytes(), before)

    def test_upgrade_rolls_back_all_runtime_files_after_an_interrupted_write(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            self.install_project_runtime(root)
            self.mark_runtime_as_generated_version(root, 11)
            tracked = installer_module.runtime_target_paths(root)
            before = {
                path: (path.exists(), path.read_bytes() if path.exists() else b"")
                for path in tracked
            }
            original_write = installer_module.write_bytes_atomic
            failure_injected = False

            def fail_once(path, data, mode=None):
                nonlocal failure_injected
                if path.name == "workflow_state.py" and not failure_injected:
                    failure_injected = True
                    raise OSError("injected write interruption")
                return original_write(path, data, mode)

            with mock.patch.object(
                installer_module, "write_bytes_atomic", side_effect=fail_once
            ):
                with self.assertRaisesRegex(OSError, "injected write interruption"):
                    installer_module.install_runtime(
                        root, "warn", True, upgrade=True
                    )

            after = {
                path: (path.exists(), path.read_bytes() if path.exists() else b"")
                for path in tracked
            }
            self.assertEqual(after, before)

    def test_host_repair_updates_only_selected_host_and_preserves_other_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            self.install_project_runtime(root)
            codex_path = root / ".codex" / "hooks.json"
            codex_before = codex_path.read_bytes()
            claude_path = root / ".claude" / "settings.json"
            claude_path.parent.mkdir()
            claude_path.write_text(
                json.dumps(
                    {
                        "worktree": {"symlinkDirectories": ["node_modules"]},
                        "hooks": {
                            "Stop": [
                                {
                                    "hooks": [
                                        {"type": "command", "command": "echo keep-me"},
                                        {
                                            "type": "command",
                                            "command": "python3 .wishgraph/hooks/memory_sync.py old-hook",
                                        },
                                    ]
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )

            process = subprocess.run(
                [
                    sys.executable,
                    str(INSTALLER),
                    "--target",
                    str(root),
                    "--host",
                    "claude",
                    "--repair-host-adapter",
                    "--json",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            payload = json.loads(process.stdout)
            self.assertEqual(payload["host"], "claude")
            self.assertEqual(payload["before"]["state"], "outdated")
            self.assertEqual(payload["after"]["state"], "current")
            self.assertEqual(codex_path.read_bytes(), codex_before)
            merged = json.loads(claude_path.read_text(encoding="utf-8"))
            stop_commands = [
                hook.get("command", "")
                for group in merged["hooks"]["Stop"]
                for hook in group.get("hooks", [])
            ]
            self.assertIn("echo keep-me", stop_commands)
            self.assertFalse(any("old-hook" in command for command in stop_commands))
            self.assertEqual(
                merged["worktree"]["symlinkDirectories"],
                ["node_modules", ".wishgraph"],
            )
            self.assertEqual(merged["worktree"]["baseRef"], "head")
            self.assertTrue(
                (root / ".claude" / "agents" / "wishgraph-worker.md").is_file()
            )

            before_rerun = claude_path.read_bytes()
            rerun = subprocess.run(
                [
                    sys.executable,
                    str(INSTALLER),
                    "--target",
                    str(root),
                    "--host",
                    "claude",
                    "--repair-host-adapter",
                    "--json",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            self.assertEqual(json.loads(rerun.stdout)["changed"], [])
            self.assertEqual(claude_path.read_bytes(), before_rerun)

    def test_host_repair_requires_one_explicit_current_host(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            self.install_project_runtime(root)
            codex_before = (root / ".codex" / "hooks.json").read_bytes()
            process = subprocess.run(
                [
                    sys.executable,
                    str(INSTALLER),
                    "--target",
                    str(root),
                    "--host",
                    "all",
                    "--repair-host-adapter",
                    "--json",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(process.returncode, 2)
            self.assertFalse(json.loads(process.stdout)["ok"])
            self.assertEqual((root / ".codex" / "hooks.json").read_bytes(), codex_before)
            self.assertFalse((root / ".claude").exists())

    def test_installer_rejects_non_git_directory_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            process = subprocess.run(
                [sys.executable, str(INSTALLER), "--target", str(root)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(process.returncode, 3)
            self.assertIn("git init", process.stderr)
            self.assertIn("under a second", process.stderr)
            self.assertFalse((root / ".wishgraph").exists())

    def test_installer_uses_detected_repository_root(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            nested = root / "nested" / "project"
            nested.mkdir(parents=True)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            process = subprocess.run(
                [
                    sys.executable,
                    str(INSTALLER),
                    "--target",
                    str(nested),
                    "--host",
                    "codex",
                    "--mode",
                    "warn",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertIn("Using detected Git repository root", process.stdout)
            self.assertTrue((root / ".codex" / "hooks.json").exists())
            self.assertFalse((nested / ".codex").exists())

    def test_installer_merges_existing_codex_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            existing = {
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "startup",
                            "hooks": [{"type": "command", "command": "echo existing"}],
                        }
                    ]
                }
            }
            (root / ".codex").mkdir()
            (root / ".codex" / "hooks.json").write_text(
                json.dumps(existing), encoding="utf-8"
            )
            (root / ".wishgraph").mkdir()
            (root / ".wishgraph" / "config.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "mode": "enforce",
                        "required_impact_rows": ["PRD.md"],
                    }
                ),
                encoding="utf-8",
            )
            process = subprocess.run(
                [
                    sys.executable,
                    str(INSTALLER),
                    "--target",
                    str(root),
                    "--host",
                    "codex",
                    "--mode",
                    "warn",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            merged = json.loads((root / ".codex" / "hooks.json").read_text())
            commands = [
                hook["command"]
                for group in merged["hooks"]["SessionStart"]
                for hook in group["hooks"]
            ]
            self.assertIn("echo existing", commands)
            self.assertTrue(any("memory_sync.py" in command for command in commands))
            wishgraph_commands = [
                command for command in commands if "memory_sync.py" in command
            ]
            self.assertTrue(
                all(str(Path(sys.executable).resolve()) in command for command in wishgraph_commands)
            )
            for runtime_name in (
                "memory_sync.py",
                "git_state.py",
                "workflow_state.py",
                "policy.py",
                "host_adapter.py",
                "codex_worker_provider.py",
            ):
                self.assertTrue((root / ".wishgraph" / "hooks" / runtime_name).exists())
            status = subprocess.run(
                [
                    sys.executable,
                    str(root / ".wishgraph" / "hooks" / "memory_sync.py"),
                    "status",
                ],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertEqual(json.loads(status.stdout)["kind"], "integration_status")
            config = json.loads((root / ".wishgraph" / "config.json").read_text())
            self.assertEqual(config["mode"], "warn")
            self.assertEqual(config["version"], 11)
            self.assertEqual(config["runtime_version"], 16)
            self.assertTrue(
                (root / ".wishgraph" / "hooks" / "runtime-manifest.json").is_file()
            )
            codex_agent = root / ".codex" / "agents" / "wishgraph-worker.toml"
            self.assertTrue(codex_agent.is_file())
            self.assertIn(
                'name = "wishgraph-worker"',
                codex_agent.read_text(encoding="utf-8"),
            )
            self.assertEqual(config["session_start_context_mode"], "safety_only")
            self.assertEqual(
                config["python_executable"], str(Path(sys.executable).resolve())
            )
            self.assertEqual(config["paths"]["run_report_glob"], "reports/runs/*.md")
            self.assertEqual(
                config["paths"]["project_status"], "reports/PROJECT_STATUS.md"
            )
            self.assertEqual(config["paths"]["task_glob"], "tasks/build/*.md")
            self.assertEqual(
                config["paths"]["task_globs"],
                ["tasks/build/*.md", ".tasks/build/*.md"],
            )
            self.assertEqual(
                config["paths"]["revision_glob"], "tasks/revisions/*.md"
            )
            self.assertTrue(config["scan_worker_refs_for_status"])
            self.assertEqual(config["project_status_max_lines"], 160)
            self.assertEqual(config["project_status_max_chars"], 12000)
            self.assertEqual(config["discussion_dynamic_max_lines"], 30)
            self.assertTrue(config["orchestration_gate_enabled"])
            self.assertEqual(config["read_gate_mode"], "host_dependent")
            self.assertIn("prompts/INTEGRATION_AI.md", config["required_impact_rows"])

            second = subprocess.run(
                [
                    sys.executable,
                    str(INSTALLER),
                    "--target",
                    str(root),
                    "--host",
                    "codex",
                    "--mode",
                    "warn",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            rerun = json.loads((root / ".codex" / "hooks.json").read_text())
            memory_groups = [
                group
                for group in rerun["hooks"]["SessionStart"]
                if any("memory_sync.py" in hook["command"] for hook in group["hooks"])
            ]
            self.assertEqual(len(memory_groups), 1)

    def test_installer_migrates_version_two_status_config(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            (root / ".wishgraph").mkdir()
            (root / ".wishgraph" / "config.json").write_text(
                json.dumps(
                    {
                        "version": 2,
                        "mode": "warn",
                        "session_summary_max_chars": 1234,
                        "paths": {
                            "task_glob": ".tasks/build/*.md",
                            "dev_report": "custom/CURRENT.md",
                        },
                    }
                ),
                encoding="utf-8",
            )
            process = subprocess.run(
                [
                    sys.executable,
                    str(INSTALLER),
                    "--target",
                    str(root),
                    "--host",
                    "codex",
                    "--mode",
                    "warn",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            config = json.loads((root / ".wishgraph" / "config.json").read_text())
            self.assertEqual(config["version"], 11)
            self.assertEqual(config["session_start_context_mode"], "safety_only")
            self.assertEqual(config["session_summary_max_chars"], 1234)
            self.assertTrue(config["scan_worker_refs_for_status"])
            self.assertEqual(config["paths"]["task_glob"], ".tasks/build/*.md")
            self.assertEqual(
                config["paths"]["task_globs"],
                ["tasks/build/*.md", ".tasks/build/*.md"],
            )
            self.assertEqual(config["paths"]["project_status"], "custom/CURRENT.md")
            self.assertNotIn("dev_report", config["paths"])


class OneCommandInstallerTests(unittest.TestCase):
    def test_check_mode_reports_cost_without_installing(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            project = root / "project"
            project.mkdir()
            subprocess.run(["git", "-C", str(project), "init", "-q"], check=True)
            env = os.environ.copy()
            env["CODEX_HOME"] = str(root / "codex-home")
            process = subprocess.run(
                [
                    "bash",
                    str(TOP_LEVEL_INSTALLER),
                    "codex",
                    "--setup-project",
                    "--check",
                ],
                cwd=project,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertIn("about 0.5 MB", process.stdout)
            self.assertIn("Prerequisite check passed", process.stdout)
            self.assertFalse((root / "codex-home").exists())
            self.assertFalse((project / ".wishgraph").exists())

    def test_missing_python_reports_guidance_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            project = root / "project"
            project.mkdir()
            fake_bin = root / "bin"
            fake_bin.mkdir()
            git_path = shutil.which("git")
            bash_path = shutil.which("bash")
            assert git_path is not None
            assert bash_path is not None
            os.symlink(git_path, fake_bin / "git")
            env = os.environ.copy()
            env["PATH"] = str(fake_bin)
            env["CODEX_HOME"] = str(root / "codex-home")
            process = subprocess.run(
                [bash_path, str(TOP_LEVEL_INSTALLER), "codex", "--setup-project"],
                cwd=project,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(process.returncode, 3)
            self.assertIn("Python 3.9 or newer", process.stderr)
            self.assertIn("100-300 MB", process.stderr)
            self.assertIn("Nothing was installed", process.stderr)
            self.assertFalse((root / "codex-home").exists())
            self.assertFalse((project / ".wishgraph").exists())

    def test_missing_dependencies_are_guided_one_at_a_time(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            project = root / "project"
            project.mkdir()
            fake_bin = root / "bin"
            fake_bin.mkdir()
            bash_path = shutil.which("bash")
            assert bash_path is not None
            env = os.environ.copy()
            env["PATH"] = str(fake_bin)
            process = subprocess.run(
                [bash_path, str(TOP_LEVEL_INSTALLER), "codex", "--setup-project"],
                cwd=project,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(process.returncode, 3)
            self.assertIn("Git is required", process.stderr)
            self.assertNotIn("Python 3.9", process.stderr)
            self.assertIn("Nothing was installed", process.stderr)

    def test_fresh_install_can_setup_current_project_in_one_command(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            source = root / "source"
            source.mkdir()
            subprocess.run(["git", "-C", str(source), "init", "-q"], check=True)
            subprocess.run(
                ["git", "-C", str(source), "checkout", "-qb", "main"], check=True
            )
            subprocess.run(
                ["git", "-C", str(source), "config", "user.email", "test@example.com"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(source), "config", "user.name", "WishGraph Tests"],
                check=True,
            )
            shutil.copytree(
                ROOT / "skills" / "wishgraph",
                source / "skills" / "wishgraph",
            )
            subprocess.run(["git", "-C", str(source), "add", "."], check=True)
            subprocess.run(
                ["git", "-C", str(source), "commit", "-qm", "fixture"], check=True
            )

            project = root / "project"
            project.mkdir()
            subprocess.run(["git", "-C", str(project), "init", "-q"], check=True)
            codex_home = root / "codex-home"
            env = os.environ.copy()
            env["CODEX_HOME"] = str(codex_home)
            env["WISHGRAPH_REPO_URL"] = str(source)
            env["WISHGRAPH_REF"] = "main"

            process = subprocess.run(
                ["bash", str(TOP_LEVEL_INSTALLER), "codex", "--setup-project"],
                cwd=project,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertIn("Next: reopen the current Agent session", process.stdout)
            self.assertTrue((codex_home / "skills" / "wishgraph" / "SKILL.md").exists())
            self.assertTrue((project / ".codex" / "hooks.json").exists())
            config = json.loads((project / ".wishgraph" / "config.json").read_text())
            self.assertEqual(config["mode"], "warn")

    def test_setup_project_reuses_installed_skill_and_defaults_to_warn(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            project = root / "project"
            project.mkdir()
            subprocess.run(["git", "-C", str(project), "init", "-q"], check=True)

            codex_home = root / "codex-home"
            installed_skill = codex_home / "skills" / "wishgraph"
            shutil.copytree(ROOT / "skills" / "wishgraph", installed_skill)
            env = os.environ.copy()
            env["CODEX_HOME"] = str(codex_home)

            process = subprocess.run(
                ["bash", str(TOP_LEVEL_INSTALLER), "codex", "--setup-project"],
                cwd=project,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertIn("reusing it for project setup", process.stdout)
            config = json.loads((project / ".wishgraph" / "config.json").read_text())
            self.assertEqual(config["mode"], "warn")
            self.assertTrue((project / ".codex" / "hooks.json").exists())
            self.assertFalse((project / ".claude" / "settings.json").exists())

            strict = subprocess.run(
                [
                    "bash",
                    str(TOP_LEVEL_INSTALLER),
                    "codex",
                    "--setup-project",
                    "--strict",
                ],
                cwd=project,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(strict.returncode, 0, strict.stderr)
            config = json.loads((project / ".wishgraph" / "config.json").read_text())
            self.assertEqual(config["mode"], "enforce")
            self.assertTrue((project / ".git" / "hooks" / "pre-commit").exists())

    def test_claude_user_install_adds_managed_global_worker_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            source = root / "source"
            source.mkdir()
            subprocess.run(["git", "-C", str(source), "init", "-q"], check=True)
            subprocess.run(
                ["git", "-C", str(source), "checkout", "-qb", "main"], check=True
            )
            subprocess.run(
                ["git", "-C", str(source), "config", "user.email", "test@example.com"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(source), "config", "user.name", "WishGraph Tests"],
                check=True,
            )
            shutil.copytree(
                ROOT / "skills" / "wishgraph", source / "skills" / "wishgraph"
            )
            subprocess.run(["git", "-C", str(source), "add", "."], check=True)
            subprocess.run(
                ["git", "-C", str(source), "commit", "-qm", "fixture"], check=True
            )
            home = root / "home"
            home.mkdir()
            env = os.environ.copy()
            env["HOME"] = str(home)
            env["WISHGRAPH_REPO_URL"] = str(source)
            env["WISHGRAPH_REF"] = "main"
            process = subprocess.run(
                ["bash", str(TOP_LEVEL_INSTALLER), "claude-user"],
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertTrue((home / ".claude/skills/wishgraph/SKILL.md").is_file())
            agent = home / ".claude/agents/wishgraph-worker.md"
            self.assertTrue(agent.is_file())
            self.assertIn(
                "wishgraph-managed: wishgraph-worker",
                agent.read_text(encoding="utf-8"),
            )

    def test_strict_requires_project_setup(self) -> None:
        process = subprocess.run(
            ["bash", str(TOP_LEVEL_INSTALLER), "codex", "--strict"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(process.returncode, 2)
        self.assertIn("requires --setup-project", process.stderr)

    def test_windows_installer_exposes_equivalent_guided_options(self) -> None:
        content = POWERSHELL_INSTALLER.read_text(encoding="utf-8")
        for expected in (
            "[switch]$SetupProject",
            "[switch]$Strict",
            "[switch]$Check",
            "winget install --id Git.Git",
            "winget install 9NQ7512CXL7T",
            "py list --format=exe",
            "about 0.5 MB",
            "wishgraph-worker.md",
            "wishgraph-managed: wishgraph-worker",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, content)

    def test_skill_prompts_agent_to_recommend_and_resume(self) -> None:
        skill = (ROOT / "skills" / "wishgraph" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        installation = (
            ROOT / "skills" / "wishgraph" / "references" / "installation.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Installation, prerequisites", skill)
        self.assertNotIn("Natural-Language Installation", skill)
        self.assertIn("Make a recommendation before asking", installation)
        self.assertIn("four visible stages", installation)
        self.assertIn("按推荐来", installation)
        self.assertIn("exact resume phrase", installation)
        self.assertIn("选择", installation)
        self.assertIn("已安装 Python", installation)

    def test_discussion_prompt_guides_workers_and_work_classification(self) -> None:
        prompt = (ROOT / "templates" / "prompts" / "DISCUSSION_AI.md").read_text(
            encoding="utf-8"
        )
        for expected in (
            "## Work Classification",
            "discussion",
            "sequential",
            "parallel_batch",
            "high_risk",
            "expected_transition",
            "awaiting_worker_authorization",
            "routing_worker",
            "执行 <task-id> 任务",
            "Discussion-local Integration",
            "<task-id> · <short title> · WG Worker",
            "Never implement Worker work",
            "worker_creation_authorized",
            "integrated` to `reviewed",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, prompt)

    def test_worker_launch_protocol_requires_visible_human_authorized_tasks(self) -> None:
        reference = (
            ROOT
            / "skills"
            / "wishgraph"
            / "references"
            / "worker-execution.md"
        ).read_text(encoding="utf-8")
        chinese_prompt = (
            ROOT / "templates" / "zh-CN" / "prompts" / "DISCUSSION_AI.md"
        ).read_text(encoding="utf-8")
        for expected in (
            "approve_worker_launch",
            "waiting_for_user_launch",
            "执行 <task-id> 任务",
            "separate user-visible and inspectable Worker thread or window",
            "<task-id> · <short title> · WG Worker",
            "Never substitute a hidden subagent or let Discussion implement the Task",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, reference)
        for expected in (
            "expected_transition",
            "awaiting_worker_authorization",
            "routing_worker",
            "执行 <task-id> 任务",
            "Discussion-local Integration",
            "不得在 Discussion 中实现 Worker 工作",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, chinese_prompt)

    def test_integration_prompt_is_discussion_local_and_lease_bound(self) -> None:
        discussion = (
            ROOT / "templates" / "prompts" / "DISCUSSION_AI.md"
        ).read_text(encoding="utf-8")
        integration = (
            ROOT / "templates" / "prompts" / "INTEGRATION_AI.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Discussion-local Integration", discussion)
        self.assertIn("integration_pending", discussion)
        self.assertIn("decision_required", discussion)
        self.assertIn("Integration lease", integration)
        self.assertIn("Do not create a new Integration window", integration)
        self.assertIn("task-state", integration)
        self.assertIn("`completed` to `integrated`", integration)
        self.assertNotIn("silently launch a temporary Integrator", discussion)
        self.assertNotIn("end this temporary agent", integration)

    def test_hooks_are_not_semantic_reviewers_or_agent_launchers(self) -> None:
        runtime = (HOOK_ASSETS / "memory_sync.py").read_text(encoding="utf-8")
        reference = (
            ROOT / "skills" / "wishgraph" / "references" / "memory-sync-hooks.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Hooks do not start agents", runtime)
        self.assertIn("do not write semantic project memory", reference)
        self.assertIn("launch Workers", reference)
        self.assertNotIn("subprocess.Popen", runtime)


class TemplateMirrorTests(unittest.TestCase):
    def test_new_task_templates_use_versioned_task_state(self) -> None:
        for relative in (
            "tasks/build/001-bootstrap-project.md",
            "tasks/build/EXAMPLE-good-task.md",
            "tasks/build/NNN-task.md",
            "zh-CN/tasks/build/001-bootstrap-project.md",
            "zh-CN/tasks/build/EXAMPLE-good-task.md",
            "zh-CN/tasks/build/NNN-task.md",
        ):
            with self.subTest(template=relative):
                content = (ROOT / "templates" / relative).read_text(encoding="utf-8")
                self.assertIn("wishgraph:task-state:start", content)
                self.assertIn('"schema_version": 1', content)
                self.assertIn('"worker_creation_authorized": false', content)
                self.assertTrue(
                    "Task state records only Task Lifecycle" in content
                    or "Task state 只记录 Task Lifecycle" in content
                )

    def test_distributable_template_mirrors_stay_identical(self) -> None:
        pairs = [
            ("CODEMAP.md", "CODEMAP.md"),
            ("CONVENTIONS.md", "CONVENTIONS.md"),
            ("prompts/DISCUSSION_AI.md", "DISCUSSION_AI.md"),
            ("prompts/EXECUTION_AI.md", "EXECUTION_AI.md"),
            ("prompts/INTEGRATION_AI.md", "INTEGRATION_AI.md"),
            ("reports/PROJECT_STATUS.md", "PROJECT_STATUS.md"),
            ("reports/RUN_REPORT.md", "RUN_REPORT.md"),
            ("tasks/revisions/TASK_REVISION.md", "TASK_REVISION.md"),
            ("tasks/build/001-bootstrap-project.md", "001-bootstrap-project.md"),
            ("tasks/build/EXAMPLE-good-task.md", "EXAMPLE-good-task.md"),
            ("tasks/build/NNN-task.md", "NNN-task.md"),
        ]
        for manual, bundled in pairs:
            with self.subTest(template=manual):
                self.assertEqual(
                    (ROOT / "templates" / manual).read_bytes(),
                    (ROOT / "skills" / "wishgraph" / "assets" / "templates" / bundled).read_bytes(),
                )

    def test_chinese_template_mirrors_stay_identical(self) -> None:
        pairs = [
            ("CODEMAP.md", "CODEMAP.md"),
            ("CONVENTIONS.md", "CONVENTIONS.md"),
            ("prompts/DISCUSSION_AI.md", "prompts/DISCUSSION_AI.md"),
            ("prompts/EXECUTION_AI.md", "prompts/EXECUTION_AI.md"),
            ("prompts/INTEGRATION_AI.md", "prompts/INTEGRATION_AI.md"),
            ("reports/PROJECT_STATUS.md", "reports/PROJECT_STATUS.md"),
            ("reports/RUN_REPORT.md", "reports/RUN_REPORT.md"),
            (
                "tasks/revisions/TASK_REVISION.md",
                "tasks/revisions/TASK_REVISION.md",
            ),
            ("tasks/build/001-bootstrap-project.md", "tasks/build/001-bootstrap-project.md"),
            ("tasks/build/EXAMPLE-good-task.md", "tasks/build/EXAMPLE-good-task.md"),
            ("tasks/build/NNN-task.md", "tasks/build/NNN-task.md"),
        ]
        for manual, bundled in pairs:
            with self.subTest(template=manual):
                self.assertEqual(
                    (ROOT / "templates" / "zh-CN" / manual).read_bytes(),
                    (
                        ROOT
                        / "skills"
                        / "wishgraph"
                        / "assets"
                        / "templates"
                        / "zh-CN"
                        / bundled
                    ).read_bytes(),
                )

    def test_new_templates_use_project_status_only(self) -> None:
        self.assertTrue((ROOT / "templates" / "reports" / "PROJECT_STATUS.md").exists())
        self.assertFalse((ROOT / "templates" / "reports" / "DEV_REPORT.md").exists())
        self.assertTrue(
            (
                ROOT
                / "skills"
                / "wishgraph"
                / "assets"
                / "templates"
                / "PROJECT_STATUS.md"
            ).exists()
        )
        self.assertFalse(
            (ROOT / "skills" / "wishgraph" / "assets" / "templates" / "DEV_REPORT.md").exists()
        )

    def test_legacy_dev_report_references_are_compatibility_only(self) -> None:
        allowed = {
            "docs/memory-sync-hooks.md",
            "docs/memory-sync-hooks.zh-CN.md",
            "scripts/install-wishgraph.ps1",
            "scripts/install-wishgraph.sh",
            "skills/wishgraph/SKILL.md",
            "skills/wishgraph/assets/hooks/memory_sync.py",
            "skills/wishgraph/assets/hooks/git_state.py",
            "skills/wishgraph/assets/hooks/host_adapter.py",
            "skills/wishgraph/assets/hooks/policy.py",
            "skills/wishgraph/assets/templates/INTEGRATION_AI.md",
            "skills/wishgraph/assets/templates/zh-CN/prompts/INTEGRATION_AI.md",
            "skills/wishgraph/references/memory-sync-hooks.md",
            "skills/wishgraph/references/project-bootstrap.md",
            "skills/wishgraph/scripts/install_project_hooks.py",
            "templates/prompts/INTEGRATION_AI.md",
            "templates/zh-CN/prompts/INTEGRATION_AI.md",
            "tests/test_memory_sync.py",
        }
        unexpected: list[str] = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts:
                continue
            if path.suffix.lower() not in {".md", ".py", ".sh", ".ps1", ".json"}:
                continue
            content = path.read_text(encoding="utf-8", errors="ignore")
            if "DEV_REPORT" in content or "dev_report" in content:
                relative = path.relative_to(ROOT).as_posix()
                if relative not in allowed:
                    unexpected.append(relative)
        self.assertEqual(unexpected, [])


if __name__ == "__main__":
    unittest.main()
