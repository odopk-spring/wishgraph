# Installation and Prerequisite Routing

Use this reference only for Skill installation, project-hook setup, environment checks, or setup failures.

## Contents

- Default decision and guided continuation
- Preflight and cost notice
- Platform dependency guidance
- Installation execution
- Verification

## Default Decision

Infer the active host from the current agent. Use `codex` for Codex and `claude` for Claude Code. Default an unspecified setup request to safe `warn` hooks. Use strict `enforce --git-hook` only when the user explicitly asks for strict or blocking behavior.

Make a recommendation before asking. Use this routing:

- Recommend **safe setup** for a first active project, an unfamiliar repository, or any repository that has not completed a WishGraph closeout.
- Recommend **Skill only** when there is no target project, the user is only evaluating WishGraph, or they explicitly do not want project files.
- Recommend **strict setup** only when the Git worktree is clean, the governance skeleton exists, safe mode already completed successfully, and the user wants mechanical blocking.

Use a compact choice message in the user's language. Include the detected host/system, one-sentence rationale, WishGraph's own size/time, and the recommendation first. Example:

```text
我检测到你正在 Codex 中配置一个现有 Git 项目。推荐“安全配置”：安装 Skill 和提醒型 Hooks，不会阻止结束或提交；WishGraph Skill 约 0.5 MB，项目 hooks 约 0.3 MB，通常不到 1 分钟。

你可以直接回复“按推荐来”，也可以说“只装 Skill”或“严格配置”。
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
5. Confirm the current host. Ask only if the host is genuinely unknowable.

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
python3 scripts/install_project_hooks.py --target PROJECT_ROOT --host codex --mode warn
python3 scripts/install_project_hooks.py --target PROJECT_ROOT --host claude --mode warn
```

Use `--mode enforce --git-hook` for an explicitly selected strict setup. The installer detects the repository root and preserves unrelated hook configuration.

For first-time macOS or Linux installation, the repository bootstrap script supports `--check`, `--setup-project`, and `--strict`. For Windows, use `scripts/install-wishgraph.ps1` with `-Check`, `-SetupProject`, and `-Strict`.

## Verification

After installation:

1. Read `.wishgraph/config.json` and confirm the selected mode.
2. Confirm only the current host file was installed: `.codex/hooks.json` or `.claude/settings.json`.
3. Confirm the host commands use the exact Python executable recorded in `.wishgraph/config.json`; then run that interpreter with `.wishgraph/hooks/memory_sync.py check --scope worktree`.
4. Treat a missing governance skeleton as a next setup step, not a dependency failure; safe mode remains non-blocking.
5. Tell Codex users to trust the repository and review `/hooks`.
6. Finish with the selected mode, verified host files, dependency status, and exactly one recommended next action. Do not teach hook internals unless asked.
