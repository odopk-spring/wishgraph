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

This safely merges `SessionStart`, `PreToolUse`, `Stop`, and `TaskCompleted` groups into `.claude/settings.json`. Switch `.wishgraph/config.json` to `enforce` after a successful closeout. See [`docs/memory-sync-hooks.md`](../../docs/memory-sync-hooks.md).

## Recommended Claude Code Flow

1. Start a discussion session:

   ```text
   /wishgraph start this project. If there is no PRD, run the WishGraph intake prompt and grill one decision at a time.
   ```

   For bilingual output, append: `Use bilingual Chinese and English for user-facing prompts and summaries.`

2. Let WishGraph create or update:

   ```text
   PRD.md
   ARCHITECTURE.md
   CODEMAP.md
   CONVENTIONS.md
   prompts/DISCUSSION_AI.md
   prompts/EXECUTION_AI.md
   prompts/INTEGRATION_AI.md
   tasks/build/*.md
   reports/RUN_REPORT.md
   reports/PROJECT_STATUS.md
   ```

3. Let discussion AI explain whether the task is sequential or parallel and ask whether to create the execution session. After an explicit human command, it should create and configure one user-visible Worker per authorized spec when the host supports that capability, including the execution prompt, approved task file, and canonical `<task-id> · <short title> · WG Worker` name. It must not create Workers silently or use hidden subagents. Manual copying is the fallback when visible session creation is unavailable.

   An explicitly approved `micro` ad-hoc edit may omit the task file only when every risk flag is false; it still creates a unique immutable run report. Safe sequential and mechanically proven independent parallel results integrate silently. The host uses real background capability, an internal active-Agent phase, or pending-until-refresh fallback.

4. If the discussion session must move, ask:

   ```text
   迁移讨论窗口，把当前讨论提示词完整显示出来供我复制。
   ```
