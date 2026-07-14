from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
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


memory_sync = load_runtime_module()


class MemorySyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "WishGraph Tests")

        (self.root / ".wishgraph" / "hooks").mkdir(parents=True)
        shutil.copy2(HOOK_ASSETS / "config.json", self.root / ".wishgraph" / "config.json")
        shutil.copy2(
            HOOK_ASSETS / "memory_sync.py",
            self.root / ".wishgraph" / "hooks" / "memory_sync.py",
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
            "reports/DEV_REPORT.md",
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
            "# Project Report Overview\n\n"
            "## Latest Integration\n\n"
            "- Integration ID: integration/test\n"
            "- Status: Completed\n"
            f"- Integration kind: {kind}\n"
            f"- Authorization: {auth}\n\n"
            "## Integrated Run Reports\n\n"
            f"{report_list}\n\n"
            "## Latest Integrated Results\n\n"
            "- Completed result: latest worker results integrated\n"
            "- Next recommended task: review the overview\n\n"
            "## External Memory Impact\n\n"
            "| File | Result | Reason |\n"
            "|---|---|---|\n"
            f"{table}\n"
        )

    def discussion(self, unit: str) -> str:
        return (
            "# Discussion\n\n"
            "<!-- wishgraph:state:start -->\n\n"
            "## Current Handoff State\n\n"
            f"- Last completed work unit: {unit}\n"
            "- Next likely task: next\n"
            "- Validation health: passing\n\n"
            "<!-- wishgraph:state:end -->\n"
        )

    def test_clean_repo_passes(self) -> None:
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertTrue(result.ok, result.errors)

    def test_chinese_report_status_is_machine_readable(self) -> None:
        self.assertEqual(memory_sync.parse_report_status("- 状态：Completed\n"), "completed")

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
            "reports/DEV_REPORT.md",
            self.overview(
                report_paths,
                {"CODEMAP.md": ("Updated", "Integrated new source anchors")},
            ),
        )
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertTrue(result.ok, result.errors)

    def test_integration_requires_discussion_state_update(self) -> None:
        report_path = "reports/runs/005-no-discussion.md"
        self.write("src/new.py", "print('new')\n")
        self.write(report_path, self.run_report("005-no-discussion"))
        self.write("reports/DEV_REPORT.md", self.overview([report_path]))
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertFalse(result.ok)
        self.assertTrue(any("discussion" in error.lower() for error in result.errors))

    def test_existing_run_report_is_immutable(self) -> None:
        self.write("reports/runs/000-bootstrap.md", self.run_report("rewritten"))
        self.write("src/app.py", "print('changed')\n")
        result = memory_sync.check_sync(self.root, self.config, "worktree")
        self.assertFalse(result.ok)
        self.assertTrue(any("immutable" in error for error in result.errors))

    def test_session_start_injects_integrated_results_and_handoff(self) -> None:
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
        self.assertIn("Current Handoff State", context)

    def test_safe_sequential_result_needs_no_second_confirmation(self) -> None:
        self.write("src/app.py", "print('safe sequential')\n")
        report_path = "reports/runs/006-sequential.md"
        self.write(report_path, self.run_report("006-sequential"))
        state = memory_sync.integration_state(self.root, self.config).as_dict()
        self.assertTrue(state["pending_integration"])
        self.assertEqual(state["integration_kind"], "sequential")
        self.assertEqual(state["ready_reports"], [report_path])
        self.assertFalse(state["requires_user_confirmation"])

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
            "reports/DEV_REPORT.md",
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
        self.assertIn("pending_integration", payload)
        after = self.git("status", "--porcelain").stdout
        self.assertEqual(before, after)

    def test_session_start_injects_pending_integration_status(self) -> None:
        self.write("src/app.py", "print('pending')\n")
        self.write("reports/runs/012-pending.md", self.run_report("012-pending"))
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


class InstallerTests(unittest.TestCase):
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
            self.assertTrue((root / ".wishgraph" / "hooks" / "memory_sync.py").exists())
            config = json.loads((root / ".wishgraph" / "config.json").read_text())
            self.assertEqual(config["mode"], "warn")
            self.assertEqual(config["version"], 4)
            self.assertEqual(config["paths"]["run_report_glob"], "reports/runs/*.md")
            self.assertEqual(config["paths"]["task_glob"], "tasks/build/*.md")
            self.assertEqual(
                config["paths"]["task_globs"],
                ["tasks/build/*.md", ".tasks/build/*.md"],
            )
            self.assertTrue(config["scan_worker_refs_for_status"])
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
                        "paths": {"task_glob": ".tasks/build/*.md"},
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
            self.assertEqual(config["version"], 4)
            self.assertEqual(config["session_summary_max_chars"], 1234)
            self.assertTrue(config["scan_worker_refs_for_status"])
            self.assertEqual(config["paths"]["task_glob"], ".tasks/build/*.md")
            self.assertEqual(
                config["paths"]["task_globs"],
                ["tasks/build/*.md", ".tasks/build/*.md"],
            )


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
            self.assertIn("about 0.2 MB", process.stdout)
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
            self.assertIn("Hooks remain non-blocking", process.stdout)
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
            "about 0.2 MB",
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
        self.assertIn("proactively recommend", skill)
        self.assertIn("four-stage conversation", skill)
        self.assertIn("按推荐来", skill)
        self.assertIn("exact short reply that will resume setup", skill)
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
            "The task is ready. Create the execution window?",
            "explicit human command",
            "user-visible, user-owned Worker tasks",
            "<task-id> · <short title> · WG Worker",
            "Do not use hidden subagents",
            "manual fallback",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, prompt)

    def test_worker_launch_protocol_requires_visible_human_authorized_tasks(self) -> None:
        reference = (
            ROOT
            / "skills"
            / "wishgraph"
            / "references"
            / "worker-window-launch.md"
        ).read_text(encoding="utf-8")
        chinese_prompt = (
            ROOT / "templates" / "zh-CN" / "prompts" / "DISCUSSION_AI.md"
        ).read_text(encoding="utf-8")
        for expected in (
            "创建执行窗口",
            "为这三个任务分别创建执行窗口",
            "visible, user-owned, inspectable, and controllable",
            "<task-id> · <short title> · WG Worker",
            "Do not create extra Workers",
            "Manual copying is the fallback, not the default",
            "Do not use a hidden subagent as the Worker",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, reference)
        for expected in (
            "任务已准备好，是否创建执行窗口？",
            "创建执行窗口",
            "为这三个任务分别创建执行窗口",
            "不得用隐藏 subagent 代替 Worker",
            "手动复制仅作为降级方案",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, chinese_prompt)

    def test_integration_prompt_is_temporary_and_has_truthful_fallback(self) -> None:
        discussion = (
            ROOT / "templates" / "prompts" / "DISCUSSION_AI.md"
        ).read_text(encoding="utf-8")
        integration = (
            ROOT / "templates" / "prompts" / "INTEGRATION_AI.md"
        ).read_text(encoding="utf-8")
        self.assertIn("temporary background integration agent", discussion)
        self.assertIn("If the platform does not support background work", discussion)
        self.assertIn("do not pretend it does", discussion)
        self.assertIn("end this temporary agent", integration)

    def test_hooks_are_not_semantic_reviewers_or_agent_launchers(self) -> None:
        runtime = (HOOK_ASSETS / "memory_sync.py").read_text(encoding="utf-8")
        reference = (
            ROOT / "skills" / "wishgraph" / "references" / "memory-sync-hooks.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Hooks do not start agents", runtime)
        self.assertIn("never start them", reference)
        self.assertNotIn("subprocess.Popen", runtime)


class TemplateMirrorTests(unittest.TestCase):
    def test_distributable_template_mirrors_stay_identical(self) -> None:
        pairs = [
            ("CODEMAP.md", "CODEMAP.md"),
            ("CONVENTIONS.md", "CONVENTIONS.md"),
            ("prompts/DISCUSSION_AI.md", "DISCUSSION_AI.md"),
            ("prompts/EXECUTION_AI.md", "EXECUTION_AI.md"),
            ("prompts/INTEGRATION_AI.md", "INTEGRATION_AI.md"),
            ("reports/DEV_REPORT.md", "DEV_REPORT.md"),
            ("reports/RUN_REPORT.md", "RUN_REPORT.md"),
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
            ("reports/DEV_REPORT.md", "reports/DEV_REPORT.md"),
            ("reports/RUN_REPORT.md", "reports/RUN_REPORT.md"),
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


if __name__ == "__main__":
    unittest.main()
