from tests.wishgraph_test_support import *  # noqa: F401,F403

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
        worker_execution_profiles: Optional[dict[str, dict[str, str]]] = None,
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
                worker_execution_profiles=worker_execution_profiles or {},
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

    def test_contextual_approval_may_override_worker_profile(self) -> None:
        plan = memory_sync.reduce_orchestration(
            self.state(),
            self.event("user_message", text="批准，用 sol 高"),
            self.capability(),
        )
        self.assertTrue(plan.accepted)
        self.assertEqual(
            plan.work_payload["execution_profile"],
            {"model": "gpt-5.6-sol", "reasoning_effort": "high"},
        )

    def test_plain_approval_uses_this_tasks_grounded_recommendation(self) -> None:
        plan = memory_sync.reduce_orchestration(
            self.state(
                worker_execution_profiles={
                    "codex": {
                        "model": "gpt-5.6-terra",
                        "reasoning_effort": "medium",
                    },
                    "claude": {"model": "sonnet", "reasoning_effort": "low"},
                }
            ),
            self.event("user_message", text="批准"),
            self.capability(host="codex"),
        )
        self.assertEqual(
            plan.work_payload["execution_profile"],
            {"model": "gpt-5.6-terra", "reasoning_effort": "medium"},
        )

    def test_plain_approval_without_recommendation_keeps_host_default(self) -> None:
        plan = memory_sync.reduce_orchestration(
            self.state(),
            self.event("user_message", text="批准"),
            self.capability(host="codex"),
        )
        self.assertEqual(plan.work_payload["execution_profile"], {})

    def test_osm_02_neutral_explicit_execute_binds_current_worker(self) -> None:
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
        self.assertTrue(plan.accepted)
        self.assertEqual(plan.next_action, "bind_current_worker")
        self.assertFalse(plan.required_claim)
        self.assertEqual(plan.state_patch["session"]["role"], "neutral")
        self.assertEqual(plan.state_patch["session"]["phase"], "routing_worker")
        self.assertEqual(plan.state_patch["task"]["lifecycle"], "approved")
        self.assertTrue(plan.state_patch["task"]["worker_authorized"])

    def test_neutral_exact_execute_authorizes_draft_for_current_worker(self) -> None:
        plan = memory_sync.reduce_orchestration(
            self.state(
                role="neutral",
                phase="planning",
                lifecycle="draft",
                worker_authorized=False,
                expected_kind=None,
            ),
            self.event("user_message", text="执行 002 任务"),
            self.capability(host="claude", create_worker=True),
        )
        self.assertTrue(plan.accepted)
        self.assertEqual(plan.next_action, "bind_current_worker")
        self.assertEqual(plan.state_patch["session"]["role"], "neutral")
        self.assertEqual(plan.state_patch["task"]["lifecycle"], "approved")
        self.assertTrue(plan.state_patch["task"]["worker_authorized"])

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
            grants = []
            for session_id, integration_id, task_id in (
                ("discussion-1", "integration-1", "002"),
                ("discussion-2", "integration-2", "003"),
            ):
                memory_sync.write_session_runtime(
                    root,
                    session_id,
                    {
                        "session": {
                            "session_id": session_id,
                            "role": "discussion",
                            "host": "codex",
                            "phase": "integrating",
                            "expected_transition": None,
                        },
                        "session_provenance": {
                            "initial_role": "neutral",
                            "discussion_authorized": True,
                        },
                    },
                )
                grants.append(
                    memory_sync.create_integration_transition_grant(
                        root,
                        session_id=session_id,
                        integration_id=integration_id,
                        task_ids=[task_id],
                        reports=[f"reports/runs/{task_id}-attempt-1.md"],
                        outcome="safe",
                    )["grant"]["grant_id"]
                )
            first = memory_sync.acquire_integration_lease(
                root,
                session_id="discussion-1",
                grant_id=grants[0],
                integration_id="integration-1",
                task_ids=["002"],
                reports=["reports/runs/002-attempt-1.md"],
                require_clean=False,
            )
            second = memory_sync.acquire_integration_lease(
                root,
                session_id="discussion-2",
                grant_id=grants[1],
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
            task_path = root / "tasks/012-table-scope.md"
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

    def test_revision_report_path_uses_project_template(self) -> None:
        config = {
            "paths": {
                "run_report_glob": "evidence/*.md",
                "run_report_template": "evidence/{work_unit_id}-run-{attempt}.md",
            }
        }
        plan = memory_sync.reduce_orchestration(
            self.state(task_id="012", lifecycle="completed", expected_kind=None),
            self.event(
                "user_requested_revision", **self.revision_data(next_revision_number=2)
            ),
            self.capability(create_worker=True),
            config,
        )
        self.assertEqual(plan.revision_id, "012-r2")
        self.assertEqual(
            plan.work_payload["run_report"], "evidence/012-r2-run-1.md"
        )

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
            ),
            self.capability(),
        )
        self.assertEqual(plan.state_patch["revision"]["status"], "integrated")
        self.assertNotIn("project_status_updated", plan.state_patch["revision"])
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
            task_path = root / "tasks/012-parent.md"
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
                        "integration_route": "auto_in_discussion",
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
