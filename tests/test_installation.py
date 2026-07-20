from tests.wishgraph_test_support import *  # noqa: F401,F403

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

    def test_fresh_activation_defaults_to_both_required_hosts(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            process = subprocess.run(
                [sys.executable, str(INSTALLER), "--target", str(root), "--json"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            payload = json.loads(process.stdout)
            config = json.loads(
                (root / ".wishgraph/config.json").read_text(encoding="utf-8")
            )
            self.assertEqual(payload["required_hosts"], ["codex", "claude"])
            self.assertEqual(config["required_hosts"], ["codex", "claude"])
            for path in (
                ".codex/hooks.json",
                ".codex/agents/wishgraph-worker.toml",
                ".claude/settings.json",
                ".claude/agents/wishgraph-worker.md",
            ):
                self.assertTrue((root / path).is_file(), path)

    def test_explicit_single_host_activation_persists_only_that_host(self) -> None:
        for host, present, absent in (
            ("codex", ".codex/hooks.json", ".claude/settings.json"),
            ("claude", ".claude/settings.json", ".codex/hooks.json"),
        ):
            with self.subTest(host=host), tempfile.TemporaryDirectory() as tempdir:
                root = Path(tempdir)
                subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
                process = subprocess.run(
                    [
                        sys.executable,
                        str(INSTALLER),
                        "--target",
                        str(root),
                        "--host",
                        host,
                        "--json",
                    ],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                self.assertEqual(process.returncode, 0, process.stderr)
                config = json.loads(
                    (root / ".wishgraph/config.json").read_text(encoding="utf-8")
                )
                self.assertEqual(config["required_hosts"], [host])
                self.assertTrue((root / present).is_file())
                self.assertFalse((root / absent).exists())


    def test_dual_host_activation_preflights_conflicts_and_rolls_back_write_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            conflict = root / ".claude/agents/wishgraph-worker.md"
            conflict.parent.mkdir(parents=True)
            conflict.write_text("user-owned agent\n", encoding="utf-8")
            result = installer_module.activate_project(
                root,
                mode="warn",
                required_hosts=["codex", "claude"],
                force_assets=False,
                install_git_fallback=False,
            )
            self.assertFalse(result["ok"])
            self.assertIn("Refusing to replace", result["failed"][0])
            self.assertFalse((root / ".codex").exists())
            self.assertFalse((root / ".wishgraph").exists())
            self.assertEqual(conflict.read_text(encoding="utf-8"), "user-owned agent\n")

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            original = installer_module.install_host_config

            def fail_second(target: Path, host: str, python_executable: str) -> Path:
                if host == "claude":
                    raise OSError("simulated Claude adapter write failure")
                return original(target, host, python_executable)

            with mock.patch.object(
                installer_module, "install_host_config", side_effect=fail_second
            ):
                result = installer_module.activate_project(
                    root,
                    mode="warn",
                    required_hosts=["codex", "claude"],
                    force_assets=False,
                    install_git_fallback=False,
                )
            self.assertFalse(result["ok"])
            self.assertTrue(result["rolled_back"])
            self.assertFalse((root / ".codex").exists())
            self.assertFalse((root / ".wishgraph").exists())

    def test_dual_host_activation_preserves_unrelated_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            for path in (root / ".codex/hooks.json", root / ".claude/settings.json"):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(
                        {
                            "hooks": {
                                "SessionStart": [
                                    {
                                        "matcher": "custom",
                                        "hooks": [
                                            {"type": "command", "command": "echo keep-me"}
                                        ],
                                    }
                                ]
                            }
                        }
                    ),
                    encoding="utf-8",
                )
            result = installer_module.activate_project(
                root,
                mode="warn",
                required_hosts=["codex", "claude"],
                force_assets=False,
                install_git_fallback=False,
            )
            self.assertTrue(result["ok"], result)
            for path in (root / ".codex/hooks.json", root / ".claude/settings.json"):
                self.assertIn("echo keep-me", path.read_text(encoding="utf-8"))
                self.assertIn("memory_sync.py", path.read_text(encoding="utf-8"))

    def test_upgrade_and_host_repair_preserve_required_hosts(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            self.install_project_runtime(root)
            config_path = root / ".wishgraph/config.json"
            before = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(before["required_hosts"], ["codex"])
            upgraded = subprocess.run(
                [sys.executable, str(INSTALLER), "--target", str(root), "--upgrade"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(upgraded.returncode, 0, upgraded.stderr)
            repaired = installer_module.repair_host_adapter(root, "codex")
            self.assertTrue(repaired["ok"], repaired)
            after = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(after["required_hosts"], ["codex"])
            self.assertFalse((root / ".claude/settings.json").exists())

    def test_doctor_defaults_to_required_hosts_and_keeps_liveness_separate(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            process = subprocess.run(
                [
                    sys.executable,
                    str(INSTALLER),
                    "--target",
                    str(root),
                    "--host",
                    "claude",
                    "--mode",
                    "enforce",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            report = installer_module.doctor_report(root)
            self.assertEqual(set(report["host_adapters"]), {"claude"})
            self.assertTrue(report["healthy"])
            self.assertFalse(report["host_execution_confirmed"])
            self.assertEqual(
                report["host_adapters"]["claude"]["execution"]["state"],
                "unverified",
            )
            unselected = installer_module.doctor_report(root, "codex")
            self.assertFalse(unselected["healthy"])
            self.assertEqual(unselected["host_adapters"]["codex"]["state"], "missing")
            config_path = root / ".wishgraph/config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["required_hosts"] = ["codex"]
            config_path.write_text(json.dumps(config), encoding="utf-8")
            missing_required = installer_module.doctor_report(root)
            self.assertFalse(missing_required["healthy"])
            self.assertEqual(
                missing_required["host_adapters"]["codex"]["state"], "missing"
            )

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
                self.assertEqual(manifest["runtime_version"], 28)

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
            self.assertEqual(execution["observed_runtime_version"], 28)
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
            self.assertEqual(payload["after"]["installed_runtime_version"], 28)
            config = json.loads(
                (root / ".wishgraph" / "config.json").read_text(encoding="utf-8")
            )
            self.assertEqual(config["mode"], "enforce")
            self.assertEqual(config["runtime_version"], 28)

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
                        "required_impact_rows": [
                            "PRD.md",
                            "prompts/DISCUSSION_AI.md",
                            "CUSTOM.md",
                        ],
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
                "claude_worker_provider.py",
                "tool_gate_provider.py",
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
            self.assertEqual(config["version"], 12)
            self.assertEqual(config["runtime_version"], 28)
            self.assertTrue(
                (root / ".wishgraph" / "hooks" / "runtime-manifest.json").is_file()
            )
            codex_agent = root / ".codex" / "agents" / "wishgraph-worker.toml"
            self.assertTrue(codex_agent.is_file())
            self.assertIn(
                'name = "wishgraph-worker"',
                codex_agent.read_text(encoding="utf-8"),
            )
            self.assertEqual(
                config["python_executable"], str(Path(sys.executable).resolve())
            )
            self.assertEqual(config["paths"]["run_report_glob"], "reports/runs/*.md")
            self.assertEqual(
                config["paths"]["run_report_template"],
                "reports/runs/{work_unit_id}-attempt-{attempt}.md",
            )
            self.assertEqual(
                config["paths"]["project_status"], "reports/PROJECT_STATUS.md"
            )
            self.assertEqual(config["paths"]["task_glob"], "tasks/*.md")
            self.assertEqual(
                config["paths"]["task_globs"],
                ["tasks/*.md"],
            )
            self.assertNotIn("discussion_prompt", config["paths"])
            self.assertNotIn("execution_prompt", config["paths"])
            self.assertNotIn("integration_prompt", config["paths"])
            self.assertEqual(
                config["paths"]["revision_glob"], "tasks/revisions/*.md"
            )
            self.assertTrue(config["scan_worker_refs_for_status"])
            self.assertEqual(config["project_status_max_lines"], 160)
            self.assertEqual(config["project_status_max_chars"], 12000)
            self.assertTrue(config["orchestration_gate_enabled"])
            self.assertEqual(config["read_gate_mode"], "host_dependent")
            self.assertEqual(
                config["required_impact_rows"],
                [
                    "PRD.md",
                    "ARCHITECTURE.md",
                    "CODEMAP.md",
                    "CONVENTIONS.md",
                    "CUSTOM.md",
                ],
            )

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


class OneCommandInstallerTests(unittest.TestCase):
    def test_top_level_installers_keep_current_host_separate_from_project_hosts(self) -> None:
        shell = TOP_LEVEL_INSTALLER.read_text(encoding="utf-8")
        powershell = POWERSHELL_INSTALLER.read_text(encoding="utf-8")
        self.assertIn('project_hosts="all"', shell)
        self.assertIn('--host "$project_hosts"', shell)
        self.assertIn('--current-host "$hook_host"', shell)
        self.assertIn('[string]$ProjectHosts = "all"', powershell)
        self.assertIn('"--host", $ProjectHosts', powershell)
        self.assertIn('"--current-host", $hookHost', powershell)

    def test_windows_installer_forces_utf8_for_python_children(self) -> None:
        content = POWERSHELL_INSTALLER.read_text(encoding="utf-8")
        self.assertIn('$env:PYTHONUTF8 = "1"', content)
        self.assertIn('$env:PYTHONIOENCODING = "utf-8"', content)

    @unittest.skipUnless(shutil.which("bash"), "bash is required")
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
            self.assertIn("adds no Python packages", process.stdout)
            self.assertIn("Prerequisite check passed", process.stdout)
            self.assertFalse((root / "codex-home").exists())
            self.assertFalse((project / ".wishgraph").exists())

    @unittest.skipUnless(shutil.which("bash"), "bash is required")
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

    @unittest.skipUnless(shutil.which("bash"), "bash is required")
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

    @unittest.skipUnless(shutil.which("bash"), "bash is required")
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
            self.assertTrue((project / ".claude" / "settings.json").exists())
            config = json.loads((project / ".wishgraph" / "config.json").read_text())
            self.assertEqual(config["mode"], "warn")
            self.assertEqual(config["required_hosts"], ["codex", "claude"])

    @unittest.skipUnless(shutil.which("bash"), "bash is required")
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
            self.assertTrue((project / ".claude" / "settings.json").exists())
            self.assertEqual(config["required_hosts"], ["codex", "claude"])

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

    @unittest.skipUnless(shutil.which("bash"), "bash is required")
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

    @unittest.skipUnless(shutil.which("bash"), "bash is required")
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
            "adds no Python packages",
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

    def test_role_rules_live_in_skill_and_adapters(self) -> None:
        worker = (
            ROOT / "skills" / "wishgraph" / "references" / "worker-execution.md"
        ).read_text(encoding="utf-8")
        bootstrap = (
            ROOT / "skills" / "wishgraph" / "references" / "project-bootstrap.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Stable role rules come from the installed Skill", bootstrap)
        self.assertIn("exact Task or Revision", worker)
        self.assertFalse(any((ROOT / "templates" / "prompts").glob("*.md")))

    def test_worker_launch_protocol_requires_visible_human_authorized_tasks(self) -> None:
        reference = (
            ROOT
            / "skills"
            / "wishgraph"
            / "references"
            / "worker-execution.md"
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

    def test_integration_rules_are_discussion_local_and_lease_bound(self) -> None:
        revisions = (
            ROOT / "skills" / "wishgraph" / "references" / "task-revisions.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Integration lease", revisions)
        self.assertIn("same integration change", revisions)
        self.assertIn("Project Status", revisions)

    def test_hooks_are_not_semantic_reviewers_or_agent_launchers(self) -> None:
        runtime = (HOOK_ASSETS / "memory_sync.py").read_text(encoding="utf-8")
        reference = (
            ROOT / "skills" / "wishgraph" / "references" / "memory-sync-hooks.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Hooks do not start agents", runtime)
        self.assertIn("do not write semantic project memory", reference)
        self.assertIn("launch Workers", reference)
        self.assertNotIn("subprocess.Popen", runtime)
