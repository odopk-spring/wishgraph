# Installation and Prerequisite Routing

Use this reference only for Skill installation, project-hook setup, environment checks, or setup failures.

## Contents

- Default decision and guided continuation
- Explicit project opt-in
- Preflight and cost notice
- Platform dependency guidance
- Installation execution
- Health checks, safe upgrade, and current-host recovery
- Verification

## Explicit Project Opt-In

Global Skill installation means WishGraph is available, not active in every folder. A project is enabled only when its Git root contains a readable `.wishgraph/config.json` whose `mode` is `warn` or `enforce`.

The user-level installers also merge a global no-op Host Adapter into the selected host config; Claude user installation also installs the managed global Worker Agent. The bridge returns immediately outside an enabled Git project, so global capability does not activate WishGraph elsewhere. Project-local adapters remain supported for teams that want repository-contained host configuration.

- In a project with no config or `mode: off`, generic phrases such as `开始讨论`, `刷新项目状态`, and `执行 012 任务` are ordinary user requests. Do not bootstrap WishGraph, load its References, or create files from those phrases.
- `使用 WishGraph`, `为这个项目启用 WishGraph`, `Use WishGraph`, or an equally explicit request naming WishGraph authorizes the recommended safe project setup unless the user names another mode.
- Command-line `--setup-project` or `-SetupProject` is also explicit project activation.
- After activation succeeds, keep the current session `neutral`. Give one next action: reopen the current Agent session; the first input in the reopened session is `开始讨论` / `Start discussion`.
- A later `开始讨论` event enters Discussion only while the project remains enabled. It never enables an inactive project by itself.

## Default Decision

Detect the active Agent only as `current_host`. Separately ask which `required_hosts` the project should support:

- **Codex + Claude Code** (`all`) — recommended and the CLI default.
- **Codex only** (`codex`).
- **Claude Code only** (`claude`).

Never infer the project scope from the Agent running setup. Persist the choice in `.wishgraph/config.json` as `required_hosts`. Default an unspecified CLI setup to `all` and safe `warn` hooks. Use strict `enforce --git-hook` only when the user explicitly asks for strict or blocking behavior.

Make a recommendation before asking, except that an explicit `使用 WishGraph` / `Use WishGraph` activation request already selects the recommended safe setup. Use this routing:

- Recommend **safe dual-host setup** for a first active project, an unfamiliar repository, or any repository that has not completed a WishGraph closeout.
- Recommend **Skill only** when there is no target project, the user is only evaluating WishGraph, or they explicitly do not want project files.
- Recommend **strict setup** only when the Git worktree is clean, the governance skeleton exists, safe mode already completed successfully, and the user wants mechanical blocking.

Use a compact choice message in the user's language. Include the detected host/system, one-sentence rationale, WishGraph's own size/time, and the recommendation first. Example:

```text
我检测到你正在 Codex 中配置一个现有 Git 项目。推荐“安全配置”：安装 Skill 和提醒型 Hooks，不会阻止结束或提交；WishGraph Skill 约 0.5 MB，项目 hooks 约 0.3 MB，通常不到 1 分钟。

这个项目需要在哪些 Agent 中使用 WishGraph？
- Codex + Claude Code（推荐）
- 仅 Codex
- 仅 Claude Code

你也可以回复“按推荐来”，选择 Codex + Claude Code 的安全配置。
```

Do not expose command flags in the question.

## Guided Continuation

Use four visible stages without dumping a long checklist:

1. **选择**: recommend a mode and obtain one natural-language choice.
2. **环境检查**: detect dependencies and repository state.
3. **安装配置**: continue automatically through approved local installation steps.
4. **验证完成**: verify files, mode, and checker behavior; give one next action.

Do not repeatedly ask for confirmation after the user selects a mode. Pause only when new authority or external user action is required.

For a missing dependency, use this response shape:

```text
安装进度：环境检查
缺少：Python 3.9+
用途：运行本地记忆检查，不会安装第三方 Python 包
预计：100-300 MB，2-10 分钟
推荐：<platform-specific command or official route>
完成后回复“已安装 Python”，我会重新检查并继续。
```

For a non-Git folder, recommend `git init`, explain that it adds under 1 MB and normally takes under a second, ask permission, then continue automatically after approval.

If a restart is required, give an exact resume phrase such as: `继续刚才的 WishGraph 安全配置`.

## Preflight

Check before writing project configuration:

1. Detect Windows, macOS, or Linux.
2. Confirm `git` is available.
3. For hooks, confirm Python 3.9 or newer is available. No pip packages are required.
4. Confirm the target exists and detect its Git root. If it is not a repository, ask before running `git init`.
5. Detect `current_host` for the current receipt, but obtain `required_hosts` independently.

Do not install Git, Python, Homebrew, package managers, or system developer tools without explicit user approval.

## Rough Cost Notice

These are intentionally broad estimates; hardware, mirrors, package managers, and existing dependencies change the result.

| Component | Typical Added Disk | Typical Time |
|---|---:|---:|
| WishGraph Skill | about 0.5 MB | under 1 minute |
| Project hooks | about 0.3 MB | under 10 seconds |
| Git package | about 200-500 MB | about 2-10 minutes |
| Python runtime | about 100-300 MB | about 2-10 minutes |
| Apple Command Line Tools route for Git | about 1-3 GB | about 5-30 minutes |
| `git init` metadata | under 1 MB | normally under 1 second |

Report only missing-component estimates. Do not burden users who already pass preflight.

## Dependency Guidance

### Windows

- Git: `winget install --id Git.Git -e --source winget`
- Python install manager: `winget install 9NQ7512CXL7T`, then `py install default` for a runtime.
- After installation, reopen PowerShell and re-check `git --version` and `python --version` or `py -3 --version`.

### macOS

- Git: `xcode-select --install`; if Homebrew already exists, `brew install git` is a smaller alternative.
- Python: `brew install python`, or use the installer from `https://www.python.org/downloads/macos/`.
- Explain the larger Apple Command Line Tools estimate before recommending that route.

### Linux

- Debian / Ubuntu: `sudo apt install git python3`
- Fedora: `sudo dnf install git python3`
- Arch: `sudo pacman -S git python`
- Do not guess a package manager when the distribution can be detected.

## Execution

For an already installed Skill, run the bundled installer from the Skill root:

```bash
python3 scripts/install_project_hooks.py --target PROJECT_ROOT --mode warn
python3 scripts/install_project_hooks.py --target PROJECT_ROOT --host codex --mode warn
python3 scripts/install_project_hooks.py --target PROJECT_ROOT --host claude --mode warn
```

The first command installs both project-local adapters. The other commands are explicit single-host choices. Dual-host activation preflights and snapshots the runtime, config, both adapter files, and both Worker Agent definitions before writing; any conflict or failed write restores the whole snapshot. Existing unrelated Hook groups are merged and preserved. A globally installed current Adapter and Agent may satisfy host execution without duplicating `.claude/settings.json` in every enabled project.

Old configs without `required_hosts` retain the Adapter scope already installed. If no managed Adapter can be identified, they are interpreted as requiring both hosts so Doctor reports the incomplete state instead of silently claiming protection. The next successful activation or upgrade persists the resolved value. Upgrade preserves an existing choice; repair changes only the named Adapter.

Use `--mode enforce --git-hook` for an explicitly selected strict setup. The installer detects the repository root and preserves unrelated hook configuration.

For first-time macOS or Linux installation, the repository bootstrap script supports `--check`, `--setup-project`, and `--strict`. For Windows, use `scripts/install-wishgraph.ps1` with `-Check`, `-SetupProject`, and `-Strict`.

## Health, Upgrade, And Current-Host Recovery

Normal users may say `检查 WishGraph 状态`, `更新这个项目的 WishGraph`, or `修复当前宿主的 WishGraph Hooks`. Keep flags internal unless the user asks for them.

For an explicit health check or recovery request in an existing project, run Doctor first. It reads only fixed WishGraph configuration, the manifest-listed runtime files, selected host adapters, the configured Python executable, minimal governance entry files, and bounded host receipts. It does not scan business source or write anything:

```bash
python3 scripts/install_project_hooks.py --target PROJECT_ROOT --doctor --json
python3 scripts/install_project_hooks.py --target PROJECT_ROOT --host codex --doctor --json
```

Without `--host`, Doctor checks exactly the configured `required_hosts`. Adapter static health and host liveness are separate: every required Adapter may be current while an unopened host remains `unverified`. That is a successful static installation with a pending first-session verification, not a failed installation.

Doctor separates static installation health from observed host execution. `SessionStart` and `UserPromptSubmit` write bounded liveness receipts under the Git common directory at `.git/wishgraph/host-observations/`; Doctor only reads them. A current receipt proves that the selected host recently invoked the installed runtime. No receipt, an older runtime version, or a receipt older than the host adapter yields `restart_agent_session` instead of a false active claim. Never write receipts from `PreToolUse`.

Use `next_action` as the route:

- `use_wishgraph`: the project is inactive; require explicit activation.
- `upgrade_project_runtime`: current bundled files only need metadata repair, or the installed fingerprints match a bundled known version, so a safe upgrade may continue.
- `review_runtime_changes`: preserve incomplete, unknown, or locally modified runtime files and ask before `--force-assets`.
- `repair_current_host_adapter`: repair only the host in the current window.
- `restart_agent_session`: the files are current but this host has not recently invoked them; reopen the Agent session and try `开始讨论`.
- `bootstrap_project_memory` or `start_discussion`: continue normal setup or entry.

Safe project upgrade is atomic and preserves the configured `mode`. It snapshots every manifest-listed runtime file, the runtime manifest, and project config in memory; a failed write restores the snapshot and leaves no backup files:

```bash
python3 scripts/install_project_hooks.py --target PROJECT_ROOT --upgrade --json
```

Do not use `--force-assets` automatically. It is an explicit override for a human-reviewed local customization, incomplete install, version conflict, or intentional downgrade. Updating a global Skill changes only the bundled source; project-local runtimes are upgraded separately.

When the runtime is current but the active host adapter is missing or outdated, repair that host only. The merge removes obsolete WishGraph handlers, preserves unrelated handlers, and is idempotent:

```bash
python3 scripts/install_project_hooks.py --target PROJECT_ROOT --host codex --repair-host-adapter --json
python3 scripts/install_project_hooks.py --target PROJECT_ROOT --host claude --repair-host-adapter --json
```

Never pass `--host all` for a one-host repair. To add a host later, run activation explicitly with `--host all`, verify the persisted `required_hosts`, then reopen the newly enabled Agent. To remove a host, explicitly reactivate with the remaining host selection. A single-host project is valid, but an ordinary session in the unselected host is not mechanically protected.

## Verification

After installation:

1. Read `.wishgraph/config.json` and confirm the selected mode.
2. Confirm every selected `required_host` has one current Adapter and Worker definition, either project-local or user-global. Refuse to overwrite a same-path non-WishGraph Agent definition. Claude background launch injects its Worktree settings per launch, so missing project `.claude/settings.json` is not by itself a failure and user settings remain unchanged.
3. Confirm the host commands use the exact Python executable recorded in `.wishgraph/config.json`; then run that interpreter with `.wishgraph/hooks/memory_sync.py check --scope worktree`.
4. Treat a missing governance skeleton as a next setup step, not a dependency failure; safe mode remains non-blocking.
5. Finish with the selected mode and one next action: reopen the current Agent session, then use `开始讨论` / `Start discussion`. Do not teach Hook internals during normal setup.
6. Only if the reopened session does not respond, run Doctor. For an unverified Codex receipt, direct the user to `/hooks`; for Claude Code CLI, additionally allow `claude doctor`. Mention `--bare`, `--safe-mode`, or setting-source overrides only when the diagnosis requires them.

`warn` and `enforce` operate only when the host has installed and invoked its Adapter. They are host-tool gates, not an operating-system sandbox. Without a Claude Adapter, a normal Claude Code session cannot be detected or blocked by WishGraph. The optional Git pre-commit hook is only a commit-time fallback, not write-time enforcement.
