# Generic Agent Adapter

Use this adapter for tools that do not support Codex or Claude Code skills directly.

The core idea is simple: put the WishGraph workflow in the instruction file your agent already loads, then let the agent create the same project memory files.

## Install Into A Project

Copy `AGENTS.md` into the target project root:

```bash
cp adapters/generic/AGENTS.md /path/to/project/AGENTS.md
```

If your tool uses another always-loaded instruction file, copy the same content there instead.

Common examples:

- `AGENTS.md`
- `CLAUDE.md`
- project rules file supported by your editor or agent tool
- a pinned system/developer prompt in the agent workspace

Then start the agent with:

```text
Follow AGENTS.md. Start WishGraph for this project. If there is no PRD, run the WishGraph intake prompt and grill it into a PRD before writing code.
```

For bilingual Chinese and English handoff, add:

```text
Use bilingual Chinese and English for user-facing prompts and summaries. Keep file paths, commands, and code identifiers unchanged.
```

## Expected Output

The agent should create or update:

```text
PRD.md
ARCHITECTURE.md
CODEMAP.md
CONVENTIONS.md
prompts/DISCUSSION_AI.md
prompts/EXECUTION_AI.md
.tasks/build/*.md
reports/DEV_REPORT.md
reports/RUN_REPORT.md
reports/runs/<work-unit-id>.md
```

## Tool-Agnostic Rule

Do not depend on a specific chat product. The durable protocol is the file set above. Any agent that can read and write files can participate if it follows the planning/execution split.

When the WishGraph hook runtime is installed, generic agents can run the deterministic checks directly:

```bash
python3 .wishgraph/hooks/memory_sync.py check --scope worktree
python3 .wishgraph/hooks/memory_sync.py check --scope staged
```

See [`docs/memory-sync-hooks.md`](../../docs/memory-sync-hooks.md) for installation and optional Git pre-commit enforcement.
