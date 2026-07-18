from __future__ import annotations

import ast
import concurrent.futures
import errno
import hashlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
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
claude_worker_provider_module = sys.modules["claude_worker_provider"]


class MemorySyncTestCase(unittest.TestCase):
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
            "claude_worker_provider.py",
            "tool_gate_provider.py",
        ):
            shutil.copy2(
                HOOK_ASSETS / runtime_name,
                self.root / ".wishgraph" / "hooks" / runtime_name,
            )
        for source_name, destination in (
            ("codex-hooks.json", ".codex/hooks.json"),
            ("claude-settings.json", ".claude/settings.json"),
            ("../codex-agents/wishgraph-worker.toml", ".codex/agents/wishgraph-worker.toml"),
            ("../claude-agents/wishgraph-worker.md", ".claude/agents/wishgraph-worker.md"),
        ):
            target = self.root / destination
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(HOOK_ASSETS / source_name, target)
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
        for host in ("codex", "claude"):
            observed = memory_sync.record_host_observation(
                self.root, host, "session-start", self.config["runtime_version"]
            )
            self.assertTrue(observed["ok"], observed)

    def tearDown(self) -> None:
        # Python 3.9 on Linux can observe a transient ENOTEMPTY while removing
        # a Git directory whose final lock/log entry has just disappeared.
        # Retry only that race; every other cleanup failure remains visible.
        for attempt in range(5):
            try:
                self.tempdir.cleanup()
                return
            except OSError as error:
                if error.errno != errno.ENOTEMPTY or attempt == 4:
                    raise
                time.sleep(0.02 * (attempt + 1))

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

    def _run_report_narrative(
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
        return self.structured_run_report(
            unit,
            work_type=work_type,
            batch_id=None if batch_id.casefold() in {"n/a", "na"} else batch_id,
            status=status.casefold(),
            readiness=readiness.casefold(),
            validation=validation.casefold(),
            scope_check=scope_check.casefold(),
            conflict_status=conflict_status.casefold(),
            new_decision=new_decision.casefold() not in {"no", "none", "false", "否", "无"},
            narrative_overrides=overrides,
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
        scope_check: str = "pass",
        conflict_status: str = "none",
        new_decision: bool = False,
        narrative_overrides: Optional[dict[str, tuple[str, str]]] = None,
    ) -> str:
        narrative = self._run_report_narrative(
            unit,
            overrides=narrative_overrides,
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
            "integration_recommendation": (
                "decision_required"
                if work_type in {"parallel_batch", "high_risk"}
                else "safe_for_discussion_integration"
            ),
            "integration_readiness": readiness,
            "scope_check": scope_check,
            "conflict_status": conflict_status,
            "new_decision": new_decision,
            "validation": {"tests": validation},
        }
        block = (
            "<!-- wishgraph:run-state:start -->\n```json\n"
            + json.dumps(state, ensure_ascii=False, indent=2)
            + "\n```\n<!-- wishgraph:run-state:end -->\n\n"
        )
        return narrative.replace("## Work Unit\n\n", "## Work Unit\n\n" + block, 1)

    def structured_task(
        self,
        task_id: str,
        *,
        status: str = "draft",
        work_type: str = "sequential",
        batch_id: Optional[str] = None,
        worker_authorized: bool = False,
        integration_policy: str = "auto_in_discussion",
        parent_task_id: Optional[str] = None,
        dependencies: Optional[list[str]] = None,
        attempt: int = 1,
        run_report: Optional[str] = None,
        execution_mode: str = "exclusive",
        comparison_group: Optional[str] = None,
        worker_execution_profiles: Optional[dict[str, dict[str, str]]] = None,
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
            "worker_execution_profiles": worker_execution_profiles or {},
            "integration_route": integration_policy,
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

    def authorize_execution_run(
        self,
        task_id: str,
        task_path: str,
        discussion_session_id: str,
        *,
        host: str,
        report_path: str,
    ) -> dict[str, object]:
        task_content = (self.root / task_path).read_text(encoding="utf-8")
        head = self.git("rev-parse", "HEAD").stdout.strip()
        created = memory_sync.update_execution_run(
            self.root,
            task_id=task_id,
            attempt=1,
            create=True,
            patch={
                "phase": "dispatching",
                "task_path": task_path,
                "run_report": report_path,
                "base_commit": head,
                "task_fingerprint": memory_sync.content_fingerprint(task_content),
                "authorization": {
                    "authorized": True,
                    "event": "exact_execute_command",
                    "source_session_id": discussion_session_id,
                    "parent_discussion_id": discussion_session_id,
                    "host": host,
                    "dispatch_mode": "background_worker",
                    "authorized_at": "2026-07-18T00:00:00Z",
                },
            },
        )
        self.assertTrue(created["ok"], created)
        return created["run"]

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
        self.authorize_execution_run(
            task_id,
            task_path,
            discussion_session_id,
            host=host,
            report_path=f"reports/runs/{task_id}-attempt-1.md",
        )
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
                "session_provenance": {
                    "initial_role": "neutral",
                    "host": host,
                    "discussion_authorized": True,
                },
                "task": {
                    "task_id": task_id,
                    "lifecycle": "approved",
                    "attempt": 1,
                    "worker_authorized": True,
                    "run_report": f"reports/runs/{task_id}-attempt-1.md",
                },
            },
        )
        self.assertTrue(persisted["ok"], persisted)

    def prepare_safe_integration(
        self,
        task_id: str,
        discussion_session_id: str,
        integration_id: str,
    ) -> dict[str, object]:
        task_path = f"tasks/build/{task_id}-integration.md"
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
        self.git("commit", "-qm", f"authorize {task_id}")
        execution_run = self.authorize_execution_run(
            task_id,
            task_path,
            discussion_session_id,
            host="codex",
            report_path=report_path,
        )
        claimed = memory_sync.acquire_claim(
            self.root,
            task_id,
            1,
            f"worker-{task_id}",
            discussion_session_id=discussion_session_id,
            require_clean=True,
        )
        self.assertTrue(claimed["ok"], claimed)
        running = memory_sync.update_execution_run(
            self.root,
            task_id=task_id,
            attempt=1,
            patch={
                "phase": "running",
                "claim_id": claimed["claim"]["claim_id"],
                "worker": {
                    "host": "codex",
                    "container_kind": "manual_worker_window",
                    "thread_or_session_id": f"worker-{task_id}",
                    "branch": claimed["claim"]["branch"],
                    "worktree": claimed["claim"]["worktree"],
                },
            },
        )
        self.assertTrue(running["ok"], running)
        self.write(
            task_path,
            self.execution_ready_task(
                task_id,
                status="approved",
                worker_authorized=True,
                run_report=report_path,
            ),
        )
        terminal = memory_sync.update_execution_run(
            self.root,
            task_id=task_id,
            attempt=1,
            patch={
                "phase": "succeeded",
                "result": {
                    "terminal_state": "completed",
                    "commit": execution_run["base_commit"],
                    "report": report_path,
                    "risk_outcome": "safe",
                    "reason": "safe",
                    "observed_at": "2026-07-18T00:00:01Z",
                },
            },
        )
        self.assertTrue(terminal["ok"], terminal)
        self.write(
            report_path,
            self.structured_run_report(
                f"{task_id}-attempt-1",
                task_id=task_id,
                changed_paths=["src/app.py"],
            ),
        )
        released = memory_sync.update_claim(
            self.root,
            claimed["claim"]["claim_id"],
            "release",
            branch=claimed["claim"]["branch"],
            worktree=claimed["claim"]["worktree"],
        )
        self.assertTrue(released["ok"], released)
        runtime = memory_sync.write_session_runtime(
            self.root,
            discussion_session_id,
            {
                "session": {
                    "session_id": discussion_session_id,
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
                    "host": "codex",
                    "discussion_authorized": True,
                },
                "task": {
                    "task_id": task_id,
                    "lifecycle": "approved",
                    "worker_authorized": True,
                    "run_report": report_path,
                },
            },
        )
        self.assertTrue(runtime["ok"], runtime)
        transition = memory_sync.transition_session_runtime(
            self.root,
            self.config,
            discussion_session_id,
            "integration_evaluated",
            {
                "outcome": "safe",
                "integration_id": integration_id,
                "task_ids": [task_id],
                "reports": [report_path],
            },
        )
        self.assertTrue(transition["ok"], transition)
        return transition

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
