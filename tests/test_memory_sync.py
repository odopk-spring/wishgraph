from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
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


class RuntimeBoundaryTests(unittest.TestCase):
    def test_runtime_dependencies_follow_the_four_boundaries(self) -> None:
        local_modules = {
            "git_state",
            "workflow_state",
            "policy",
            "host_adapter",
        }
        expected = {
            "git_state.py": set(),
            "workflow_state.py": set(),
            "policy.py": {"git_state", "workflow_state"},
            "host_adapter.py": {"git_state", "policy", "workflow_state"},
            "memory_sync.py": local_modules,
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
            "unit": unit,
            "status": status,
            "work_type": work_type,
            "batch_id": batch_id,
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
        inspect = memory_sync.parse_task_command("查看012号任务")
        family = memory_sync.parse_task_command("查看012系列任务")
        assert execute is not None and inspect is not None and family is not None
        self.assertEqual(execute["action"], "execute")
        self.assertTrue(execute["authorizes_execution"])
        self.assertEqual(inspect["action"], "inspect")
        self.assertFalse(inspect["authorizes_execution"])
        self.assertEqual(family["action"], "family")
        self.assertIsNone(memory_sync.parse_task_command("随便看看012"))

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
            for runtime_name in (
                "memory_sync.py",
                "git_state.py",
                "workflow_state.py",
                "policy.py",
                "host_adapter.py",
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
            self.assertEqual(config["version"], 8)
            self.assertEqual(config["session_start_context_mode"], "safety_only")
            self.assertEqual(config["paths"]["run_report_glob"], "reports/runs/*.md")
            self.assertEqual(
                config["paths"]["project_status"], "reports/PROJECT_STATUS.md"
            )
            self.assertEqual(config["paths"]["task_glob"], "tasks/build/*.md")
            self.assertEqual(
                config["paths"]["task_globs"],
                ["tasks/build/*.md", ".tasks/build/*.md"],
            )
            self.assertTrue(config["scan_worker_refs_for_status"])
            self.assertEqual(config["project_status_max_lines"], 160)
            self.assertEqual(config["project_status_max_chars"], 12000)
            self.assertEqual(config["discussion_dynamic_max_lines"], 30)
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
            self.assertEqual(config["version"], 8)
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
        self.assertIn("task-state", integration)
        self.assertIn("`completed` to `integrated`", integration)

    def test_hooks_are_not_semantic_reviewers_or_agent_launchers(self) -> None:
        runtime = (HOOK_ASSETS / "memory_sync.py").read_text(encoding="utf-8")
        reference = (
            ROOT / "skills" / "wishgraph" / "references" / "memory-sync-hooks.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Hooks do not start agents", runtime)
        self.assertIn("never start them", reference)
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

    def test_distributable_template_mirrors_stay_identical(self) -> None:
        pairs = [
            ("CODEMAP.md", "CODEMAP.md"),
            ("CONVENTIONS.md", "CONVENTIONS.md"),
            ("prompts/DISCUSSION_AI.md", "DISCUSSION_AI.md"),
            ("prompts/EXECUTION_AI.md", "EXECUTION_AI.md"),
            ("prompts/INTEGRATION_AI.md", "INTEGRATION_AI.md"),
            ("reports/PROJECT_STATUS.md", "PROJECT_STATUS.md"),
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
            ("reports/PROJECT_STATUS.md", "reports/PROJECT_STATUS.md"),
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
