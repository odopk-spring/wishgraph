# Claude Code Adapter

Claude Code can use WishGraph as a native skill. Claude Code skills live in a skill directory with `SKILL.md`; the skill directory name becomes the slash command name. Because this repository installs the folder as `wishgraph`, WishGraph runs as:

```text
/wishgraph
```

Claude Code project memory can also use `CLAUDE.md`; the template in this folder is a lightweight bridge for teams that want every Claude Code session to know the WishGraph workflow.

Official references:

- Claude Code skills: https://code.claude.com/docs/en/skills
- Claude Code memory and `CLAUDE.md`: https://code.claude.com/docs/en/memory

## Install As A User Skill

Use this when you want `/wishgraph` available in all Claude Code projects:

```bash
curl -fsSL https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.sh | bash -s -- claude-user
```

Then restart Claude Code if needed and run:

```text
/wishgraph recommend the best installation for this project, let me choose in natural language, then continue through prerequisites, setup, and verification
```

On Windows PowerShell, use the native installer:

```powershell
& ([scriptblock]::Create((irm 'https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.ps1'))) claude-user -SetupProject
```

For bilingual Chinese and English handoff, add:

```text
Use bilingual Chinese and English for user-facing prompts and summaries. Keep file paths, commands, and code identifiers unchanged.
```

## Install Into One Project

Use this when a team wants the skill checked into one repository:

```bash
curl -fsSL https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.sh | bash -s -- claude-project
```

This creates:

```text
.claude/skills/wishgraph/
```

Review the skill before trusting the workspace.

## Add Project Memory

Copy this adapter's `CLAUDE.md` into the target project root or merge it into an existing project `CLAUDE.md`:

```bash
cp adapters/claude-code/CLAUDE.md /path/to/project/CLAUDE.md
```

Use `CLAUDE.md` for always-loaded project rules. Keep large task procedures in the `/wishgraph` skill and in WishGraph project files such as `PRD.md`, `CODEMAP.md`, `tasks/build/*.md`, `reports/runs/*.md`, and `reports/PROJECT_STATUS.md`.

## Install Project Memory-Sync Hooks

The lowest-learning-cost option is to ask:

```text
/wishgraph 为这个项目推荐合适的 Hooks 配置，让我用自然语言选择，然后继续配置到验证完成
```

For a manual warning-mode installation:

```bash
python3 ~/.claude/skills/wishgraph/scripts/install_project_hooks.py \
  --target /path/to/project \
  --host claude \
  --mode warn
```

This safely merges `SessionStart`, `PreToolUse`, `Stop`, and `TaskCompleted` groups into `.claude/settings.json`, defaults an unset Worktree `baseRef` to `head`, preserves existing Worktree entries while adding `.wishgraph` to `worktree.symlinkDirectories`, and installs the managed `.claude/agents/wishgraph-worker.md` definition. Switch `.wishgraph/config.json` to `enforce` after a successful closeout. See [`docs/memory-sync-hooks.md`](../../docs/memory-sync-hooks.md).

## Recommended Claude Code Flow

1. Explicitly enable WishGraph in the target project:

   ```text
   /wishgraph Use WishGraph for this project.
   ```

   Safe setup leaves the current session neutral. Reopen Claude Code, then say `Start discussion`. A global Skill install or the phrase `Start discussion` alone does not activate an unconfigured project.

2. Let each role read only what it needs:

   - Discussion starts from the concise handoff, current Project Status, and active state; it opens product or architecture files only for the current question.
   - Worker reads the exact Task or Revision, `prompts/EXECUTION_AI.md`, necessary state, and source files inside its scope.
   - Integration reads selected reports and only the shared files they affect.

   Existing repositories reuse equivalent native files and create Task, Revision, and report directories only when first needed.

3. Let Discussion explain whether the task is sequential or parallel and ask for Worker authorization. After authorization, the Claude Code adapter uses three capability levels:

   - `background_session`: when the managed Agent, `agents --json`, worktree runtime, authorized Task, and current `HEAD` are compatible, run `claude --bg --agent wishgraph-worker "执行 <task-id> 任务"`, then track the returned stable session ID with `claude agents --json --all --cwd <project>`.
   - `forked_subagent`: reserve session forking for short, low-risk checks; do not use it as the formal business Worker.
   - `manual_command_only`: output only `执行 <task-id> 任务`, then stop Discussion execution.

   The background Worker enters its isolated worktree, reads the exact Task and necessary context, then acquires the bound Claim before implementation. Returning from `claude --bg` is not enough to mark the Task `running`; a stable session ID and later Claim evidence are required. A launch failure never authorizes Discussion to modify business code.

   `claude agents` shows native background sessions. `claude logs <id>` reads recent output and `claude attach <id>` resumes interactive control. `/tasks` only shows background work associated with the current Claude session; it does not create a WishGraph Task, grant execution authority, or replace Task Specs and Claims.

   Claim release writes one idempotent pending notification to the shared Git runtime. The bound Discussion consumes it on its next activation; an explicit Discussion entry or status refresh adopts it after a host switch. This is pull-on-activation, not a real-time popup. Safe sequential and mechanically proven independent parallel results enter Discussion-local Integration automatically with a lease. Risk or conflict asks only the concrete decision; Integration never creates another window or uses a daemon, polling, IPC, or popup.

4. If the discussion session must move, ask:

   ```text
   迁移讨论窗口，把当前讨论提示词完整显示出来供我复制。
   ```
