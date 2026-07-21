from tests.wishgraph_test_support import *  # noqa: F401,F403

class ClaimAndHookTests(MemorySyncTestCase):
    def test_parallel_claude_workers_receive_distinct_worktree_names(self) -> None:
        host_adapter_module = sys.modules["host_adapter"]
        first = claude_worker_provider_module._claude_worker_worktree_name("056")
        second = claude_worker_provider_module._claude_worker_worktree_name("056")
        self.assertNotEqual(first, second)
        self.assertRegex(first, r"^wishgraph-056-[0-9a-f]{8}$")

    def test_execution_profile_uses_grounded_request_or_actual_host_default(self) -> None:
        host_adapter_module = sys.modules["host_adapter"]
        defaults = host_adapter_module._resolve_execution_profile(
            self.config, "codex", {}
        )
        self.assertEqual(defaults["resolved"], {})
        self.assertEqual(defaults["source"], "current_host_default")
        self.assertEqual(
            host_adapter_module._resolve_claude_execution_profile(
                {"model": "opus", "reasoning_effort": "xhigh"}, self.config
            )["resolved"],
            {"model": "opus", "reasoning_effort": "xhigh"},
        )
        incompatible = host_adapter_module._resolve_claude_execution_profile(
            {"model": "gpt-5.6-sol", "reasoning_effort": "high"}, self.config
        )
        self.assertTrue(incompatible["override_applied"])
        self.assertEqual(
            incompatible["resolved"],
            {"reasoning_effort": "high"},
        )
        self.assertEqual(incompatible["ignored_fields"], ["model"])

    def test_formal_worker_requires_local_head_but_not_remote(self) -> None:
        host_adapter_module = sys.modules["host_adapter"]
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            missing = host_adapter_module._local_git_baseline(root)
            self.assertFalse(missing["ok"])
            self.assertEqual(missing["error"], "local_git_baseline_commit_required")
            (root / "README.md").write_text("baseline\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "-c",
                    "user.name=WishGraph Test",
                    "-c",
                    "user.email=wishgraph@example.test",
                    "commit",
                    "-qm",
                    "local baseline",
                ],
                check=True,
            )
            self.assertTrue(host_adapter_module._local_git_baseline(root)["ok"])
            remotes = subprocess.run(
                ["git", "-C", str(root), "remote"],
                check=True,
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
            )
            self.assertEqual(remotes.stdout, "")

    def test_claude_launch_failure_cli_outputs_host_neutral_manual_handoff(self) -> None:
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
                claude_worker_provider_module,
                "detect_claude_worker_capability",
                return_value=capability,
            ),
            mock.patch.object(
                claude_worker_provider_module,
                "_query_claude_agents",
                return_value={"ok": True, "sessions": []},
            ),
            mock.patch.object(
                claude_worker_provider_module, "_run_process", return_value=failed_process
            ),
        ):
            payload = memory_sync.launch_claude_worker(
                self.root, self.config, task_id, discussion_id
            )
        self.assertTrue(payload["fallback"])
        self.assertEqual(payload["user_message"], "执行 037 任务")
        self.assertIn("cd ", payload["manual_launch_instructions"])
        self.assertIn("Codex：", payload["manual_launch_instructions"])
        self.assertIn("Claude Code：", payload["manual_launch_instructions"])
        self.assertIn("当前默认配置", payload["manual_launch_instructions"])
        self.assertIn("\ncodex\n", payload["manual_launch_instructions"])
        self.assertIn("\nclaude\n", payload["manual_launch_instructions"])
        self.assertNotIn("--model", payload["manual_launch_instructions"])
        self.assertIn("执行 037", payload["manual_launch_instructions"])
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
        printed.assert_called_once_with(payload["manual_launch_instructions"])

    def test_claude_unverified_created_session_uses_real_recovery_surface(self) -> None:
        task_id = "063"
        discussion_id = "discussion-063"
        worker_id = "12345678-aaaa-bbbb-cccc-123456789abc"
        self.prepare_claude_worker_task(task_id, discussion_id)
        host_adapter_module = sys.modules["host_adapter"]
        capability = memory_sync.ClaudeWorkerCapability(
            tier="background_session",
            claude_executable="/bin/claude",
            agent_definition="managed-agent",
            supports_background=True,
            supports_agents_json=True,
            supports_worktree=True,
            supports_settings=True,
            reason="native_background_session_available",
        )
        launched_process = subprocess.CompletedProcess(
            [], 0, stdout="backgrounded · 12345678\n", stderr=""
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
        with (
            mock.patch.object(
                claude_worker_provider_module,
                "detect_claude_worker_capability",
                return_value=capability,
            ),
            mock.patch.object(
                claude_worker_provider_module,
                "_query_claude_agents",
                return_value=after,
            ),
            mock.patch.object(
                claude_worker_provider_module,
                "_run_process",
                return_value=launched_process,
            ) as run_process,
        ):
            payload = memory_sync.launch_claude_worker(
                self.root, self.config, task_id, discussion_id
            )
        self.assertTrue(payload["fallback"])
        self.assertEqual(payload["user_message"], "执行 063 任务")
        self.assertEqual(payload["orphaned_background_session_id"], worker_id)
        self.assertEqual(run_process.call_count, 1)
        self.assertNotIn(" stop ", f" {payload['recovery_command']} ")
        self.assertIn(" agents --cwd ", f" {payload['recovery_command']} ")
        runtime = memory_sync.read_session_runtime(self.root, discussion_id)
        assert runtime is not None
        self.assertEqual(
            runtime["worker_runtime"]["sync_status"],
            "manual_intervention_required",
        )
        self.assertEqual(
            runtime["worker_runtime"]["worker_handle"]["terminal_state"],
            "manual_intervention_required",
        )

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
                claude_worker_provider_module,
                "detect_claude_worker_capability",
                return_value=capability,
            ),
            mock.patch.object(
                claude_worker_provider_module,
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
                claude_worker_provider_module,
                "detect_claude_worker_capability",
                return_value=capability,
            ),
            mock.patch.object(
                claude_worker_provider_module, "_query_claude_agents", return_value=working
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
        self.write(
            f"reports/runs/{task_id}-attempt-1.md",
            self.run_report(task_id),
        )
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
        notified = memory_sync.enqueue_terminal_notification_from_claim(
            self.root, self.config, released["claim"]
        )
        self.assertTrue(notified["ok"], notified)
        completed = {
            "ok": True,
            "sessions": [
                {"id": "87654321", "sessionId": worker_id, "state": "done"}
            ],
        }
        with (
            mock.patch.object(
                claude_worker_provider_module,
                "detect_claude_worker_capability",
                return_value=capability,
            ),
            mock.patch.object(
                claude_worker_provider_module, "_query_claude_agents", return_value=completed
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
                claude_worker_provider_module,
                "detect_claude_worker_capability",
                return_value=capability,
            ),
            mock.patch.object(
                claude_worker_provider_module,
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
            encoding="utf-8",
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
            encoding="utf-8",
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
            encoding="utf-8",
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
        content = self._run_report_narrative("structured-invalid").replace(
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
            integration_policy="decision_required",
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
                    "integration_route": "auto_in_discussion",
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
            self.discussion("worker-should-not-write") + "\nworker edit\n",
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
            encoding="utf-8",
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
            encoding="utf-8",
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

    def test_claude_discussion_route_requires_head_commit_and_direct_adapter_call(self) -> None:
        task_id = "059"
        discussion_id = "discussion-059"
        task_path = f"tasks/build/{task_id}-claude-worker.md"
        self.write(task_path, self.execution_ready_task(task_id))
        self.git("add", task_path)
        self.git("commit", "-qm", "prepare draft 059")
        persisted = memory_sync.write_session_runtime(
            self.root,
            discussion_id,
            {
                "session": {
                    "session_id": discussion_id,
                    "role": "discussion",
                    "host": "claude",
                    "phase": "awaiting_worker_authorization",
                    "expected_transition": {
                        "kind": "approve_worker_launch",
                        "task_id": task_id,
                    },
                },
                "task": {
                    "task_id": task_id,
                    "lifecycle": "draft",
                    "worker_authorized": False,
                    "run_report": f"reports/runs/{task_id}-attempt-1.md",
                },
            },
        )
        self.assertTrue(persisted["ok"], persisted)
        routed = subprocess.run(
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
                    "session_id": discussion_id,
                    "prompt": f"执行 {task_id} 任务",
                }
            ),
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        context = json.loads(routed.stdout)["hookSpecificOutput"]["additionalContext"]
        route = json.loads(context.split("WishGraph explicit route:\n", 1)[1])
        command = route["host_adapter_command"]
        self.assertIn("current Discussion session, directly run", context)
        self.assertIn(str(sys.executable), command)
        self.assertIn("claude-worker", command)
        self.assertIn("launch", command)
        self.assertIn(task_id, command)
        self.assertIn(discussion_id, command)
        self.assertIn("Do not use Task, Agent, /fork", context)
        self.assertIn("managed wishgraph-worker", context)
        self.assertIn('"authorization_commit_required":false', context)
        self.assertIn('"delegation_forbidden":true', context)

        self.write(
            task_path,
            self.execution_ready_task(
                task_id,
                status="approved",
                worker_authorized=True,
            ),
        )
        rejected = memory_sync.launch_claude_worker(
            self.root,
            self.config,
            task_id,
            discussion_id,
            claude_executable="definitely-not-claude",
        )
        self.assertFalse(rejected["ok"])
        self.assertEqual(
            rejected["error"],
            "authorized_task_must_match_current_head_for_execution_thread",
        )

    def test_internal_session_runtime_apply_deep_merges_reducer_patch(self) -> None:
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
        internal = memory_sync.apply_session_runtime_patch(
            self.root,
            "discussion-apply",
            {
                "session": {"phase": "routing_worker", "expected_transition": None},
                "task": {"lifecycle": "approved", "worker_authorized": True},
            },
        )
        self.assertTrue(internal["ok"], internal)
        runtime = internal["runtime"]
        self.assertEqual(runtime["session"]["role"], "discussion")
        self.assertEqual(runtime["session"]["phase"], "routing_worker")
        self.assertIsNone(runtime["session"]["expected_transition"])
        self.assertEqual(runtime["task"]["task_id"], "002")
        self.assertEqual(runtime["task"]["lifecycle"], "approved")

    def test_public_session_apply_rejects_authority_fields(self) -> None:
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
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(process.returncode, 1)
        payload = json.loads(process.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "session_direct_authority_write_forbidden")

    def test_public_session_set_cannot_promote_worker_to_discussion(self) -> None:
        process = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "session",
                "set",
                "worker-promote",
                "--role",
                "discussion",
                "--phase",
                "integrating",
            ],
            cwd=self.root,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(process.returncode, 1)
        self.assertEqual(
            json.loads(process.stdout)["error"],
            "session_direct_authority_write_forbidden",
        )

    def test_worker_control_commands_cannot_change_session_or_acquire_lease(self) -> None:
        memory_sync.write_session_runtime(
            self.root,
            "worker-control",
            {
                "session": {
                    "session_id": "worker-control",
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

        def invoke(command: str) -> dict[str, object]:
            process = subprocess.run(
                [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "pre-tool-use"],
                cwd=self.root,
                input=json.dumps(
                    {
                        "cwd": str(self.root),
                        "session_id": "worker-control",
                        "tool_name": "Bash",
                        "tool_input": {"command": command},
                    }
                ),
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            return json.loads(process.stdout)

        commands = (
            "python3 .wishgraph/hooks/memory_sync.py session set worker-control --role discussion --phase integrating",
            "python3 .wishgraph/hooks/memory_sync.py session apply worker-control",
            "python3 .wishgraph/hooks/memory_sync.py session transition other-discussion integration_evaluated --data-json '{}'",
            "python3 .wishgraph/hooks/memory_sync.py integration-lease acquire --session-id worker-control --grant-id fake --integration-id fake --task-id 002 --report reports/runs/002.md",
        )
        for command in commands:
            with self.subTest(command=command):
                payload = invoke(command)
                self.assertEqual(
                    payload["hookSpecificOutput"]["permissionDecision"], "deny"
                )

    def test_helper_agent_cannot_control_claim_or_integration_lease(self) -> None:
        memory_sync.write_session_runtime(
            self.root,
            "helper-control",
            {
                "session": {
                    "session_id": "helper-control",
                    "role": "neutral",
                    "host": "codex",
                    "phase": "planning",
                    "expected_transition": None,
                },
                "launch_context": {"agent_kind": "helper"},
            },
        )
        for command in (
            "python3 .wishgraph/hooks/memory_sync.py claim acquire 002 --worker-id helper-control --session-id helper-control --agent-kind helper --container-kind helper_subagent",
            "python3 .wishgraph/hooks/memory_sync.py integration-lease acquire --session-id helper-control --grant-id fake --integration-id fake --task-id 002 --report reports/runs/002.md",
            "python3 .wishgraph/hooks/memory_sync.py integration-lease revoke --session-id helper-control",
        ):
            process = subprocess.run(
                [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "pre-tool-use"],
                cwd=self.root,
                input=json.dumps(
                    {
                        "cwd": str(self.root),
                        "session_id": "helper-control",
                        "tool_name": "Bash",
                        "tool_input": {"command": command},
                    }
                ),
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
                check=True,
            )
            payload = json.loads(process.stdout)
            self.assertEqual(payload["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_worker_cannot_turn_its_session_into_discussion_by_user_alias(self) -> None:
        memory_sync.write_session_runtime(
            self.root,
            "worker-discussion-alias",
            {
                "session": {
                    "session_id": "worker-discussion-alias",
                    "role": "worker",
                    "host": "codex",
                    "phase": "waiting_for_worker",
                    "expected_transition": None,
                }
            },
        )
        process = subprocess.run(
            [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "user-prompt-submit"],
            cwd=self.root,
            input=json.dumps(
                {
                    "cwd": str(self.root),
                    "session_id": "worker-discussion-alias",
                    "prompt": "开始讨论",
                }
            ),
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            check=True,
        )
        context = json.loads(process.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("cannot become Discussion", context)
        runtime = memory_sync.read_session_runtime(self.root, "worker-discussion-alias")
        assert runtime is not None
        self.assertEqual(runtime["session"]["role"], "worker")

    def test_unclaimed_formal_worker_thread_cannot_enter_discussion(self) -> None:
        session_id = "unclaimed-formal-worker"
        memory_sync.write_session_runtime(
            self.root,
            session_id,
            {
                "session": {
                    "session_id": session_id,
                    "role": "neutral",
                    "host": "claude",
                    "phase": "planning",
                    "expected_transition": None,
                },
                "session_provenance": {
                    "initial_role": "neutral",
                    "host": "claude",
                    "discussion_authorized": False,
                },
                "launch_context": {
                    "agent_kind": "formal_worker",
                    "task_id": "002",
                },
            },
        )
        process = subprocess.run(
            [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "user-prompt-submit"],
            cwd=self.root,
            input=json.dumps(
                {
                    "cwd": str(self.root),
                    "session_id": session_id,
                    "prompt": "开始讨论",
                }
            ),
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            check=True,
        )
        context = json.loads(process.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("cannot become Discussion", context)
        runtime = memory_sync.read_session_runtime(self.root, session_id)
        assert runtime is not None
        self.assertEqual(runtime["session"]["role"], "neutral")
        self.assertFalse(runtime["session_provenance"]["discussion_authorized"])

    def test_worker_cannot_edit_approved_task_integration_route(self) -> None:
        task_path = "tasks/build/052-policy.md"
        self.write(
            task_path,
            self.execution_ready_task(
                "052", status="approved", worker_authorized=True
            ),
        )
        self.git("add", task_path)
        self.git("commit", "-qm", "approve policy fixture")
        memory_sync.write_session_runtime(
            self.root,
            "worker-policy",
            {
                "session": {
                    "session_id": "worker-policy",
                    "role": "worker",
                    "host": "unknown",
                    "phase": "waiting_for_worker",
                    "expected_transition": None,
                },
                "task": {
                    "task_id": "052",
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
                    "session_id": "worker-policy",
                    "tool_name": "Edit",
                    "tool_input": {
                        "file_path": str(self.root / task_path),
                        "old_string": '"integration_route": "auto_in_discussion"',
                        "new_string": '"integration_route": "decision_required"',
                    },
                }
            ),
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            check=True,
        )
        payload = json.loads(process.stdout)
        self.assertEqual(payload["hookSpecificOutput"]["permissionDecision"], "deny")
        reason = payload["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("valid authority", reason)
        self.assertNotIn("integration_route", reason)

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
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        payload = json.loads(process.stdout)
        self.assertEqual(payload["hookSpecificOutput"]["permissionDecision"], "deny")
        reason = payload["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("not authorized", reason)
        self.assertNotIn("Claim", reason)

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
            encoding="utf-8",
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
            encoding="utf-8",
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
                encoding="utf-8",
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

    def test_powershell_write_commands_and_aliases_enter_existing_gate(self) -> None:
        commands = {
            "Set-Content -Path src/app.py -Value updated": {"src/app.py"},
            "'value' | Out-File -FilePath src/output.txt": {"src/output.txt"},
            "Add-Content src/app.py updated": {"src/app.py"},
            "Remove-Item -LiteralPath src/old.py -Force": {"src/old.py"},
            "Copy-Item -Path src/app.py -Destination src/copy.py": {
                "src/app.py",
                "src/copy.py",
            },
            "Move-Item src/old.py src/new.py": {"src/old.py", "src/new.py"},
            "New-Item -Path src -Name generated.py -ItemType File": {
                "src/generated.py"
            },
            "Clear-Content -Path src/app.py": {"src/app.py"},
            "Rename-Item -Path src/old.py -NewName new.py": {
                "src/old.py",
                "src/new.py",
            },
            "'value' | Tee-Object -FilePath src/tee.txt": {"src/tee.txt"},
            "Invoke-WebRequest https://example.invalid -OutFile src/download.bin": {
                "src/download.bin"
            },
            'powershell -NoProfile -Command "Set-Content -Path src/wrapped.py -Value updated"': {
                "src/wrapped.py"
            },
            'pwsh -Command "Move-Item src/old.py src/wrapped-new.py"': {
                "src/old.py",
                "src/wrapped-new.py",
            },
        }
        for command, expected_paths in commands.items():
            with self.subTest(command=command):
                classified = memory_sync.classify_tool_operation(
                    self.root,
                    self.config,
                    {"tool_name": "Bash", "tool_input": {"command": command}},
                )
                self.assertIsNotNone(classified)
                assert classified is not None
                self.assertEqual(classified[0], "business_write")
                self.assertEqual(
                    set(classified[1].removeprefix("business_paths:").splitlines()),
                    expected_paths,
                )

        aliases = (
            "sc src/app.py updated",
            "ac src/app.py updated",
            "ri src/app.py",
            "cpi src/app.py src/copy.py",
            "mi src/app.py src/moved.py",
            "ni src/generated.py",
            "del src/app.py",
            "erase src/app.py",
            "rd src/generated",
            "rmdir src/generated",
            "copy src/app.py src/copy.py",
            "move src/app.py src/moved.py",
            "clc src/app.py",
            "rni src/app.py renamed.py",
            "ren src/app.py renamed.py",
            "iwr https://example.invalid -OutFile src/download.bin",
        )
        for command in aliases:
            with self.subTest(alias=command):
                classified = memory_sync.classify_tool_operation(
                    self.root,
                    self.config,
                    {"tool_name": "shell", "tool_input": {"command": command}},
                )
                self.assertIsNotNone(classified)
                assert classified is not None
                self.assertEqual(classified[0], "business_write")

    def test_opaque_powershell_write_fails_closed_as_business_write(self) -> None:
        classified = memory_sync.classify_tool_operation(
            self.root,
            self.config,
            {
                "tool_name": "exec_command",
                "tool_input": {"command": "Set-Content -Value updated"},
            },
        )
        self.assertEqual(classified, ("business_write", ""))

        encoded = memory_sync.classify_tool_operation(
            self.root,
            self.config,
            {
                "tool_name": "exec_command",
                "tool_input": {"command": "powershell -EncodedCommand ZgBvAG8A"},
            },
        )
        self.assertEqual(encoded, ("opaque_write", ""))

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
            encoding="utf-8",
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
                encoding="utf-8",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            return json.loads(process.stdout)

        self.assertEqual(invoke(own_task), {})
        denied = invoke(other_task)
        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_integration_lease_cli_requires_discussion_integrating_runtime(self) -> None:
        transition = self.prepare_safe_integration(
            "002", "discussion-cli", "integration-cli"
        )
        grant_id = transition["grant"]["grant_id"]
        process = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "integration-lease",
                "acquire",
                "--session-id",
                "discussion-cli",
                "--grant-id",
                grant_id,
                "--integration-id",
                "integration-cli",
                "--task-id",
                "002",
                "--report",
                "reports/runs/002-attempt-1.md",
                "--allow-dirty",
            ],
            cwd=self.root,
            text=True,
            encoding="utf-8",
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
        run = memory_sync.read_execution_run(self.root, "002-attempt-1")
        assert run is not None
        self.assertEqual(run["phase"], "integrating")
        self.assertEqual(
            run["integration"]["lease_id"], payload["lease"]["lease_id"]
        )

        premature_release = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "integration-lease",
                "release",
                "--session-id",
                "discussion-cli",
            ],
            cwd=self.root,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(premature_release.returncode, 1)
        self.assertEqual(
            json.loads(premature_release.stdout)["error"],
            "integrated_report_not_in_head",
        )
        lease = memory_sync.inspect_integration_lease(self.root)
        assert lease is not None
        self.assertEqual(lease["lease_status"], "active")
        run = memory_sync.read_execution_run(self.root, "002-attempt-1")
        assert run is not None
        self.assertEqual(run["phase"], "integrating")

        self.git("cherry-pick", run["result"]["commit"])
        released = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "integration-lease",
                "release",
                "--session-id",
                "discussion-cli",
            ],
            cwd=self.root,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        self.assertTrue(json.loads(released.stdout)["ok"])
        run = memory_sync.read_execution_run(self.root, "002-attempt-1")
        assert run is not None
        self.assertEqual(run["phase"], "integrated")
        lease = memory_sync.inspect_integration_lease(self.root)
        assert lease is not None
        self.assertEqual(lease["lease_status"], "released")

    def test_integration_acquire_preserves_lease_when_run_rollback_fails(self) -> None:
        transition = self.prepare_safe_integration(
            "002", "discussion-rollback", "integration-rollback"
        )
        args = mock.Mock(
            lease_action="acquire",
            session_id="discussion-rollback",
            grant_id=transition["grant"]["grant_id"],
            integration_id="integration-rollback",
            task_id=["002"],
            report=["reports/runs/002-attempt-1.md"],
            allow_dirty=True,
        )
        host_adapter_module = sys.modules["host_adapter"]
        with (
            mock.patch.object(
                host_adapter_module,
                "find_git_root",
                return_value=self.root,
            ),
            mock.patch.object(
                host_adapter_module,
                "update_execution_run",
                return_value={"ok": False, "error": "injected_update_failure"},
            ),
            mock.patch.object(
                host_adapter_module,
                "_restore_integration_runs",
                return_value=[{"ok": False, "error": "injected_rollback_failure"}],
            ),
            mock.patch.object(
                host_adapter_module, "update_integration_lease"
            ) as lease_update,
            mock.patch("builtins.print") as printed,
        ):
            exit_code = host_adapter_module.integration_lease_main(args)

        self.assertEqual(exit_code, 1)
        lease_update.assert_not_called()
        payload = json.loads(printed.call_args.args[0])
        self.assertTrue(payload["lease_preserved"])
        lease = memory_sync.inspect_integration_lease(self.root)
        assert lease is not None
        self.assertEqual(lease["lease_status"], "active")

    def test_integration_transition_rejects_missing_task_and_report(self) -> None:
        memory_sync.write_session_runtime(
            self.root,
            "discussion-missing-evidence",
            {
                "session": {
                    "session_id": "discussion-missing-evidence",
                    "role": "discussion",
                    "host": "codex",
                    "phase": "integration_pending",
                    "expected_transition": {
                        "kind": "auto_integrate",
                        "task_id": "099",
                        "report_id": "reports/runs/099.md",
                    },
                },
                "session_provenance": {
                    "initial_role": "neutral",
                    "discussion_authorized": True,
                },
                "task": {
                    "task_id": "099",
                    "lifecycle": "completed",
                    "worker_authorized": True,
                    "run_report": "reports/runs/099.md",
                },
            },
        )
        transition = memory_sync.transition_session_runtime(
            self.root,
            self.config,
            "discussion-missing-evidence",
            "integration_evaluated",
            {
                "outcome": "safe",
                "integration_id": "integration-missing",
                "task_ids": ["099"],
                "reports": ["reports/runs/099.md"],
            },
        )
        self.assertFalse(transition["ok"])
        self.assertEqual(transition["error"], "integration_evidence_not_safe")

    def test_integration_grant_is_one_time_and_exactly_bound(self) -> None:
        transition = self.prepare_safe_integration(
            "053", "discussion-grant", "integration-grant"
        )
        grant_id = transition["grant"]["grant_id"]
        mismatches = (
            {"integration_id": "integration-other"},
            {"task_ids": ["053a"]},
            {"reports": ["reports/runs/053-other.md"]},
            {"branch": "wrong-branch"},
            {"worktree": str(self.root.parent.resolve())},
        )
        for override in mismatches:
            with self.subTest(override=override):
                arguments = {
                    "session_id": "discussion-grant",
                    "grant_id": grant_id,
                    "integration_id": "integration-grant",
                    "task_ids": ["053"],
                    "reports": ["reports/runs/053-attempt-1.md"],
                    "require_clean": False,
                    **override,
                }
                mismatch = memory_sync.acquire_integration_lease(
                    self.root, **arguments
                )
                self.assertFalse(mismatch["ok"])
                self.assertEqual(
                    mismatch["error"], "integration_transition_grant_mismatch"
                )
        acquired = memory_sync.acquire_integration_lease(
            self.root,
            session_id="discussion-grant",
            grant_id=grant_id,
            integration_id="integration-grant",
            task_ids=["053"],
            reports=["reports/runs/053-attempt-1.md"],
            require_clean=False,
        )
        self.assertTrue(acquired["ok"], acquired)
        released = memory_sync.update_integration_lease(
            self.root,
            "release",
            session_id="discussion-grant",
            branch=acquired["lease"]["base_branch"],
            worktree=acquired["lease"]["worktree"],
        )
        self.assertTrue(released["ok"], released)
        replay = memory_sync.acquire_integration_lease(
            self.root,
            session_id="discussion-grant",
            grant_id=grant_id,
            integration_id="integration-grant",
            task_ids=["053"],
            reports=["reports/runs/053-attempt-1.md"],
            require_clean=False,
        )
        self.assertFalse(replay["ok"])
        self.assertEqual(replay["error"], "integration_transition_grant_consumed")

    def test_active_worker_claim_blocks_integration_transition(self) -> None:
        task_id = "054"
        task_path = f"tasks/build/{task_id}-active.md"
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
        self.git("commit", "-qm", "authorize active claim fixture")
        claimed = memory_sync.acquire_claim(
            self.root,
            task_id,
            1,
            "worker-054",
            discussion_session_id="discussion-active",
            require_clean=True,
        )
        self.assertTrue(claimed["ok"], claimed)
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
                f"{task_id}-attempt-1",
                task_id=task_id,
                changed_paths=["src/app.py"],
            ),
        )
        memory_sync.write_session_runtime(
            self.root,
            "discussion-active",
            {
                "session": {
                    "session_id": "discussion-active",
                    "role": "discussion",
                    "host": "codex",
                    "phase": "integration_pending",
                    "expected_transition": {
                        "kind": "auto_integrate",
                        "task_id": task_id,
                        "report_id": report_path,
                    },
                },
                "session_provenance": {
                    "initial_role": "neutral",
                    "discussion_authorized": True,
                },
                "task": {
                    "task_id": task_id,
                    "lifecycle": "completed",
                    "worker_authorized": True,
                    "run_report": report_path,
                },
            },
        )
        transition = memory_sync.transition_session_runtime(
            self.root,
            self.config,
            "discussion-active",
            "integration_evaluated",
            {
                "outcome": "safe",
                "integration_id": "integration-active",
                "task_ids": [task_id],
                "reports": [report_path],
            },
        )
        self.assertFalse(transition["ok"])
        self.assertEqual(transition["error"], "active_worker_claim_exists")

    def test_safe_grant_cannot_be_reused_after_evidence_becomes_high_risk(self) -> None:
        transition = self.prepare_safe_integration(
            "055", "discussion-risk", "integration-risk"
        )
        task_path = "tasks/build/055-integration.md"
        report_path = "reports/runs/055-attempt-1.md"
        self.write(
            task_path,
            self.execution_ready_task(
                "055",
                status="completed",
                work_type="high_risk",
                worker_authorized=True,
                integration_policy="decision_required",
                run_report=report_path,
            ),
        )
        self.write(
            report_path,
            self.structured_run_report(
                "055-attempt-1",
                task_id="055",
                work_type="high_risk",
                changed_paths=["src/app.py"],
                security_impact=True,
            ),
        )
        process = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "integration-lease",
                "acquire",
                "--session-id",
                "discussion-risk",
                "--grant-id",
                transition["grant"]["grant_id"],
                "--integration-id",
                "integration-risk",
                "--task-id",
                "055",
                "--report",
                report_path,
                "--allow-dirty",
            ],
            cwd=self.root,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(process.returncode, 1)
        payload = json.loads(process.stdout)
        self.assertFalse(payload["ok"])
        self.assertIn(
            payload["error"],
            {"integration_evidence_not_safe", "integration_run_report_invalid"},
        )

    def test_pre_tool_use_allows_discussion_local_integration_merge_with_lease(self) -> None:
        transition = self.prepare_safe_integration(
            "002", "discussion-1", "integration-1"
        )
        acquired = memory_sync.acquire_integration_lease(
            self.root,
            session_id="discussion-1",
            grant_id=transition["grant"]["grant_id"],
            integration_id="integration-1",
            task_ids=["002"],
            reports=["reports/runs/002-attempt-1.md"],
            require_clean=False,
        )
        self.assertTrue(acquired["ok"])
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
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        self.assertEqual(json.loads(process.stdout), {})
