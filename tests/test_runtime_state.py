from tests.wishgraph_test_support import *  # noqa: F401,F403

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
                "claude_worker_provider.py",
                "tool_gate_provider.py",
            ):
                shutil.copy2(HOOK_ASSETS / runtime_name, hooks / runtime_name)

            process = subprocess.run(
                [sys.executable, str(hooks / "memory_sync.py"), "session-start"],
                cwd=root,
                input=json.dumps({"cwd": str(root)}),
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )

            payload = json.loads(process.stdout)
            self.assertIn("hookSpecificOutput", payload)
            self.assertIn(
                "needs a minimal project handoff",
                payload["hookSpecificOutput"]["additionalContext"],
            )

class RuntimeStateTests(MemorySyncTestCase):
    def test_integration_lease_reads_terminal_report_from_worker_commit(self) -> None:
        task_id = "071"
        discussion_id = "discussion-071"
        worker_id = "worker-071"
        task_path = f"tasks/build/{task_id}-cross-worktree.md"
        report_path = f"reports/runs/{task_id}-attempt-1.md"
        task_content = self.execution_ready_task(
            task_id,
            status="approved",
            worker_authorized=True,
            run_report=report_path,
        )
        self.write(task_path, task_content)
        self.git("add", task_path)
        self.git("commit", "-qm", "prepare cross-worktree integration")
        base_commit = self.git("rev-parse", "HEAD").stdout.strip()
        runtime = memory_sync.write_session_runtime(
            self.root,
            discussion_id,
            {
                "session": {
                    "session_id": discussion_id,
                    "role": "discussion",
                    "host": "codex",
                    "phase": "waiting_for_worker",
                    "expected_transition": {"kind": "wait_for_worker", "task_id": task_id},
                },
                "session_provenance": {
                    "initial_role": "neutral",
                    "host": "codex",
                    "discussion_authorized": True,
                },
                "task": {
                    "task_id": task_id,
                    "lifecycle": "approved",
                    "attempt": 1,
                    "worker_authorized": True,
                    "run_report": report_path,
                },
            },
        )
        self.assertTrue(runtime["ok"], runtime)
        run = memory_sync.update_execution_run(
            self.root,
            task_id=task_id,
            attempt=1,
            create=True,
            patch={
                "phase": "dispatching",
                "task_path": task_path,
                "run_report": report_path,
                "base_commit": base_commit,
                "task_fingerprint": memory_sync.content_fingerprint(task_content),
                "authorization": {
                    "authorized": True,
                    "event": "test_authorization",
                    "source_session_id": discussion_id,
                    "parent_discussion_id": discussion_id,
                    "host": "codex",
                    "dispatch_mode": "background_worker",
                },
            },
        )
        self.assertTrue(run["ok"], run)

        worker_root = Path(tempfile.mkdtemp(prefix="wishgraph-worker-071-"))
        worker_root.rmdir()
        self.addCleanup(shutil.rmtree, worker_root, True)
        self.git("worktree", "add", "-q", "-b", "worker-071", str(worker_root), "HEAD")
        claimed = memory_sync.acquire_claim(
            worker_root,
            task_id,
            1,
            worker_id,
            host_thread_ref=worker_id,
            agent_platform="codex",
            discussion_session_id=discussion_id,
            container_kind="codex_agent_thread",
            agent_kind="formal_worker",
            allowed_scope=["src/worker_071.py"],
            validation_plan=["focused test"],
            require_clean=True,
        )
        self.assertTrue(claimed["ok"], claimed)
        running = memory_sync.update_execution_run(
            worker_root,
            task_id=task_id,
            attempt=1,
            patch={
                "phase": "running",
                "claim_id": claimed["claim"]["claim_id"],
                "worker": {
                    "host": "codex",
                    "container_kind": "codex_agent_thread",
                    "thread_or_session_id": worker_id,
                    "branch": claimed["claim"]["branch"],
                    "worktree": claimed["claim"]["worktree"],
                },
            },
        )
        self.assertTrue(running["ok"], running)
        worker_source = worker_root / "src" / "worker_071.py"
        worker_source.parent.mkdir(parents=True, exist_ok=True)
        worker_source.write_text("print('worker result')\n", encoding="utf-8")
        worker_report = worker_root / report_path
        worker_report.parent.mkdir(parents=True, exist_ok=True)
        worker_report.write_text(
            self.structured_run_report(
                f"{task_id}-attempt-1",
                task_id=task_id,
                changed_paths=["src/worker_071.py"],
            ),
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "-C", str(worker_root), "add", "src/worker_071.py", report_path],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(worker_root), "commit", "-qm", "worker result 071"],
            check=True,
        )
        released = memory_sync.update_claim(
            worker_root,
            claimed["claim"]["claim_id"],
            "release",
            branch=claimed["claim"]["branch"],
            worktree=claimed["claim"]["worktree"],
        )
        self.assertTrue(released["ok"], released)
        notified = memory_sync.enqueue_terminal_notification_from_claim(
            worker_root, self.config, released["claim"]
        )
        self.assertTrue(notified["ok"], notified)
        terminal_run = memory_sync.latest_execution_run(self.root, task_id, attempt=1)
        assert terminal_run is not None
        result_commit = terminal_run["result"]["commit"]
        self.assertEqual(terminal_run["base_commit"], base_commit)
        self.assertEqual(
            self.git("rev-parse", f"{result_commit}^").stdout.strip(), base_commit
        )
        self.assertFalse((self.root / report_path).exists())

        context = memory_sync.consume_discussion_notification_context(
            self.root, discussion_id
        )
        self.assertIn(task_id, context)
        transition = memory_sync.transition_session_runtime(
            self.root,
            self.config,
            discussion_id,
            "integration_evaluated",
            {
                "outcome": "safe",
                "integration_id": "integration-071",
                "task_ids": [task_id],
                "reports": [report_path],
            },
        )
        self.assertTrue(transition["ok"], transition)
        grant = transition["grant"]
        lease = memory_sync.acquire_integration_lease(
            self.root,
            session_id=discussion_id,
            grant_id=grant["grant_id"],
            integration_id="integration-071",
            task_ids=[task_id],
            reports=[report_path],
            require_clean=True,
        )
        self.assertTrue(lease["ok"], lease)
        subprocess.run(
            [
                "git",
                "-C",
                str(self.root),
                "cherry-pick",
                "--no-commit",
                result_commit,
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.write(
            task_path,
            self.execution_ready_task(
                task_id,
                status="integrated",
                worker_authorized=True,
                run_report=report_path,
            ),
        )
        self.write("reports/PROJECT_STATUS.md", self.overview([report_path]))
        self.write("prompts/DISCUSSION_AI.md", self.discussion("integration-071"))
        self.git("add", task_path, report_path, "src/worker_071.py")
        self.git("add", "reports/PROJECT_STATUS.md", "prompts/DISCUSSION_AI.md")
        checked = memory_sync.check_sync(self.root, self.config, "staged")
        self.assertTrue(checked.ok, checked.errors)
        revoked = memory_sync.update_integration_lease(
            self.root, "revoke", session_id=discussion_id
        )
        self.assertTrue(revoked["ok"], revoked)

    def test_clean_repo_passes(self) -> None:
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertTrue(result.ok, result.errors)

    def test_chinese_report_status_is_machine_readable(self) -> None:
        self.assertEqual(memory_sync.parse_report_status("- 状态：Completed\n"), "completed")

    def test_structured_run_state_is_canonical(self) -> None:
        content = self.structured_run_report("structured-001")
        state = memory_sync.report_state("reports/runs/structured-001.md", content)
        self.assertEqual(state.status, "completed")
        self.assertEqual(state.readiness, "ready")
        self.assertEqual(state.safety_errors, [])

    def test_new_integration_route_and_recommendation_fields_are_canonical(self) -> None:
        task_content = self.structured_task(
            "061",
            status="approved",
            worker_execution_profiles={
                "codex": {
                    "model": "gpt-5.6-sol",
                    "reasoning_effort": "high",
                }
            },
        )
        task = memory_sync.parse_task_state("tasks/build/061.md", task_content)
        self.assertEqual(task.integration_policy, "inherited_task_approval")
        self.assertEqual(
            task.worker_execution_profiles,
            {
                "codex": {
                    "model": "gpt-5.6-sol",
                    "reasoning_effort": "high",
                }
            },
        )

        report_content = self.structured_run_report("061-attempt-1")
        report = memory_sync.report_state(
            "reports/runs/061-attempt-1.md", report_content
        )
        self.assertEqual(report.authorization, "inherited_task_approval")
        self.assertEqual(report.safety_errors, [])

    def test_retired_integration_field_aliases_fail_closed(self) -> None:
        task_content = self.structured_task("063").replace(
            '"integration_route": "auto_in_discussion"',
            '"integration_policy": "inherited_task_approval"',
        )
        task = memory_sync.parse_task_state("tasks/build/063.md", task_content)
        self.assertIn(
            "integration_route must be auto_in_discussion or decision_required",
            task.errors,
        )

        report_content = self.structured_run_report("063-attempt-1").replace(
            '"integration_recommendation": "safe_for_discussion_integration"',
            '"integration_authorization": "inherited_task_approval"',
        )
        report = memory_sync.report_state(
            "reports/runs/063-attempt-1.md", report_content
        )
        self.assertIn(
            "integration_recommendation must be safe_for_discussion_integration, decision_required, or blocked",
            report.safety_errors,
        )

    def test_worker_report_recommendation_cannot_downgrade_high_risk_route(self) -> None:
        content = self.structured_run_report(
            "062-attempt-1", work_type="high_risk"
        ).replace(
            '"integration_recommendation": "decision_required"',
            '"integration_recommendation": "safe_for_discussion_integration"',
        )
        report = memory_sync.report_state("reports/runs/062-attempt-1.md", content)
        self.assertIn(
            "high-risk work requires a decision-required integration recommendation",
            report.safety_errors,
        )

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
            encoding="utf-8",
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
            encoding="utf-8",
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
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(process.returncode, 1)
        payload = json.loads(process.stdout)
        self.assertEqual(payload["error"], "duplicate_task_id")
        self.assertEqual(len(payload["matches"]), 2)

    def test_exact_task_resolution_does_not_read_unrelated_task_bodies(self) -> None:
        self.write("tasks/build/008-target.md", self.structured_task("008-target"))
        self.write("tasks/build/099-unrelated.md", self.structured_task("099-unrelated"))
        with mock.patch("host_adapter.read_version", wraps=memory_sync.read_version) as read:
            payload = memory_sync.resolve_task(self.root, self.config, "008")
        self.assertTrue(payload["ok"], payload)
        read_paths = {str(call.args[1]) for call in read.call_args_list}
        self.assertIn("tasks/build/008-target.md", read_paths)
        self.assertNotIn("tasks/build/099-unrelated.md", read_paths)

    def test_execution_preflight_reads_only_exact_task_and_dependencies(self) -> None:
        self.write(
            "tasks/build/001-dependency.md",
            self.structured_task(
                "001-dependency", status="integrated", worker_authorized=True
            ),
        )
        self.write(
            "tasks/build/008-target.md",
            self.execution_ready_task("008-target", dependencies=["001"]),
        )
        self.write("tasks/build/099-unrelated.md", self.structured_task("099-unrelated"))
        with mock.patch("policy.read_version", wraps=memory_sync.read_version) as read:
            _, errors = memory_sync.evaluate_execution_preflight(
                self.root, self.config, "tasks/build/008-target.md", "execute"
            )
        self.assertEqual(errors, [])
        read_paths = {str(call.args[1]) for call in read.call_args_list}
        self.assertIn("tasks/build/008-target.md", read_paths)
        self.assertIn("tasks/build/001-dependency.md", read_paths)
        self.assertNotIn("tasks/build/099-unrelated.md", read_paths)

    def test_discussion_fast_context_does_not_scan_active_tasks_or_reports(self) -> None:
        config = json.loads(json.dumps(self.config))
        with mock.patch(
            "host_adapter.integration_state",
            side_effect=AssertionError("default Discussion context must stay bounded"),
        ):
            context = memory_sync.project_session_context(self.root, config)
        self.assertIsNotNone(context)
        self.assertIn("Current integrated project status", context)

    def test_exact_revision_resolution_reads_only_its_parent_revision_family(self) -> None:
        self.write("tasks/build/012-parent.md", self.structured_task("012-parent"))
        template = (HOOK_ASSETS.parent / "templates" / "TASK_REVISION.md").read_text(
            encoding="utf-8"
        )
        self.write(
            "tasks/revisions/012-r1.md",
            template,
        )
        self.write(
            "tasks/revisions/099-r1.md",
            template.replace("012-r1", "099-r1").replace(
                '"parent_task_id": "012"', '"parent_task_id": "099"'
            ),
        )
        with mock.patch("host_adapter.read_version", wraps=memory_sync.read_version) as read:
            payload = memory_sync.resolve_revision(self.root, self.config, "012-r1")
        self.assertTrue(payload["ok"], payload)
        read_paths = {str(call.args[1]) for call in read.call_args_list}
        self.assertIn("tasks/revisions/012-r1.md", read_paths)
        self.assertNotIn("tasks/revisions/099-r1.md", read_paths)

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

    def test_authority_timestamps_treat_naive_values_as_utc(self) -> None:
        parsed = memory_sync.parse_timestamp("2026-07-21T12:34:56")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.utcoffset().total_seconds(), 0)
        self.assertEqual(parsed.isoformat(), "2026-07-21T12:34:56+00:00")

    def test_corrupt_claim_is_visible_and_blocks_replacement_authority(self) -> None:
        claim_dir = memory_sync.claim_root(self.root) / "028c"
        claim_dir.mkdir(parents=True)
        claim_path = claim_dir / "broken-claim.json"
        claim_path.write_text("{", encoding="utf-8")

        claims = memory_sync.inspect_claims(self.root, "028c")
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["record_status"], "invalid")
        self.assertEqual(claims[0]["invalid_reason"], "claim_record_invalid_json")
        self.assertEqual(claims[0]["record_path"], str(claim_path))

        blocked = memory_sync.acquire_claim(
            self.root, "028c", 1, "replacement-worker", require_clean=True
        )
        self.assertFalse(blocked["ok"], blocked)
        self.assertEqual(blocked["error"], "invalid_claim_record")

    def test_initial_claim_record_uses_existing_atomic_writer(self) -> None:
        git_state_module = sys.modules["git_state"]
        with mock.patch.object(
            git_state_module,
            "_atomic_claim_update",
            wraps=git_state_module._atomic_claim_update,
        ) as atomic_write:
            acquired = memory_sync.acquire_claim(
                self.root, "028d", 1, "atomic-worker", require_clean=True
            )
        self.assertTrue(acquired["ok"], acquired)
        claim_id = acquired["claim"]["claim_id"]
        destinations = [call.args[0] for call in atomic_write.call_args_list]
        self.assertIn(
            memory_sync.claim_root(self.root) / "028d" / f"{claim_id}.json",
            destinations,
        )

    def test_mutex_release_checks_owner_token_after_stale_takeover(self) -> None:
        git_state_module = sys.modules["git_state"]
        mutex_dir = memory_sync.git_common_dir(self.root) / "wishgraph" / "mutex-test"
        original = git_state_module._claim_mutex(mutex_dir)
        mutex_path = original[0]
        stale_time = time.time() - 60
        os.utime(mutex_path, (stale_time, stale_time))
        replacement = git_state_module._claim_mutex(mutex_dir)
        try:
            git_state_module._release_claim_mutex(original)
            self.assertTrue(mutex_path.is_file())
            self.assertEqual(
                mutex_path.read_text(encoding="utf-8").split(maxsplit=1)[0],
                replacement[1],
            )
        finally:
            git_state_module._release_claim_mutex(replacement)
        self.assertFalse(mutex_path.exists())

    def test_detached_head_cannot_acquire_worker_claim(self) -> None:
        wrong_branch = memory_sync.acquire_claim(
            self.root,
            "028e",
            1,
            "wrong-branch-worker",
            branch="not-the-current-branch",
            require_clean=True,
        )
        self.assertFalse(wrong_branch["ok"], wrong_branch)
        self.assertEqual(wrong_branch["error"], "claim_branch_mismatch")
        wrong_worktree = memory_sync.acquire_claim(
            self.root,
            "028e",
            1,
            "wrong-worktree-worker",
            worktree=str(self.root.parent),
            require_clean=True,
        )
        self.assertFalse(wrong_worktree["ok"], wrong_worktree)
        self.assertEqual(wrong_worktree["error"], "claim_worktree_mismatch")

        self.git("checkout", "--detach", "-q")
        blocked = memory_sync.acquire_claim(
            self.root, "028e", 1, "detached-worker", require_clean=True
        )
        self.assertFalse(blocked["ok"], blocked)
        self.assertEqual(blocked["error"], "detached_head_not_supported")

        memory_sync.write_session_runtime(
            self.root,
            "detached-discussion",
            {
                "session": {
                    "session_id": "detached-discussion",
                    "role": "discussion",
                    "phase": "integrating",
                },
                "session_provenance": {
                    "initial_role": "neutral",
                    "discussion_authorized": True,
                },
            },
        )
        grant = memory_sync.create_integration_transition_grant(
            self.root,
            session_id="detached-discussion",
            integration_id="detached-integration",
            task_ids=["028e"],
            reports=["reports/runs/028e-attempt-1.md"],
            outcome="safe",
        )
        self.assertFalse(grant["ok"], grant)
        self.assertEqual(grant["error"], "detached_head_not_supported")

    def test_corrupt_execution_run_is_visible_and_cannot_be_recreated(self) -> None:
        run_id = "028f-attempt-1"
        run_path = memory_sync.execution_run_root(self.root) / f"{run_id}.json"
        run_path.parent.mkdir(parents=True)
        run_path.write_text("{", encoding="utf-8")

        run = memory_sync.read_execution_run(self.root, run_id)
        assert run is not None
        self.assertEqual(run["record_status"], "invalid")
        self.assertEqual(run["invalid_reason"], "execution_run_invalid_json")
        visible = memory_sync.inspect_execution_runs(self.root, "028f")
        self.assertEqual([item["run_id"] for item in visible], [run_id])
        latest = memory_sync.latest_execution_run(self.root, "028f", attempt=1)
        assert latest is not None
        self.assertEqual(latest["record_status"], "invalid")

        blocked = memory_sync.update_execution_run(
            self.root,
            task_id="028f",
            attempt=1,
            patch={"phase": "dispatching"},
            create=True,
        )
        self.assertFalse(blocked["ok"], blocked)
        self.assertEqual(blocked["error"], "invalid_execution_run_record")

    def test_corrupt_integration_lease_is_visible_and_blocks_new_claim(self) -> None:
        lease_path = memory_sync.integration_runtime_root(self.root) / "lease.json"
        lease_path.parent.mkdir(parents=True)
        lease_path.write_text("{", encoding="utf-8")

        lease = memory_sync.inspect_integration_lease(self.root)
        assert lease is not None
        self.assertEqual(lease["record_status"], "invalid")
        self.assertEqual(lease["invalid_reason"], "integration_lease_invalid_json")

        blocked = memory_sync.acquire_claim(
            self.root, "028g", 1, "worker-with-corrupt-lease", require_clean=True
        )
        self.assertFalse(blocked["ok"], blocked)
        self.assertEqual(blocked["error"], "invalid_integration_lease_record")

    def test_incomplete_integration_lease_identity_fails_closed(self) -> None:
        lease_path = memory_sync.integration_runtime_root(self.root) / "lease.json"
        lease_path.parent.mkdir(parents=True)
        lease_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "kind": "integration_lease",
                    "lease_status": "active",
                    "updated_at": "2026-07-18T00:00:00Z",
                }
            ),
            encoding="utf-8",
        )
        lease = memory_sync.inspect_integration_lease(self.root)
        assert lease is not None
        self.assertEqual(lease["record_status"], "invalid")
        self.assertEqual(lease["invalid_reason"], "integration_lease_identity_invalid")

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
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        context = json.loads(process.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("needs attention before integration", context)
        self.assertIn("029b", context)
        self.assertNotIn("claim-029b", context)
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
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        context = json.loads(process.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Task 029b is ready", context)
        self.assertNotIn("auto_integrate", context)
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
                "completed",
                {"public_api_change": True},
            ),
        )
        for task_id, lifecycle, work_type, expected_event, report_options in cases:
            with self.subTest(task_id=task_id):
                task_path = f"tasks/build/{task_id}-notification.md"
                report_path = f"reports/runs/{task_id}-attempt-1.md"
                self.write(
                    task_path,
                    self.structured_task(
                        task_id,
                        status="approved",
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
                self.git("add", task_path)
                self.git("commit", "-qm", f"authorize terminal evidence {task_id}")
                self.authorize_execution_run(
                    task_id,
                    task_path,
                    "discussion-terminal",
                    host="codex",
                    report_path=report_path,
                )
                self.write(
                    task_path,
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
                self.git(
                    "add",
                    task_path,
                    report_path,
                )
                self.git("commit", "-qm", f"terminal evidence {task_id}")
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
        self.authorize_execution_run(
            task_id,
            task_path,
            "discussion-029f",
            host="codex",
            report_path=report_path,
            dispatch_mode="current_window",
            source_session_id="worker-029f",
        )
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
            encoding="utf-8",
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
            encoding="utf-8",
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
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(released.returncode, 1)
        payload = json.loads(released.stdout)
        self.assertEqual(payload["error"], "terminal_notification_preflight_failed")
        claim = memory_sync.inspect_claims(self.root, "029g")[0]
        self.assertEqual(claim["lease_status"], "active")
        self.assertEqual(memory_sync.inspect_worker_notifications(self.root), [])

    def test_claim_release_rejects_report_not_present_in_result_commit(self) -> None:
        task_id = "029h"
        task_path = f"tasks/build/{task_id}-uncommitted-report.md"
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
        self.git("commit", "-qm", "prepare uncommitted report task")
        self.authorize_execution_run(
            task_id,
            task_path,
            "discussion-029h",
            host="codex",
            report_path=report_path,
            dispatch_mode="current_window",
            source_session_id="worker-029h",
        )
        acquired = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "claim",
                "acquire",
                task_id,
                "--worker-id",
                "worker-029h",
                "--session-id",
                "worker-029h",
                "--host",
                "codex",
            ],
            cwd=self.root,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        claim_id = json.loads(acquired.stdout)["claim"]["claim_id"]
        self.write(
            report_path,
            self.structured_run_report(f"{task_id}-attempt-1", task_id=task_id),
        )
        self.git("add", report_path)
        released = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "claim",
                "release",
                claim_id,
                "--session-id",
                "worker-029h",
            ],
            cwd=self.root,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(released.returncode, 1)
        payload = json.loads(released.stdout)
        self.assertEqual(
            payload["detail"]["error"], "terminal_run_report_not_committed"
        )
        claim = memory_sync.inspect_claims(self.root, task_id)[0]
        self.assertEqual(claim["lease_status"], "active")

    def test_claim_release_rejects_multi_commit_worker_result(self) -> None:
        task_id = "029j"
        task_path = f"tasks/build/{task_id}-multi-commit.md"
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
        self.git("commit", "-qm", "prepare multi commit task")
        self.authorize_execution_run(
            task_id,
            task_path,
            "discussion-029j",
            host="codex",
            report_path=report_path,
            dispatch_mode="current_window",
            source_session_id="worker-029j",
        )
        acquired = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "claim",
                "acquire",
                task_id,
                "--worker-id",
                "worker-029j",
                "--session-id",
                "worker-029j",
                "--host",
                "codex",
            ],
            cwd=self.root,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        claim_id = json.loads(acquired.stdout)["claim"]["claim_id"]
        self.write("src/multi_commit.py", "print('first commit')\n")
        self.git("add", "src/multi_commit.py")
        self.git("commit", "-qm", "worker implementation commit")
        self.write(
            report_path,
            self.structured_run_report(
                f"{task_id}-attempt-1",
                task_id=task_id,
                changed_paths=["src/multi_commit.py"],
            ),
        )
        self.git("add", report_path)
        self.git("commit", "-qm", "worker report commit")
        released = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "claim",
                "release",
                claim_id,
                "--session-id",
                "worker-029j",
            ],
            cwd=self.root,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(released.returncode, 1)
        payload = json.loads(released.stdout)
        self.assertEqual(
            payload["detail"]["error"], "terminal_result_commit_not_based_on_run"
        )
        claim = memory_sync.inspect_claims(self.root, task_id)[0]
        self.assertEqual(claim["lease_status"], "active")

    def test_claim_release_rejects_uncommitted_business_changes(self) -> None:
        task_id = "029k"
        task_path = f"tasks/build/{task_id}-dirty-worker.md"
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
        self.git("commit", "-qm", "prepare dirty worker task")
        self.authorize_execution_run(
            task_id,
            task_path,
            "discussion-029k",
            host="codex",
            report_path=report_path,
            dispatch_mode="current_window",
            source_session_id="worker-029k",
        )
        acquired = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "claim",
                "acquire",
                task_id,
                "--worker-id",
                "worker-029k",
                "--session-id",
                "worker-029k",
                "--host",
                "codex",
            ],
            cwd=self.root,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        claim_id = json.loads(acquired.stdout)["claim"]["claim_id"]
        self.write("src/dirty_worker.py", "print('committed')\n")
        self.write(
            report_path,
            self.structured_run_report(
                f"{task_id}-attempt-1",
                task_id=task_id,
                changed_paths=["src/dirty_worker.py"],
            ),
        )
        self.git("add", "src/dirty_worker.py", report_path)
        self.git("commit", "-qm", "complete dirty worker result")
        self.write("src/left_behind.py", "print('uncommitted')\n")
        released = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "claim",
                "release",
                claim_id,
                "--session-id",
                "worker-029k",
            ],
            cwd=self.root,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(released.returncode, 1)
        payload = json.loads(released.stdout)
        self.assertEqual(payload["detail"]["error"], "terminal_worktree_not_clean")
        claim = memory_sync.inspect_claims(self.root, task_id)[0]
        self.assertEqual(claim["lease_status"], "active")

    def test_run_report_path_template_is_portable_and_configurable(self) -> None:
        config = json.loads(json.dumps(self.config))
        config["paths"]["run_report_glob"] = "evidence/runs/*.md"
        config["paths"]["run_report_template"] = (
            "evidence\\runs\\{work_unit_id}-try-{attempt}.md"
        )
        self.assertEqual(
            memory_sync.allocate_run_report_path(config, "012-r1", 2),
            "evidence/runs/012-r1-try-2.md",
        )
        with self.assertRaises(ValueError):
            memory_sync.canonical_repo_path("C:\\outside\\report.md")
        with self.assertRaises(ValueError):
            memory_sync.canonical_repo_path("reports/../outside.md")

    def test_run_report_impact_rows_follow_configured_memory_paths(self) -> None:
        config = json.loads(json.dumps(self.config))
        replacements = {
            "PRD.md": "docs/product/PRD.md",
            "ARCHITECTURE.md": "docs/engineering/ARCHITECTURE.md",
            "CODEMAP.md": "docs/engineering/CODEMAP.md",
            "CONVENTIONS.md": "docs/engineering/CONVENTIONS.md",
        }
        for name, path in zip(
            ("prd", "architecture", "codemap", "conventions"),
            replacements.values(),
        ):
            config["paths"][name] = path
        self.assertEqual(
            memory_sync.configured_memory_impact_paths(config),
            list(replacements.values()),
        )

        report_path = "reports/runs/029m-attempt-1.md"
        content = self.structured_run_report("029m-attempt-1", task_id="029m")
        for old_path, new_path in replacements.items():
            content = content.replace(old_path, new_path)
        self.write(report_path, content)
        result = memory_sync.CheckResult()
        memory_sync.validate_run_report(
            self.root, config, "worktree", report_path, result
        )
        self.assertFalse(
            [error for error in result.errors if "missing an impact row" in error],
            result.errors,
        )

    def test_load_config_rejects_repository_escape_paths(self) -> None:
        config = json.loads(json.dumps(self.config))
        config["paths"]["project_status"] = "../outside.md"
        self.write(".wishgraph/config.json", json.dumps(config))
        with self.assertRaisesRegex(ValueError, "invalid paths.project_status"):
            memory_sync.load_config(self.root)

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
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        payload = json.loads(process.stdout)
        self.assertEqual(payload["decision"], "block")
        self.assertIn("Check WishGraph status", payload["reason"])
        self.assertNotIn("Claim", payload["reason"])
        self.assertEqual(memory_sync.inspect_worker_notifications(self.root), [])

    def test_claim_cli_runs_execution_preflight_and_blocks_duplicate_worker(self) -> None:
        task_path = "tasks/build/030-claim.md"
        self.write(
            task_path,
            self.execution_ready_task(
                "030-claim", status="approved", worker_authorized=True
            ),
        )
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
            encoding="utf-8",
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
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(second.returncode, 1)
        self.assertEqual(json.loads(second.stdout)["error"], "active_claim_exists")

    def test_claude_worker_capability_levels_use_only_native_host_facts(self) -> None:
        host_adapter_module = sys.modules["host_adapter"]
        config_home = self.root / "claude-config"
        (self.root / ".claude" / "agents" / "wishgraph-worker.md").unlink()
        agent_path = config_home / "agents" / "wishgraph-worker.md"
        agent_path.parent.mkdir(parents=True, exist_ok=True)
        agent_path.write_text(
            "---\nname: wishgraph-worker\n---\n"
            + claude_worker_provider_module.CLAUDE_WORKER_AGENT_MARKER
            + "\n",
            encoding="utf-8",
        )
        main_help = subprocess.CompletedProcess(
            ["claude", "--help"],
            0,
            stdout=(
                "--bg --fork-session --worktree --settings\n"
                "Commands:\n  agents [options]\n"
            ),
            stderr="",
        )
        agents_help = subprocess.CompletedProcess(
            ["claude", "agents", "--help"],
            0,
            stdout="--json --all --cwd",
            stderr="",
        )
        (self.root / ".claude" / "settings.json").unlink()
        isolated_env = {"CLAUDE_CONFIG_DIR": str(config_home)}
        with (
            mock.patch.dict(os.environ, isolated_env),
            mock.patch.object(host_adapter_module.shutil, "which", return_value="/bin/claude"),
            mock.patch.object(
                claude_worker_provider_module,
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
                claude_worker_provider_module,
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
                claude_worker_provider_module, "_run_process", return_value=manual_help
            ),
        ):
            manual = memory_sync.detect_claude_worker_capability(self.root)
        self.assertEqual(manual.tier, "manual_command_only")

    def test_global_claude_adapter_and_agent_satisfy_enabled_project_guard(self) -> None:
        config_home = self.root / "global-claude"
        installer = ROOT / "skills" / "wishgraph" / "scripts" / "install_global_adapter.py"
        installed = subprocess.run(
            [
                sys.executable,
                str(installer),
                "--host",
                "claude",
                "--config-home",
                str(config_home),
            ],
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(installed.returncode, 0, installed.stderr)
        global_agent = config_home / "agents" / "wishgraph-worker.md"
        global_agent.parent.mkdir(parents=True)
        shutil.copy2(
            ROOT
            / "skills"
            / "wishgraph"
            / "assets"
            / "claude-agents"
            / "wishgraph-worker.md",
            global_agent,
        )
        (self.root / ".claude" / "settings.json").unlink()
        (self.root / ".claude" / "agents" / "wishgraph-worker.md").unlink()
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(config_home)}):
            state = memory_sync.current_host_adapter_state(self.root, "claude")
        self.assertEqual(state["state"], "current")
        self.assertEqual(state["scope"], "global")
        self.assertEqual(Path(state["agent_path"]), global_agent)

    def test_materialized_windows_hook_command_matches_exact_event_contract(self) -> None:
        host_adapter_module = sys.modules["host_adapter"]
        command = (
            "& 'C:\\Program Files\\Python313\\python.exe' "
            "'C:\\project\\.wishgraph\\hooks\\memory_sync.py' "
            "'session-start' '--host' 'codex'"
        )
        self.assertTrue(
            host_adapter_module._command_matches_host_event(
                command, "SessionStart", "codex"
            )
        )
        self.assertFalse(
            host_adapter_module._command_matches_host_event(
                command, "UserPromptSubmit", "codex"
            )
        )

    def test_global_claude_install_launches_without_project_settings(self) -> None:
        task_id = "057"
        discussion_id = "discussion-057"
        worker_id = "87654321-4321-4321-4321-cba987654321"
        host_adapter_module = sys.modules["host_adapter"]
        with tempfile.TemporaryDirectory() as tempdir:
            config_home = Path(tempdir) / ".claude"
            installer = (
                ROOT
                / "skills"
                / "wishgraph"
                / "scripts"
                / "install_global_adapter.py"
            )
            installed = subprocess.run(
                [
                    sys.executable,
                    str(installer),
                    "--host",
                    "claude",
                    "--config-home",
                    str(config_home),
                ],
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(installed.returncode, 0, installed.stderr)
            global_agent = config_home / "agents" / "wishgraph-worker.md"
            global_agent.parent.mkdir(parents=True)
            shutil.copy2(
                ROOT
                / "skills"
                / "wishgraph"
                / "assets"
                / "claude-agents"
                / "wishgraph-worker.md",
                global_agent,
            )
            self.git(
                "rm",
                "-q",
                ".claude/settings.json",
                ".claude/agents/wishgraph-worker.md",
            )
            self.git("commit", "-qm", "use global Claude adapter")
            self.prepare_claude_worker_task(task_id, discussion_id)
            observed = memory_sync.record_host_observation(
                self.root, "claude", "session-start", self.config["runtime_version"]
            )
            self.assertTrue(observed["ok"], observed)
            capability = memory_sync.ClaudeWorkerCapability(
                tier="background_session",
                claude_executable="/bin/claude",
                agent_definition=str(global_agent),
                supports_background=True,
                supports_agents_json=True,
                supports_worktree=True,
                supports_settings=True,
                reason="native_background_session_available",
            )
            before = {"ok": True, "sessions": []}
            actual_worktree = Path(tempfile.mkdtemp(prefix="claude-worker-057-"))
            actual_worktree.rmdir()
            self.addCleanup(shutil.rmtree, actual_worktree, True)
            self.git(
                "worktree",
                "add",
                "-q",
                "-b",
                "worktree-agent-057",
                str(actual_worktree),
                "HEAD",
            )
            after = {
                "ok": True,
                "sessions": [
                    {
                        "id": "87654321",
                        "sessionId": worker_id,
                        "cwd": str(actual_worktree),
                        "state": "working",
                    }
                ],
            }
            launched_process = subprocess.CompletedProcess(
                [], 0, stdout="backgrounded · 87654321\n", stderr=""
            )
            global_settings_before = (
                config_home / "settings.json"
            ).read_bytes()
            with (
                mock.patch.dict(
                    os.environ, {"CLAUDE_CONFIG_DIR": str(config_home)}
                ),
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
                ),
            ):
                payload = memory_sync.launch_claude_worker(
                    self.root, self.config, task_id, discussion_id
                )
            self.assertTrue(payload["ok"], payload)
            self.assertTrue(payload["launched"])
            self.assertFalse((self.root / ".claude" / "settings.json").exists())
            self.assertEqual(
                (config_home / "settings.json").read_bytes(),
                global_settings_before,
            )
            self.assertEqual(payload["claude_session_id"], worker_id)
            runtime = memory_sync.read_session_runtime(self.root, discussion_id)
            assert runtime is not None
            self.assertEqual(
                runtime["worker_runtime"]["worker_handle"]["worktree"],
                str(actual_worktree.resolve()),
            )

    def test_codex_native_worker_requires_real_registered_thread_before_waiting(self) -> None:
        task_id = "041"
        discussion_id = "discussion-041"
        thread_id = "codex-thread-041"
        self.prepare_claude_worker_task(task_id, discussion_id, host="codex")
        prepared = memory_sync.prepare_codex_worker(
            self.root,
            self.config,
            task_id,
            discussion_id,
            execution_profile={
                "model": "gpt-5.6-terra",
                "reasoning_effort": "xhigh",
            },
        )
        self.assertTrue(prepared["ok"], prepared)
        self.assertEqual(prepared["agent_name"], "wishgraph-worker")
        self.assertIn(f"执行 {task_id} 任务", prepared["prompt"])
        self.assertEqual(
            prepared["host_spawn_options"],
            {"model": "gpt-5.6-terra", "thinking": "xhigh"},
        )
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

        claude_discussion_id = "discussion-042-claude"
        self.prepare_claude_worker_task("042a", claude_discussion_id, host="claude")
        memory_sync.apply_session_runtime_patch(
            self.root,
            claude_discussion_id,
            {"task": {"lifecycle": "draft", "worker_authorized": False}},
        )
        denied_claude = memory_sync.launch_claude_worker(
            self.root, self.config, "042a", claude_discussion_id
        )
        self.assertFalse(denied_claude["ok"])
        self.assertEqual(denied_claude["error"], "worker_launch_not_authorized")

    def test_worker_prepare_rejects_wrong_or_stale_complete_task_identity(self) -> None:
        task_id = "046"
        discussion_id = "discussion-046"
        self.prepare_claude_worker_task(task_id, discussion_id, host="codex")
        wrong_task = memory_sync.prepare_codex_worker(
            self.root, self.config, "046a", discussion_id
        )
        self.assertFalse(wrong_task["ok"])
        self.assertEqual(wrong_task["error"], "authorized_task_mismatch")

        memory_sync.apply_session_runtime_patch(
            self.root,
            discussion_id,
            {"task": {"attempt": 2}},
        )
        stale_identity = memory_sync.prepare_codex_worker(
            self.root, self.config, task_id, discussion_id
        )
        self.assertFalse(stale_identity["ok"])
        self.assertEqual(
            stale_identity["error"],
            "authorized_task_identity_incomplete_or_stale",
        )

    def test_formal_execution_rejects_unselected_or_unconfirmed_current_host(self) -> None:
        codex_only = dict(self.config)
        codex_only["required_hosts"] = ["codex"]
        not_selected = memory_sync.current_host_execution_guard(
            self.root, codex_only, "claude"
        )
        self.assertFalse(not_selected["ok"])
        self.assertEqual(not_selected["error"], "current_host_not_required")

        common_dir = memory_sync.git_common_dir(self.root)
        shutil.rmtree(
            common_dir / "wishgraph" / "host-observations" / "codex",
            ignore_errors=True,
        )
        missing_receipt = memory_sync.current_host_execution_guard(
            self.root, self.config, "codex"
        )
        self.assertFalse(missing_receipt["ok"])
        self.assertEqual(missing_receipt["error"], "current_host_receipt_not_recent")
        self.assertEqual(missing_receipt["next_action"], "open_supported_cli_session")
        self.assertEqual(missing_receipt["fallback_command"], "codex")
        self.assertFalse(missing_receipt["retry_same_session"])
        memory_sync.write_session_runtime(
            self.root,
            "worker-without-receipt",
            {
                "session": {
                    "session_id": "worker-without-receipt",
                    "role": "worker",
                    "host": "codex",
                    "phase": "waiting_for_worker",
                    "expected_transition": None,
                },
                "task": {
                    "task_id": "042",
                    "lifecycle": "running",
                    "worker_authorized": True,
                },
            },
        )
        process = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "pre-tool-use",
                "--host",
                "codex",
            ],
            cwd=self.root,
            input=json.dumps(
                {
                    "cwd": str(self.root),
                    "session_id": "worker-without-receipt",
                    "tool_name": "Write",
                    "tool_input": {"file_path": str(self.root / "src/app.py")},
                }
            ),
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        hook_output = json.loads(process.stdout)["hookSpecificOutput"]
        self.assertEqual(hook_output["permissionDecision"], "deny")

    def test_codex_spawn_failure_cli_outputs_cross_host_handoff(self) -> None:
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
        handoff = printed.call_args.args[0]
        self.assertIn("Codex：", handoff)
        self.assertIn("Claude Code：", handoff)
        self.assertIn("当前默认配置", handoff)
        self.assertIn("\ncodex\n", handoff)
        self.assertIn("\nclaude\n", handoff)
        self.assertNotIn("--model", handoff)
        self.assertIn(f"执行 {task_id}", handoff)

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
            encoding="utf-8",
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
        worker_path = Path(tempfile.mkdtemp(prefix="claude-worker-036-"))
        worker_path.rmdir()
        self.addCleanup(shutil.rmtree, worker_path, True)
        self.git(
            "worktree",
            "add",
            "-q",
            "-b",
            "worktree-agent-036",
            str(worker_path),
            "HEAD",
        )
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
                    "cwd": str(worker_path),
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
        settings_before = (self.root / ".claude" / "settings.json").read_bytes()
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
                claude_worker_provider_module, "_run_process", return_value=launched_process
            ) as run_process,
        ):
            payload = memory_sync.launch_claude_worker(
                self.root,
                self.config,
                task_id,
                discussion_id,
                execution_profile={"model": "sonnet", "reasoning_effort": "high"},
            )
        self.assertEqual(
            (self.root / ".claude" / "settings.json").read_bytes(), settings_before
        )
        self.assertTrue(payload["ok"], payload)
        self.assertTrue(payload["launched"])
        self.assertEqual(payload["claude_session_id"], worker_id)
        actual_command = run_process.call_args.args[0]
        self.assertEqual(actual_command[:4], ["/bin/claude", "--bg", "--agent", "wishgraph-worker"])
        self.assertEqual(actual_command[4:8], ["--model", "sonnet", "--effort", "high"])
        self.assertEqual(actual_command[8], "--worktree")
        self.assertRegex(actual_command[9], r"^wishgraph-036-[0-9a-f]{8}$")
        self.assertEqual(actual_command[10], "--settings")
        self.assertEqual(
            json.loads(actual_command[11]),
            {"worktree": {"baseRef": "head", "symlinkDirectories": [".wishgraph"]}},
        )
        self.assertEqual(actual_command[12], "执行 036 任务")
        runtime = memory_sync.read_session_runtime(self.root, discussion_id)
        assert runtime is not None
        self.assertEqual(runtime["session"]["phase"], "waiting_for_worker")
        self.assertEqual(runtime["worker_runtime"]["claude_session_id"], worker_id)
        self.assertEqual(runtime["worker_runtime"]["active_task_id"], task_id)
        self.assertEqual(runtime["worker_runtime"]["claim_id"], "")
        self.assertEqual(runtime["worker_runtime"]["binding_status"], "awaiting_claim")
        self.assertEqual(runtime["worker_runtime"]["worker_availability"], "starting")
        self.assertEqual(runtime["worker_runtime"]["launch_branch"], "worktree-agent-036")
        self.assertEqual(
            runtime["worker_runtime"]["launch_worktree"], str(worker_path.resolve())
        )
        handle = runtime["worker_runtime"]["worker_handle"]
        self.assertEqual(handle["container_kind"], "claude_background_session")
        self.assertEqual(handle["thread_or_session_id"], worker_id)
        worker_runtime = memory_sync.read_session_runtime(self.root, worker_id)
        assert worker_runtime is not None
        self.assertEqual(
            worker_runtime["launch_context"]["agent_kind"], "formal_worker"
        )
        self.assertEqual(
            worker_runtime["launch_context"]["worktree"],
            str(worker_path.resolve()),
        )
        rejected_claim = subprocess.run(
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
                "wrong-claude-session",
                "--discussion-session-id",
                discussion_id,
                "--host",
                "claude",
                "--container-kind",
                "claude_background_session",
                "--agent-kind",
                "formal_worker",
            ],
            cwd=worker_path,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(rejected_claim.returncode, 1)
        self.assertEqual(
            json.loads(rejected_claim.stdout)["error"],
            "worker_thread_id_binding_mismatch",
        )
        failed_runtime = memory_sync.read_session_runtime(self.root, worker_id)
        assert failed_runtime is not None
        self.assertEqual(
            failed_runtime["worker_runtime"]["binding_status"], "claim_failed"
        )
        self.assertEqual(
            failed_runtime["worker_runtime"]["sync_status"],
            "manual_intervention_required",
        )
        self.assertFalse(memory_sync.inspect_claims(self.root, task_id))

    @unittest.skipIf(os.name == "nt", "fixture requires POSIX executable scripts")
    def test_fake_claude_launch_and_claim_bind_real_managed_worker(self) -> None:
        task_id = "058"
        discussion_id = "discussion-058"
        worker_id = "58585858-1234-1234-1234-123456789abc"
        self.prepare_claude_worker_task(task_id, discussion_id)
        worker_path = Path(tempfile.mkdtemp(prefix="claude-worker-058-"))
        worker_path.rmdir()
        self.addCleanup(shutil.rmtree, worker_path, True)
        self.git(
            "worktree",
            "add",
            "-q",
            "-b",
            "worktree-agent-058",
            str(worker_path),
            "HEAD",
        )
        fake_dir = Path(tempfile.mkdtemp(prefix="fake-claude-"))
        self.addCleanup(shutil.rmtree, fake_dir, True)
        marker = fake_dir / "launched"
        executable = fake_dir / "claude"
        executable.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys\n"
            "from pathlib import Path\n"
            f"marker = Path({str(marker)!r})\n"
            f"worktree = {str(worker_path)!r}\n"
            f"worker_id = {worker_id!r}\n"
            "args = sys.argv[1:]\n"
            "if args == ['--help']:\n"
            "    print('--bg --fork-session --worktree --settings agents')\n"
            "elif args == ['agents', '--help']:\n"
            "    print('--json --all --cwd')\n"
            "elif args[:2] == ['agents', '--json']:\n"
            "    sessions = [] if not marker.exists() else [{\n"
            "        'id': '58585858', 'sessionId': worker_id,\n"
            "        'cwd': worktree, 'state': 'working'}]\n"
            "    print(json.dumps(sessions))\n"
            "elif '--bg' in args and '--agent' in args:\n"
            "    marker.touch()\n"
            "    print('backgrounded · 58585858')\n"
            "else:\n"
            "    raise SystemExit(2)\n",
            encoding="utf-8",
        )
        executable.chmod(0o755)

        launched = memory_sync.launch_claude_worker(
            self.root,
            self.config,
            task_id,
            discussion_id,
            claude_executable=str(executable),
        )
        self.assertTrue(launched["ok"], launched)
        before_claim = memory_sync.read_session_runtime(self.root, discussion_id)
        assert before_claim is not None
        self.assertEqual(before_claim["task"]["lifecycle"], "approved")
        self.assertEqual(before_claim["worker_runtime"]["binding_status"], "awaiting_claim")
        self.assertEqual(before_claim["worker_runtime"]["worker_availability"], "starting")

        claimed = subprocess.run(
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
                "--discussion-session-id",
                discussion_id,
                "--host",
                "claude",
                "--container-kind",
                "claude_background_session",
                "--agent-kind",
                "formal_worker",
            ],
            cwd=worker_path,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(claimed.returncode, 0, claimed.stdout + claimed.stderr)
        claim = json.loads(claimed.stdout)["claim"]
        self.assertEqual(claim["worker_id"], worker_id)
        self.assertEqual(claim["host_thread_ref"], worker_id)
        self.assertEqual(claim["discussion_session_id"], discussion_id)
        self.assertEqual(claim["branch"], "worktree-agent-058")
        self.assertEqual(claim["worktree"], str(worker_path.resolve()))
        worker_runtime = memory_sync.read_session_runtime(self.root, worker_id)
        assert worker_runtime is not None
        self.assertEqual(worker_runtime["task"]["lifecycle"], "running")
        self.assertEqual(worker_runtime["worker_runtime"]["binding_status"], "active")
