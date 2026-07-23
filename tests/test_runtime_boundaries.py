from tests.wishgraph_test_support import *  # noqa: F401,F403

class RuntimeBoundaryTests(unittest.TestCase):
    def test_release_workflow_revalidates_an_immutable_tag_from_project_cwd(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("RELEASE_REF: ${{ inputs.release_ref || github.ref_name }}", workflow)
        self.assertIn('(cd "$project" && python .wishgraph/hooks/memory_sync.py status)', workflow)
        self.assertIn("Push-Location $project", workflow)
        self.assertNotIn('python "$project/.wishgraph/hooks/memory_sync.py" status', workflow)

    def test_release_installers_pin_the_packaged_product_version(self) -> None:
        version = (ROOT / "skills" / "wishgraph" / "VERSION").read_text(
            encoding="utf-8"
        ).strip()
        self.assertEqual(version, "0.1.2")
        bash_installer = TOP_LEVEL_INSTALLER.read_text(encoding="utf-8")
        powershell_installer = POWERSHELL_INSTALLER.read_text(encoding="utf-8")
        self.assertIn('repo_ref="${WISHGRAPH_REF:-v0.1.2}"', bash_installer)
        self.assertIn('else { "v0.1.2" }', powershell_installer)
        for document in (
            "README.md",
            "README.zh-CN.md",
            "GETTING_STARTED.md",
            "GETTING_STARTED.zh-CN.md",
        ):
            content = (ROOT / document).read_text(encoding="utf-8")
            self.assertIn("/v0.1.2/scripts/install-wishgraph", content)
            self.assertNotIn("/main/scripts/install-wishgraph", content)

    def test_commit_benchmark_budget_does_not_relax_ordinary_tool_gate(self) -> None:
        benchmark_path = (
            ROOT / "skills" / "wishgraph" / "scripts" / "benchmark_hooks.py"
        )
        spec = importlib.util.spec_from_file_location(
            "wishgraph_benchmark_budget", benchmark_path
        )
        assert spec and spec.loader
        benchmark = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(benchmark)
        self.assertEqual(benchmark.PRETOOL_LIMIT_MS, 200.0)
        self.assertEqual(benchmark.COMMIT_PRETOOL_LIMIT_MS, 300.0)

    def test_benchmark_fixture_matches_the_host_receipt_contract(self) -> None:
        benchmark_path = (
            ROOT / "skills" / "wishgraph" / "scripts" / "benchmark_hooks.py"
        )
        spec = importlib.util.spec_from_file_location(
            "wishgraph_benchmark_hooks", benchmark_path
        )
        assert spec and spec.loader
        benchmark = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(benchmark)
        with tempfile.TemporaryDirectory() as tempdir:
            root, runtime = benchmark.setup_fixture(Path(tempdir))
            self.assertTrue((root / ".git" / "wishgraph" / "claims").is_dir())
            self.assertTrue(runtime.is_file())

    def test_runtime_dependencies_follow_the_four_boundaries(self) -> None:
        local_modules = {
            "git_state",
            "workflow_state",
            "policy",
            "host_adapter",
            "codex_worker_provider",
            "claude_worker_provider",
            "tool_gate_provider",
        }
        public_boundaries = local_modules - {
            "codex_worker_provider",
            "claude_worker_provider",
            "tool_gate_provider",
        }
        expected = {
            "git_state.py": set(),
            "workflow_state.py": set(),
            "policy.py": {"git_state", "workflow_state"},
            "host_adapter.py": {
                "git_state",
                "policy",
                "workflow_state",
                "codex_worker_provider",
                "claude_worker_provider",
                "tool_gate_provider",
            },
            "codex_worker_provider.py": {"git_state", "workflow_state"},
            "claude_worker_provider.py": {"git_state", "workflow_state"},
            "tool_gate_provider.py": {"git_state", "policy", "workflow_state"},
            "memory_sync.py": public_boundaries | {"tool_gate_provider"},
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
        self.assertIn(claude_worker_provider_module.CLAUDE_WORKER_AGENT_MARKER, content)
        self.assertIn("acquire a Worker Claim", content)
        self.assertIn("claude agents --json --all", content)
        self.assertIn("session get <full-session-id>", content)
        self.assertIn("Do not read unrelated Tasks", content)
        self.assertIn("Write exactly one immutable Run Report", content)
        self.assertIn("Release an acquired Claim", content)

    def test_global_host_adapter_preserves_settings_and_is_noop_when_project_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            home = Path(tempdir) / ".claude"
            home.mkdir(parents=True)
            settings_path = home / "settings.json"
            settings_path.write_text(
                json.dumps(
                    {
                        "env": {"WISHGRAPH_TEST_KEEP": "unchanged"},
                        "permissions": {"allow": ["Read"]},
                        "hooks": {
                            "SessionStart": [
                                {
                                    "hooks": [
                                        {
                                            "type": "command",
                                            "command": "echo keep-global-hook",
                                        },
                                        {
                                            "type": "command",
                                            "command": "python3 ${CLAUDE_PROJECT_DIR}/.wishgraph/hooks/memory_sync.py session-start --host claude",
                                        },
                                    ]
                                }
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )
            installer = ROOT / "skills" / "wishgraph" / "scripts" / "install_global_adapter.py"
            installed = subprocess.run(
                [sys.executable, str(installer), "--host", "claude", "--config-home", str(home)],
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(installed.returncode, 0, installed.stderr)
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertEqual(settings["env"], {"WISHGRAPH_TEST_KEEP": "unchanged"})
            self.assertEqual(settings["permissions"]["allow"], ["Read"])
            self.assertIn("global_host_hook.py", json.dumps(settings["hooks"]))
            self.assertIn("echo keep-global-hook", json.dumps(settings["hooks"]))
            self.assertNotIn(
                ".wishgraph/hooks/memory_sync.py", json.dumps(settings["hooks"])
            )

            project = Path(tempdir) / "plain-project"
            project.mkdir()
            subprocess.run(["git", "-C", str(project), "init", "-q"], check=True)
            bridge = ROOT / "skills" / "wishgraph" / "scripts" / "global_host_hook.py"
            result = subprocess.run(
                [sys.executable, str(bridge), "session-start", "--host", "claude"],
                cwd=project,
                input=json.dumps({"cwd": str(project), "session_id": "plain"}),
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {})

    def test_global_host_adapter_maps_hook_keys_to_cli_event_arguments(self) -> None:
        expected_events = {
            "SessionStart": "session-start",
            "UserPromptSubmit": "user-prompt-submit",
            "PreToolUse": "pre-tool-use",
            "Stop": "stop",
            "TaskCompleted": "task-completed",
        }
        installer = ROOT / "skills" / "wishgraph" / "scripts" / "install_global_adapter.py"
        for host, filename in (("codex", "hooks.json"), ("claude", "settings.json")):
            with self.subTest(host=host), tempfile.TemporaryDirectory() as tempdir:
                home = Path(tempdir) / f".{host}"
                installed = subprocess.run(
                    [
                        sys.executable,
                        str(installer),
                        "--host",
                        host,
                        "--config-home",
                        str(home),
                    ],
                    text=True,
                    encoding="utf-8",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                self.assertEqual(installed.returncode, 0, installed.stderr)
                config = json.loads((home / filename).read_text(encoding="utf-8"))
                for hook_key, groups in config["hooks"].items():
                    self.assertIn(hook_key, expected_events)
                    event_argument = expected_events[hook_key]
                    for group in groups:
                        for hook in group.get("hooks", []):
                            command = shlex.split(hook["command"])
                            self.assertEqual(command[2], event_argument)
                            self.assertIn(
                                f" {event_argument} --host {host}",
                                hook["commandWindows"],
                            )

    def test_global_host_bridge_accepts_every_mapped_event_argument(self) -> None:
        bridge = ROOT / "skills" / "wishgraph" / "scripts" / "global_host_hook.py"
        with tempfile.TemporaryDirectory() as tempdir:
            project = Path(tempdir) / "plain-project"
            project.mkdir()
            subprocess.run(["git", "-C", str(project), "init", "-q"], check=True)
            for event in (
                "session-start",
                "user-prompt-submit",
                "pre-tool-use",
                "stop",
                "task-completed",
            ):
                with self.subTest(event=event):
                    result = subprocess.run(
                        [sys.executable, str(bridge), event, "--host", "claude"],
                        cwd=project,
                        input=json.dumps({"cwd": str(project)}),
                        text=True,
                        encoding="utf-8",
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertNotIn("usage:", result.stderr.lower())

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

        self.assertEqual(
            memory_sync.parse_user_prompt("执行 012b terra 推理 高"),
            {
                "action": "execute",
                "task_id": "012b",
                "authorizes_execution": True,
                "execution_profile": {
                    "model": "gpt-5.6-terra",
                    "reasoning_effort": "high",
                },
            },
        )
        self.assertEqual(
            memory_sync.parse_user_prompt("execute 012b sonnet high"),
            {
                "action": "execute",
                "task_id": "012b",
                "authorizes_execution": True,
                "execution_profile": {
                    "model": "sonnet",
                    "reasoning_effort": "high",
                },
            },
        )
        self.assertEqual(
            memory_sync.parse_user_prompt("执行 012b terra 极高"),
            {
                "action": "execute",
                "task_id": "012b",
                "authorizes_execution": True,
                "execution_profile": {
                    "model": "gpt-5.6-terra",
                    "reasoning_effort": "xhigh",
                },
            },
        )

        for prompt in (
            "执行任务",
            "执行任务 012",
            "请执行 012 任务",
            "执行 012 和 013 任务",
            "执行 12 任务",
            "我们执行 012 任务",
            "执行 012b unknown-model 高",
            "执行 012 任务吧",
        ):
            with self.subTest(prompt=prompt):
                self.assertIsNone(memory_sync.parse_user_prompt(prompt))

    def test_contextual_authorization_accepts_common_replies_but_not_conditions(self) -> None:
        for prompt in (
            "批准",
            "批准，用 terra 极高",
            "行，就按推荐执行吧",
            "没问题，开始执行",
            "Sounds good, go ahead",
            "OK, use sonnet high",
        ):
            with self.subTest(prompt=prompt):
                self.assertTrue(memory_sync.is_contextual_approval(prompt))
        for prompt in (
            "可以，不过先改验收标准",
            "先别执行",
            "可以吗？",
            "我们讨论一下颜色",
            "批准，删除数据库",
            "批准 012 任务",
        ):
            with self.subTest(prompt=prompt):
                self.assertFalse(memory_sync.is_contextual_approval(prompt))

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
                    encoding="utf-8",
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
            "In `enforce`, acquire a fresh Claim",
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
