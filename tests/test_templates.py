from tests.wishgraph_test_support import *  # noqa: F401,F403

class TemplateMirrorTests(unittest.TestCase):
    def test_public_guides_match_native_worker_contract(self) -> None:
        readme_en = (ROOT / "README.md").read_text(encoding="utf-8")
        readme_zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
        getting_started = (ROOT / "GETTING_STARTED.md").read_text(
            encoding="utf-8"
        )
        getting_started_zh = (ROOT / "GETTING_STARTED.zh-CN.md").read_text(
            encoding="utf-8"
        )
        memory_sync_en = (ROOT / "docs" / "memory-sync-hooks.md").read_text(
            encoding="utf-8"
        )
        memory_sync_zh = (
            ROOT / "docs" / "memory-sync-hooks.zh-CN.md"
        ).read_text(encoding="utf-8")
        state_machine = (
            ROOT / "docs" / "orchestration-state-machine.md"
        ).read_text(encoding="utf-8")
        claude_adapter = (
            ROOT / "adapters" / "claude-code" / "CLAUDE.md"
        ).read_text(encoding="utf-8")
        generic_adapter = (
            ROOT / "adapters" / "generic" / "README.md"
        ).read_text(encoding="utf-8")
        conventions = (ROOT / "templates" / "CONVENTIONS.md").read_text(
            encoding="utf-8"
        )

        for content in (readme_en, readme_zh, state_machine):
            self.assertIn("claude --bg --agent wishgraph-worker", content)
            self.assertIn("Claim", content)
        self.assertIn("thread/session ID", readme_en)
        self.assertIn("thread/session ID", readme_zh)
        self.assertIn("thread ID", state_machine)
        self.assertIn("Authorization does not let Discussion implement", getting_started)
        for heading in (
            "## The framework",
            "## One-minute tour",
            "## Install in 60 seconds",
            "## FAQ",
            "## Safety boundaries",
            "## Go deeper",
        ):
            self.assertIn(heading, readme_en)
        for heading in (
            "## 整体框架",
            "## 一分钟看懂一次完整流程",
            "## 60 秒安装",
            "## 常见问题",
            "## 安全边界",
            "## 继续深入",
        ):
            self.assertIn(heading, readme_zh)
        self.assertIn("Role-Specific Read Scope", claude_adapter)
        self.assertIn("complete source tree", claude_adapter)
        self.assertIn("supplies no native Worker creation", generic_adapter)
        self.assertIn("engineering rules specific to this project", conventions)
        self.assertNotIn("managed background Agent is allowed", conventions)
        self.assertNotIn("## Roles", conventions)
        self.assertNotIn("Flow Phase", conventions)
        self.assertIn("No prompt migration is required", getting_started)
        self.assertIn("creates no project-level prompts", readme_en)
        self.assertIn("不创建项目级 Prompt", readme_zh)
        self.assertIn("default `warn` mode is fully advisory", getting_started)
        self.assertIn("默认 `warn` 是完全非阻断的建议模式", getting_started_zh)
        for content in (readme_en, readme_zh, getting_started, getting_started_zh):
            self.assertNotIn("stable entry prompts", content)
            self.assertNotIn("入口提示词", content)
            self.assertNotIn(".tasks/build/", content)
            self.assertNotIn("about 0.5 MB", content)
            self.assertNotIn("约 0.5 MB", content)
        for content in (memory_sync_en, memory_sync_zh):
            self.assertIn("reports/runs/<work-unit-id>-attempt-N.md", content)
            self.assertNotIn("reports/runs/<work-unit-id>.md", content)
        self.assertNotIn("output the full prompt for copying", claude_adapter)
        self.assertNotIn("full prompt for manual transfer", conventions)
        self.assertNotIn("Never start workers in the background by default", conventions)
        self.assertNotIn("运行时配置版本为 10", state_machine)

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

        guide = (ROOT / "templates" / "README.md").read_text(encoding="utf-8")
        bootstrap = (
            ROOT / "skills" / "wishgraph" / "references" / "project-bootstrap.md"
        ).read_text(encoding="utf-8")
        self.assertIn("tasks/*.md", bootstrap)
        self.assertIn("does not create project-level prompt files", guide)
        self.assertIn("does not restrict user-owned root files", guide)
        self.assertNotIn("prompts/DISCUSSION_AI.md", bootstrap)
        self.assertIn("Generate `reports/runs/<work-unit-id>-attempt-N.md` only when needed", bootstrap)
        self.assertFalse(any((ROOT / "templates" / "prompts").glob("*.md")))

    def test_project_documents_have_single_responsibilities(self) -> None:
        prd = (ROOT / "templates" / "PRD.md").read_text(encoding="utf-8")
        codemap = (ROOT / "templates" / "CODEMAP.md").read_text(encoding="utf-8")
        conventions = (ROOT / "templates" / "CONVENTIONS.md").read_text(
            encoding="utf-8"
        )
        status = (ROOT / "templates" / "reports" / "PROJECT_STATUS.md").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("Current Progress", prd)
        self.assertIn("Verified / Unverified", codemap)
        self.assertNotIn("## Roles", conventions)
        self.assertNotIn("Orchestration Snapshot", status)
        self.assertNotIn("Shared Memory Impact", status)
        self.assertIn("only user-readable dynamic project snapshot", status)

        bootstrap = (
            ROOT / "skills" / "wishgraph" / "references" / "project-bootstrap.md"
        ).read_text(encoding="utf-8")
        task = (ROOT / "templates" / "tasks" / "build" / "NNN-task.md").read_text(
            encoding="utf-8"
        )
        for expected in (
            "responsibility the document actually performs",
            "referenced paths and key symbols exist",
            "build and test commands are available",
            "obviously conflicts",
            "marks unknown facts explicitly",
        ):
            self.assertIn(expected, bootstrap)
        self.assertNotIn("document-registry", bootstrap)
        self.assertIn("## Readiness Notes", task)
        self.assertIn("Permission and risk boundaries", task)
