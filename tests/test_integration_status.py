from tests.wishgraph_test_support import *  # noqa: F401,F403

class IntegrationStatusTests(MemorySyncTestCase):
    def _commit_warn_worker_closeout(self, task_id: str) -> tuple[dict[str, object], str, str]:
        config = json.loads(json.dumps(self.config))
        config["mode"] = "warn"
        task_path = f"tasks/build/{task_id}-warn-integration.md"
        report_path = f"reports/runs/{task_id}-attempt-1.md"
        self.write(
            task_path,
            self.structured_task(
                task_id,
                status="approved",
                worker_authorized=True,
                run_report=report_path,
            ),
        )
        self.git("add", task_path)
        self.git("commit", "-qm", f"approve {task_id}")
        self.write("src/app.py", f"print('completed {task_id}')\n")
        self.write(
            task_path,
            self.structured_task(
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
        closeout = memory_sync.check_sync(self.root, config, "worktree")
        self.assertTrue(closeout.ok, closeout.errors)
        self.git("add", "src/app.py", task_path, report_path)
        self.git("commit", "-qm", f"complete {task_id}")
        return config, task_path, report_path

    def test_warn_integration_absorbs_report_from_previous_closeout_commit(self) -> None:
        config, task_path, report_path = self._commit_warn_worker_closeout("071")
        self.write(
            task_path,
            self.structured_task(
                "071",
                status="integrated",
                worker_authorized=True,
                run_report=report_path,
            ),
        )
        self.write("reports/PROJECT_STATUS.md", self.overview([report_path]))

        result = memory_sync.check_sync(self.root, config, "worktree")

        self.assertTrue(result.ok, result.errors)

    def test_existing_report_requires_completed_to_integrated_task_transition(self) -> None:
        config, _, report_path = self._commit_warn_worker_closeout("072")
        self.write("reports/PROJECT_STATUS.md", self.overview([report_path]))

        result = memory_sync.check_sync(self.root, config, "worktree")

        self.assertFalse(result.ok)
        self.assertTrue(
            any("completed -> integrated transition" in error for error in result.errors),
            result.errors,
        )

    def test_existing_integration_rejects_missing_report(self) -> None:
        config, task_path, report_path = self._commit_warn_worker_closeout("073")
        missing_report = "reports/runs/073-missing.md"
        self.write(
            task_path,
            self.structured_task(
                "073",
                status="integrated",
                worker_authorized=True,
                run_report=report_path,
            ),
        )
        self.write("reports/PROJECT_STATUS.md", self.overview([missing_report]))

        result = memory_sync.check_sync(self.root, config, "worktree")

        self.assertFalse(result.ok)
        self.assertTrue(
            any(f"Cannot read the worktree version of {missing_report}" in error for error in result.errors),
            result.errors,
        )

    def test_enforce_integration_still_requires_new_report_path(self) -> None:
        config, task_path, report_path = self._commit_warn_worker_closeout("074")
        config["mode"] = "enforce"
        self.write(
            task_path,
            self.structured_task(
                "074",
                status="integrated",
                worker_authorized=True,
                run_report=report_path,
            ),
        )
        self.write("reports/PROJECT_STATUS.md", self.overview([report_path]))

        result = memory_sync.check_sync(self.root, config, "worktree")

        self.assertFalse(result.ok)
        self.assertTrue(
            any("at least one new reports/runs/*.md" in error for error in result.errors),
            result.errors,
        )

    def test_integrated_revision_requires_same_change_project_status_writeback(self) -> None:
        self.config = json.loads(
            (HOOK_ASSETS / "config.json").read_text(encoding="utf-8")
        )
        self.write(
            ".wishgraph/config.json",
            json.dumps(self.config, ensure_ascii=False, indent=2) + "\n",
        )
        self.write(
            "tasks/060-parent.md",
            self.structured_task(
                "060-parent",
                status="completed",
                worker_authorized=True,
            ),
        )
        self.git("add", ".wishgraph/config.json", "tasks/060-parent.md")
        self.git("commit", "-m", "add completed parent task")

        revision_path = "tasks/revisions/060-r1.md"
        report_path = "reports/runs/060-r1-attempt-1.md"
        revision_state = {
            "schema_version": 1,
            "kind": "revision",
            "revision_id": "060-r1",
            "parent_task_id": "060",
            "status": "integrated",
            "user_request": "Apply the bounded correction.",
            "allowed_scope": ["src/revision.py"],
            "validation_plan": ["focused unit test"],
            "run_report": report_path,
            "worker_creation_authorized": True,
        }
        self.write(
            revision_path,
            "# 060-r1\n\n<!-- wishgraph:revision-state:start -->\n```json\n"
            + json.dumps(revision_state, indent=2)
            + "\n```\n<!-- wishgraph:revision-state:end -->\n",
        )
        self.write("src/revision.py", "VALUE = 'corrected'\n")
        self.write(
            report_path,
            self.structured_run_report(
                "060-r1-attempt-1",
                task_id="060",
                revision_id="060-r1",
                change_class="revision",
                changed_paths=["src/revision.py"],
            ),
        )

        missing_writeback = memory_sync.check_sync(
            self.root, self.config, "worktree"
        )
        self.assertFalse(missing_writeback.ok)
        self.assertTrue(
            any(
                "must update reports/PROJECT_STATUS.md in the same change" in error
                for error in missing_writeback.errors
            ),
            missing_writeback.errors,
        )

        self.write("reports/PROJECT_STATUS.md", self.overview([report_path]))
        complete = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertTrue(complete.ok, complete.errors)

    def test_integration_lease_allows_closeout_but_not_new_business_implementation(self) -> None:
        transition = self.prepare_safe_integration(
            "002", "discussion-closeout", "integration-closeout"
        )
        acquired = memory_sync.acquire_integration_lease(
            self.root,
            session_id="discussion-closeout",
            grant_id=transition["grant"]["grant_id"],
            integration_id="integration-closeout",
            task_ids=["002"],
            reports=["reports/runs/002-attempt-1.md"],
            require_clean=False,
        )
        self.assertTrue(acquired["ok"])

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
                encoding="utf-8",
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
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        payload = json.loads(process.stdout)
        self.assertEqual(payload["decision"], "block")
        self.assertIn("Check WishGraph status", payload["reason"])
        self.assertNotIn("reports/runs", payload["reason"])

    def test_task_completed_uses_blocking_exit_code(self) -> None:
        self.write("src/app.py", "print('changed')\n")
        process = subprocess.run(
            [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "task-completed"],
            cwd=self.root,
            input=json.dumps({"cwd": str(self.root)}),
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(process.returncode, 2)
        self.assertIn("Check WishGraph status", process.stderr)
        self.assertNotIn("reports/runs", process.stderr)

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
            integration_kind="parallel_batch",
            authorization="explicit_user_confirmation",
        )
        legacy_overview = legacy_overview.replace(
            "- User-visible result: current behavior verified",
            "- Integration kind: sequential\n"
            "- Authorization: Inherited task approval\n"
            "- User-visible result: current behavior verified",
        )
        self.write(
            "reports/PROJECT_STATUS.md",
            legacy_overview,
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
                integration_policy="decision_required",
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
                integration_policy="decision_required",
                run_report=report_path,
            ),
        )
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertTrue(result.ok, result.errors)

    def test_integration_does_not_require_a_second_discussion_snapshot(self) -> None:
        report_path = "reports/runs/005-no-discussion.md"
        self.write("src/new.py", "print('new')\n")
        self.write(report_path, self.run_report("005-no-discussion"))
        self.write("reports/PROJECT_STATUS.md", self.overview([report_path]))
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertTrue(result.ok, result.errors)

    def test_integration_requires_project_status_update(self) -> None:
        report_path = "reports/runs/005b-no-status.md"
        self.write("src/no_status.py", "print('new')\n")
        self.write(report_path, self.run_report("005b-no-status"))
        self.write("CODEMAP.md", "# CODEMAP\n\n- `src/no_status.py`\n")
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertFalse(result.ok)
        self.assertTrue(
            any(
                "must not update shared memory CODEMAP.md" in error
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
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        warned_payload = json.loads(warned.stdout)
        self.assertEqual(warned_payload, {})

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
            encoding="utf-8",
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
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        blocked_payload = json.loads(blocked.stdout)
        self.assertEqual(blocked_payload["decision"], "block")
        self.assertIn("Check WishGraph status", blocked_payload["reason"])
        self.assertNotIn("Do not remove unresolved risks", blocked_payload["reason"])

    def test_warn_pretool_is_silent_and_never_denies_authority_findings(self) -> None:
        config_path = self.root / ".wishgraph" / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["mode"] = "warn"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        self.write("src/warn_quiet.py", "print('quiet')\n")
        self.git("add", "src/warn_quiet.py")
        quiet = subprocess.run(
            [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "pre-tool-use"],
            cwd=self.root,
            input=json.dumps(
                {
                    "cwd": str(self.root),
                    "session_id": "warn-neutral",
                    "tool_name": "Bash",
                    "tool_input": {"command": "git commit -m quiet"},
                }
            ),
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        self.assertEqual(json.loads(quiet.stdout), {})
        self.assertEqual(quiet.stderr, "")

        memory_sync.write_session_runtime(
            self.root,
            "warn-discussion",
            {
                "session": {
                    "session_id": "warn-discussion",
                    "role": "discussion",
                    "host": "codex",
                    "phase": "planning",
                    "expected_transition": None,
                }
            },
        )
        denied = subprocess.run(
            [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "pre-tool-use"],
            cwd=self.root,
            input=json.dumps(
                {
                    "cwd": str(self.root),
                    "session_id": "warn-discussion",
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
        self.assertEqual(json.loads(denied.stdout), {})
        self.assertEqual(denied.stderr, "")

    def test_project_status_character_limit_is_enforced(self) -> None:
        self.prepare_integration("005d-long-chars")
        config = json.loads(json.dumps(self.config))
        config["project_status_max_chars"] = 100
        result = memory_sync.check_sync(self.root, config, "worktree")
        self.assertFalse(result.ok)
        self.assertTrue(any("characters; limit is 100" in error for error in result.errors))

    def test_discussion_prompt_is_not_a_dynamic_snapshot(self) -> None:
        self.prepare_integration("005e-long-discussion")
        long_state = "\n".join(f"- line {index}: value" for index in range(31))
        self.write(
            "prompts/DISCUSSION_AI.md",
            "# Discussion\n\n<!-- wishgraph:state:start -->\n"
            + long_state
            + "\n<!-- wishgraph:state:end -->\n",
        )
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertTrue(result.ok, result.errors)

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
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        self.assertEqual(json.loads(process.stdout), {})

    def test_hook_cli_normalizes_legacy_stdio_to_utf8(self) -> None:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "cp1252"
        request = json.dumps(
            {
                "cwd": str(self.root),
                "session_id": "fresh-windows-session",
                "prompt": "开始讨论",
            },
            ensure_ascii=False,
        ).encode("utf-8")
        process = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "user-prompt-submit",
                "--host",
                "codex",
            ],
            cwd=self.root,
            env=env,
            input=request,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(
            process.returncode,
            0,
            process.stderr.decode("utf-8", errors="replace"),
        )
        payload = json.loads(process.stdout.decode("utf-8"))
        self.assertEqual(
            payload["hookSpecificOutput"]["hookEventName"],
            "UserPromptSubmit",
        )
        runtime = memory_sync.read_session_runtime(
            self.root, "fresh-windows-session"
        )
        self.assertEqual(runtime["session"]["role"], "discussion")

    def test_session_start_does_not_inject_project_summary(self) -> None:
        process = subprocess.run(
            [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "session-start"],
            cwd=self.root,
            input=json.dumps({"cwd": str(self.root)}),
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        self.assertEqual(json.loads(process.stdout), {})




    def test_removed_session_start_context_mode_has_no_effect(self) -> None:
        self.update_config(session_start_context_mode="surprise")
        self.assertIsNotNone(memory_sync.load_config(self.root))


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
                    encoding="utf-8",
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
                if name == "decision":
                    self.assertIn(report_path, state["ready_reports"])
                    self.assertTrue(state["requires_user_confirmation"])
                    self.assertEqual(state["next_action"], "await_user_confirmation")
                else:
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
            self.structured_task(
                "011",
                status="approved",
                work_type="parallel_batch",
                batch_id="batch-009",
                worker_authorized=True,
                run_report=waiting_path,
            ),
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
            self.structured_task(
                "013",
                status="approved",
                worker_authorized=True,
                run_report=report_path,
            ),
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


    def test_status_command_is_read_only(self) -> None:
        before = self.git("status", "--porcelain").stdout
        process = subprocess.run(
            [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "status"],
            cwd=self.root,
            text=True,
            encoding="utf-8",
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

    def test_session_start_keeps_pending_integration_details_out_of_output(self) -> None:
        self.write("src/app.py", "print('pending')\n")
        self.write("reports/runs/012-pending.md", self.run_report("012-pending"))
        process = subprocess.run(
            [sys.executable, str(HOOK_ASSETS / "memory_sync.py"), "session-start"],
            cwd=self.root,
            input=json.dumps({"cwd": str(self.root)}),
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        self.assertEqual(json.loads(process.stdout), {})

    def test_user_prompt_submit_routes_discussion_refresh_and_exact_task(self) -> None:
        task_path = "tasks/build/012-route.md"
        self.write(
            task_path,
            self.execution_ready_task(
                "012-route", status="approved", worker_authorized=True
            ),
        )
        self.git("add", task_path)
        self.git("commit", "-qm", "prepare route task")
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
            encoding="utf-8",
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
                {"cwd": str(self.root), "session_id": "discussion-route", "prompt": "执行 012 号任务！"}
            ),
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            check=True,
        )
        context = json.loads(route.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn('"host_action":"launch_codex_agent_worker"', context)
        self.assertIn('"task_id":"012"', context)
        self.assertIn('"discussion_session_id":"discussion-route"', context)
        self.assertIn('"authorization_patch_required":false', context)
        self.assertIn('"authorization_commit_required":false', context)
        self.assertIn("012 已交给独立 Worker 执行。", context)
        self.assertIn('"hide_on_normal_path"', context)
        discussion_runtime = memory_sync.read_session_runtime(self.root, "discussion-route")
        assert discussion_runtime is not None
        self.assertEqual(discussion_runtime["session"]["role"], "discussion")
        self.assertEqual(discussion_runtime["session"]["phase"], "routing_worker")
        self.assertEqual(discussion_runtime["task"]["task_id"], "012")
        self.assertEqual(discussion_runtime["task"]["attempt"], 1)
        self.assertEqual(
            discussion_runtime["task"]["run_report"], "reports/runs/012-route.md"
        )

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
            encoding="utf-8",
            stdout=subprocess.PIPE,
            check=True,
        )
        refreshed = memory_sync.read_session_runtime(self.root, "discussion-route")
        self.assertEqual(
            refreshed["session"]["expected_transition"]["kind"],
            "approve_worker_launch",
        )

    def test_exact_execute_repairs_complete_task_identity_before_codex_prepare(self) -> None:
        task_id = "008"
        session_id = "discussion-existing-without-task-id"
        task_path = f"tasks/build/{task_id}-runtime-identity.md"
        report_path = f"reports/runs/{task_id}-attempt-2.md"
        self.write(
            task_path,
            self.execution_ready_task(
                task_id,
                status="draft",
                attempt=2,
                run_report=report_path,
            ),
        )
        self.git("add", task_path)
        self.git("commit", "-qm", "prepare draft 008")
        memory_sync.write_session_runtime(
            self.root,
            session_id,
            {
                "session": {
                    "session_id": session_id,
                    "role": "discussion",
                    "host": "codex",
                    "phase": "planning",
                    "expected_transition": None,
                },
                "session_provenance": {
                    "initial_role": "neutral",
                    "host": "codex",
                    "discussion_authorized": True,
                },
                "task": {
                    "lifecycle": "draft",
                    "attempt": 99,
                    "worker_authorized": False,
                    "run_report": "reports/runs/stale.md",
                    "stale_identity_field": "must-not-survive",
                },
            },
        )
        routed = subprocess.run(
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
                    "session_id": session_id,
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
        self.assertIn('"host_action":"launch_codex_agent_worker"', context)
        self.assertIn('"authorization_patch_required":false', context)
        runtime = memory_sync.read_session_runtime(self.root, session_id)
        assert runtime is not None
        self.assertEqual(
            runtime["task"],
            {
                "task_id": task_id,
                "lifecycle": "approved",
                "attempt": 2,
                "worker_authorized": True,
                "run_report": report_path,
                "worker_execution_profiles": {},
            },
        )

        prepared = memory_sync.prepare_codex_worker(
            self.root, self.config, task_id, session_id
        )
        self.assertTrue(prepared["ok"], prepared)
        self.assertNotEqual(prepared.get("error"), "authorized_task_mismatch")
        thread_id = "codex-thread-direct-008"
        registered = memory_sync.register_codex_worker(
            self.root,
            self.config,
            task_id,
            session_id,
            thread_id,
            inspectable=True,
            controllable=True,
            independent_context=True,
        )
        self.assertTrue(registered["ok"], registered)
        claimed = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "claim",
                "acquire",
                task_id,
                "--attempt",
                "2",
                "--worker-id",
                thread_id,
                "--session-id",
                thread_id,
                "--host-thread-ref",
                thread_id,
                "--discussion-session-id",
                session_id,
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
        self.assertEqual(claimed.returncode, 0, claimed.stderr)
        claim_payload = json.loads(claimed.stdout)
        self.assertTrue(claim_payload["ok"], claim_payload)
        worker_runtime = memory_sync.read_session_runtime(self.root, thread_id)
        assert worker_runtime is not None
        self.assertEqual(
            worker_runtime["task"],
            {
                "task_id": task_id,
                "lifecycle": "running",
                "attempt": 2,
                "worker_authorized": True,
                "run_report": report_path,
                "worker_execution_profiles": {},
            },
        )
        self.assertEqual(
            claim_payload["claim"]["discussion_session_id"], session_id
        )
        self.assertEqual(claim_payload["claim"]["host_thread_ref"], thread_id)

    def test_contextual_approval_also_persists_complete_task_identity(self) -> None:
        task_id = "010"
        session_id = "discussion-contextual-complete-task"
        task_path = f"tasks/build/{task_id}-contextual.md"
        report_path = f"reports/runs/{task_id}-attempt-3.md"
        self.write(
            task_path,
            self.execution_ready_task(
                task_id,
                status="draft",
                attempt=3,
                run_report=report_path,
            ),
        )
        self.git("add", task_path)
        self.git("commit", "-qm", "prepare contextual task")
        memory_sync.write_session_runtime(
            self.root,
            session_id,
            {
                "session": {
                    "session_id": session_id,
                    "role": "discussion",
                    "host": "codex",
                    "phase": "awaiting_worker_authorization",
                    "expected_transition": {
                        "kind": "approve_worker_launch",
                        "task_id": task_id,
                    },
                },
                "session_provenance": {
                    "initial_role": "neutral",
                    "host": "codex",
                    "discussion_authorized": True,
                },
                "task": {
                    "task_id": task_id,
                    "lifecycle": "draft",
                    "worker_authorized": False,
                },
            },
        )
        routed = subprocess.run(
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
                    "session_id": session_id,
                    "prompt": "批准",
                }
            ),
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        context = json.loads(routed.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn('"accepted":true', context)
        self.assertIn('"authorization_patch_required":false', context)
        runtime = memory_sync.read_session_runtime(self.root, session_id)
        assert runtime is not None
        self.assertEqual(
            runtime["task"],
            {
                "task_id": task_id,
                "lifecycle": "approved",
                "attempt": 3,
                "worker_authorized": True,
                "run_report": report_path,
                "worker_execution_profiles": {},
            },
        )

    def test_neutral_execute_works_with_or_without_sessionstart_and_replaces_old_task(self) -> None:
        for task_id, attempt in (("008", 1), ("009", 3)):
            path = f"tasks/build/{task_id}-direct-route.md"
            self.write(
                path,
                self.execution_ready_task(
                    task_id,
                    status="draft",
                    attempt=attempt,
                    run_report=f"reports/runs/{task_id}-attempt-{attempt}.md",
                ),
            )
        self.git("add", "tasks/build")
        self.git("commit", "-qm", "prepare direct routes")

        session_id = "neutral-existing-runtime"
        subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "session-start",
                "--host",
                "codex",
            ],
            cwd=self.root,
            input=json.dumps({"cwd": str(self.root), "session_id": session_id}),
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        for task_id, expected_attempt in (("008", 1), ("009", 3)):
            routed = subprocess.run(
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
                        "session_id": session_id,
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
            self.assertIn('"ok":true', context)
            runtime = memory_sync.read_session_runtime(self.root, session_id)
            assert runtime is not None
            self.assertEqual(runtime["session"]["role"], "neutral")
            self.assertEqual(runtime["worker_runtime"]["dispatch_mode"], "current_window")
            self.assertEqual(runtime["task"]["task_id"], task_id)
            self.assertEqual(runtime["task"]["attempt"], expected_attempt)
            self.assertEqual(
                runtime["task"]["run_report"],
                f"reports/runs/{task_id}-attempt-{expected_attempt}.md",
            )

        fresh_session = "neutral-no-runtime"
        fresh_routed = subprocess.run(
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
                    "session_id": fresh_session,
                    "prompt": "执行 008 任务",
                }
            ),
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        fresh_context = json.loads(fresh_routed.stdout)["hookSpecificOutput"][
            "additionalContext"
        ]
        fresh_route = json.loads(
            fresh_context.split("WishGraph explicit route:\n", 1)[1]
        )
        self.assertEqual(fresh_route["host_action"], "bind_current_worker")
        self.assertIn(str(sys.executable), fresh_route["current_worker_claim_command"])
        self.assertIn("claim", fresh_route["current_worker_claim_command"])
        self.assertIn("acquire", fresh_route["current_worker_claim_command"])
        fresh_runtime = memory_sync.read_session_runtime(self.root, fresh_session)
        assert fresh_runtime is not None
        self.assertEqual(fresh_runtime["session"]["role"], "neutral")
        self.assertEqual(fresh_runtime["task"]["task_id"], "008")

    def test_neutral_dispatch_and_claim_use_canonical_run_and_id(self) -> None:
        task_id = "008"
        task_path = "tasks/build/008-fast-dispatch.md"
        self.write(task_path, self.execution_ready_task(task_id, status="draft"))
        self.git("add", task_path)
        self.git("commit", "-qm", "prepare fast dispatch")

        routed = subprocess.run(
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
                    "session_id": "/root/execute_008",
                    "prompt": "执行 008 任务",
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
        self.assertEqual(route["host_action"], "bind_current_worker")
        self.assertIn("claim", route["current_worker_claim_command"])
        self.assertIn("acquire", route["current_worker_claim_command"])
        self.assertIn(task_id, route["current_worker_claim_command"])

        claimed = subprocess.run(
            [
                sys.executable,
                str(HOOK_ASSETS / "memory_sync.py"),
                "claim",
                "acquire",
                task_id,
                "--worker-id",
                "/root/execute_008",
                "--session-id",
                "/root/execute_008",
                "--host-thread-ref",
                "/root/execute_008",
                "--host",
                "codex",
                "--container-kind",
                "manual_worker_window",
                "--agent-kind",
                "formal_worker",
            ],
            cwd=self.root,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(claimed.returncode, 0, claimed.stderr)
        payload = json.loads(claimed.stdout)
        self.assertEqual(payload["claim"]["worker_id"], "execute_008")
        self.assertEqual(payload["claim"]["host_thread_ref"], "execute_008")
        run = memory_sync.latest_execution_run(self.root, task_id, attempt=1)
        assert run is not None
        self.assertEqual(run["phase"], "running")
        self.assertEqual(run["worker"]["thread_or_session_id"], "execute_008")

    def test_hook_subprocess_does_not_create_python_cache(self) -> None:
        cache = self.root / ".wishgraph" / "hooks" / "__pycache__"
        shutil.rmtree(cache, ignore_errors=True)
        subprocess.run(
            [
                sys.executable,
                str(self.root / ".wishgraph" / "hooks" / "memory_sync.py"),
                "check",
                "--scope",
                "worktree",
            ],
            cwd=self.root,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        self.assertFalse(cache.exists())

    def test_direct_execute_rejects_unsatisfied_dependencies_before_runtime_write(self) -> None:
        self.write(
            "tasks/build/001-dependency.md",
            self.execution_ready_task("001", status="draft"),
        )
        self.write(
            "tasks/build/008-dependent.md",
            self.execution_ready_task(
                "008",
                status="draft",
                dependencies=["001"],
            ),
        )
        self.git("add", "tasks/build")
        self.git("commit", "-qm", "prepare dependent task")
        session_id = "neutral-unsatisfied-dependency"
        routed = subprocess.run(
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
                    "session_id": session_id,
                    "prompt": "执行 008 任务",
                }
            ),
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        context = json.loads(routed.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn('"ok":false', context)
        self.assertIn('"denial_reason":"execution_preflight_failed"', context)
        self.assertIn("unsatisfied_dependencies:001", context)
        self.assertIsNone(memory_sync.read_session_runtime(self.root, session_id))

    def test_direct_execute_fails_closed_when_complete_runtime_cannot_persist(self) -> None:
        task_path = "tasks/build/008-persistence-failure.md"
        self.write(task_path, self.execution_ready_task("008", status="draft"))
        self.git("add", task_path)
        self.git("commit", "-qm", "prepare persistence failure")
        host_adapter_module = sys.modules["host_adapter"]
        emitted: list[dict[str, object]] = []
        with (
            mock.patch.object(
                host_adapter_module,
                "_persist_execution_route_runtime",
                return_value={
                    "ok": False,
                    "error": "session_runtime_write_failed",
                },
            ),
            mock.patch.object(
                host_adapter_module,
                "emit",
                side_effect=lambda value: emitted.append(value),
            ),
        ):
            exit_code = host_adapter_module.user_prompt_submit_main(
                self.root,
                self.config,
                {
                    "cwd": str(self.root),
                    "session_id": "neutral-persist-failure",
                    "prompt": "执行 008 任务",
                },
                "codex",
            )
        self.assertEqual(exit_code, 0)
        context = emitted[-1]["hookSpecificOutput"]["additionalContext"]
        self.assertIn('"ok":false', context)
        self.assertIn('"host_action":"no_action"', context)
        self.assertIn("authorization_runtime_persistence_failed", context)
        self.assertNotIn("codex-worker prepare", context)
        self.assertIsNone(
            memory_sync.read_session_runtime(self.root, "neutral-persist-failure")
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
            encoding="utf-8",
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
            encoding="utf-8",
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
        self.write("reports/PROJECT_STATUS.md", self.overview([report_path]))
        rejected = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertFalse(rejected.ok)
        self.assertTrue(
            any("Integration must update PRD.md" in error for error in rejected.errors),
            rejected.errors,
        )

        self.write("PRD.md", "# PRD\n\n- Decision: updated detail\n")
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
            encoding="utf-8",
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
