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
/wishgraph start this project from my rough idea
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

Use `CLAUDE.md` for always-loaded project rules. Keep large task procedures in the `/wishgraph` skill and in WishGraph project files such as `PRD.md`, `CODEMAP.md`, `.tasks/build/*.md`, and `reports/DEV_REPORT.md`.

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
   .tasks/build/*.md
   reports/DEV_REPORT.md
   ```

3. Open a fresh execution session and paste the execution prompt plus the approved task file, or invoke `/wishgraph` again and ask it to follow the assigned task exactly.

4. If the discussion session must move, ask:

   ```text
   迁移讨论窗口，把当前讨论提示词完整显示出来供我复制。
   ```
