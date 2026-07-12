# External-Memory Sync Hooks

Use this reference when a user wants WishGraph to enforce external-memory closeout, keep `prompts/DISCUSSION_AI.md` current after ad-hoc edits, or install Codex / Claude Code project hooks.

## Principle

Hooks enforce worker and integration boundaries and expose read-only integration status; they do not write semantic project memory. Workers create immutable task-scoped reports. A temporary single-writer integration agent applies shared-memory updates and refreshes the project overview and discussion handoff.

The project-local hook runtime uses three events:

1. `SessionStart`: warn about pending changes and inject a concise latest-integration summary plus discussion handoff into new or resumed sessions.
2. `PreToolUse`: inspect staged changes before an agent runs `git commit` and deny the commit when closeout is incomplete.
3. `Stop`: inspect the worktree before the agent finishes and continue the agent when closeout is incomplete.

Claude Code may also run the same check on `TaskCompleted`. Do not make that event part of the portable core because other hosts may not expose it.

## Install

The runtime requires Git and Python 3.9 or newer, and uses only the Python standard library.

When the user asks for automatic or one-click memory sync, do not expose the full option matrix. Select the current host and run:

```bash
python3 scripts/install_project_hooks.py --target /path/to/project --host CURRENT_HOST --mode warn
```

Use `codex` or `claude` for `CURRENT_HOST`. Use `enforce --git-hook` only when the user explicitly asks for strict mode or has already completed a successful closeout in `warn` mode.

Run the installer from the installed skill directory or this repository:

```bash
python3 skills/wishgraph/scripts/install_project_hooks.py \
  --target /path/to/project \
  --host all \
  --mode warn
```

Host values are `codex`, `claude`, or `all`. Modes are:

- `off`: runtime present, enforcement disabled.
- `warn`: report missing synchronization without blocking.
- `enforce`: block unsynchronized commit and stop boundaries.

Use `warn` for the first adoption pass. Change `.wishgraph/config.json` to `enforce` after the project templates have been adapted and a full closeout succeeds.

For strict `enforce` mode, add `--git-hook` so commits outside the agent and tool paths that lifecycle hooks cannot intercept are also checked. The installer never replaces an existing Git pre-commit hook; it prints manual chaining instructions instead.

## Installed Files

```text
.wishgraph/config.json
.wishgraph/hooks/memory_sync.py
.codex/hooks.json        # when Codex is selected
.claude/settings.json    # when Claude Code is selected
```

The installer merges JSON hook groups and preserves unrelated existing hooks. It refuses to replace a modified generated runtime unless `--force-assets` is supplied.

For Codex, the user must trust the repository and review new or changed hooks with `/hooks` before they run.

## Parallel Closeout Contract

Each worker uses a separate branch or worktree and creates exactly one new `reports/runs/<work-unit-id>.md`. Run reports are immutable after entering Git history. A formal task uses its task ID; ad-hoc work uses a unique timestamped ID.

Workers are explicit, user-visible tasks created only after a human creation command. The discussion agent may create and configure them through a supported host capability; Hooks never start them. Each task and report records `Work type`, `Batch ID`, and `Integration authorization`. Completed reports also record integration readiness, scope check, conflict status, material new decisions, and machine-readable validation results.

Worker reports use the exact shared-memory rows from `reports/RUN_REPORT.md`:

- Use `Integrate` when the integration agent should update shared memory.
- Use `N/A` with a concrete reason when no shared update is needed.
- Do not let workers edit PRD, architecture, CODEMAP, conventions, prompts, or `reports/DEV_REPORT.md`.

The integration agent merges worker commits with `--no-commit` or an equivalent no-commit cherry-pick. It reads every new run report, updates affected shared memory, lists absorbed report paths in `reports/DEV_REPORT.md`, and updates the dynamic state block in `prompts/DISCUSSION_AI.md`. The overview uses Updated or N/A rows and records integration kind and authorization.

Safe sequential work inherits integration authority from task approval. Parallel batches and high-risk work require explicit user confirmation naming the reports. Hooks enforce this distinction but never grant authority themselves.

## Integration Status

Use the read-only status command from the project root:

```bash
python3 .wishgraph/hooks/memory_sync.py status
```

It scans task specs, the current target branch, and immutable run reports visible on local or remote Git refs. It emits:

```json
{
  "pending_integration": true,
  "integration_kind": "parallel_batch",
  "ready_reports": [],
  "waiting_reports": [],
  "blocked_reports": [],
  "requires_user_confirmation": true,
  "reason": ""
}
```

SessionStart may inject the same status. Discussion AI combines it with platform thread status when available, presents completed, waiting, and blocked workers, and recommends the next action. The status is evidence, not a semantic review or an instruction to merge.

Treat integration as an event-triggered temporary agent. If the platform exposes an authorized background-task or independent-thread capability, discussion AI may launch it after the applicable authority exists and must report Waiting, Running, Blocked, or Completed before it ends. If unsupported, switch the current main agent explicitly or give one user-launch command. Never claim background work that the platform cannot perform.

SessionStart context injection presents results automatically on supported start, resume, clear, or compact events. It is not a real-time push into a discussion window that remains continuously active; use an explicit refresh in that case.

Run the checker directly when debugging:

```bash
python3 .wishgraph/hooks/memory_sync.py check --scope worktree
python3 .wishgraph/hooks/memory_sync.py check --scope staged
python3 .wishgraph/hooks/memory_sync.py status
```

## Failure and Pause Handling

If worker execution cannot complete, create a Blocked or Incomplete run report with validation and impact proposals. Return it to discussion for user judgment; do not auto-integrate it.

If a hook rule is incorrect for the repository, switch the project to `warn` while adjusting `.wishgraph/config.json`. Do not bypass enforcement by fabricating Updated entries or empty N/A reasons.
