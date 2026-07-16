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

After the project is explicitly enabled, keep the user-facing loop simple: reopen the session, say `Start discussion`, and use `Execute task 012` for one exact Task. The generic adapter itself cannot create a native Worker; unless the host supplies an equivalent inspectable thread integration, it falls back to the one-line execution command.

For bilingual Chinese and English handoff, add:

```text
Use bilingual Chinese and English for user-facing prompts and summaries. Keep file paths, commands, and code identifiers unchanged.
```

## Project state without file sprawl

Reuse existing product, architecture, code-map, conventions, Task, and test files when they already own the same truth. Create only the missing entry state and create Task, Revision, and Run Report directories when first needed. The standard paths are defaults, not a requirement to duplicate good project documentation:

```text
PRD.md
ARCHITECTURE.md
CODEMAP.md
CONVENTIONS.md
prompts/DISCUSSION_AI.md
prompts/EXECUTION_AI.md
tasks/build/*.md
reports/PROJECT_STATUS.md
reports/RUN_REPORT.md
reports/runs/<work-unit-id>.md
```

A new window in the same project continues with `Start discussion`; an active Discussion uses `Refresh project status`. Do not copy a full prompt or previous chat as the normal handoff.

## Tool-Agnostic Rule

Do not depend on a specific chat product for durable project truth. Any agent that can read and write the files can participate in the protocol, but that does not mean every host provides equivalent safety or automation. This adapter alone supplies no native Worker creation, lifecycle Hook registration, write/build interception, or completion notification.

When the WishGraph hook runtime is installed, generic agents can run the deterministic checks directly:

```bash
python3 .wishgraph/hooks/memory_sync.py check --scope worktree
python3 .wishgraph/hooks/memory_sync.py check --scope staged
```

These commands verify closeout state; they are not a substitute for a host `PreToolUse` integration and should not be described as a hard write/build gate.

See [`docs/memory-sync-hooks.md`](../../docs/memory-sync-hooks.md) for installation and optional Git pre-commit enforcement.
