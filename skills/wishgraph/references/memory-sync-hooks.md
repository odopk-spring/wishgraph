# External-Memory Sync Hooks

Use this reference when a user wants WishGraph to enforce external-memory closeout, keep `prompts/DISCUSSION_AI.md` current after Worker execution, or install Codex / Claude Code project hooks.

## Principle

Hooks enforce Worker and Discussion-local Integration boundaries and expose read-only orchestration status; they do not write semantic project memory. Workers create immutable task-scoped reports. Discussion temporarily acquires the single-writer Integration lease to merge, apply shared-memory updates, rewrite Project Status, and refresh the discussion handoff.

The project-local hook runtime uses three events:

1. `SessionStart`: run neutral safety checks. The default `safety_only` mode warns about pending or invalid state without activating Discussion or injecting its full context.
2. `PreToolUse`: gate business writes, build/test commands, dependency installation, integration operations, and commits against the current Session Role, Worker Claim, or Integration lease; also deny commits when closeout is incomplete.
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
.wishgraph/hooks/git_state.py
.wishgraph/hooks/workflow_state.py
.wishgraph/hooks/policy.py
.wishgraph/hooks/host_adapter.py
.codex/hooks.json        # when Codex is selected
.claude/settings.json    # when Claude Code is selected
```

The installer merges JSON hook groups and preserves unrelated existing hooks. It refuses to replace a modified generated runtime unless `--force-assets` is supplied.

New projects use the visible `tasks/build/*.md` path. The runtime also scans legacy `.tasks/build/*.md`, and installer upgrades preserve an existing project's configured primary task path instead of moving its files automatically.

New projects use `reports/PROJECT_STATUS.md` as the current integrated snapshot. Existing `paths.dev_report` configuration is migrated to `paths.project_status` without changing a custom path value. A project that only has `reports/DEV_REPORT.md` remains readable with a migration warning; if both standard files exist, the hook reports an ambiguous source of truth and strict mode blocks integration until one authoritative file remains.

The default snapshot limits are 160 lines and 12,000 characters. The discussion prompt's dynamic state block is limited to 30 lines, and SessionStart context is capped at 2,000 characters. Exceeding either Project Status limit means the Discussion-local Integration phase must rewrite it more concisely: move historical detail to immutable Run Reports and Git history, but retain every unresolved risk, conflict, and pending decision. `warn` mode reports the issue without blocking completion; `enforce` mode blocks integration completion and commit boundaries.

For Codex, the user must trust the repository and review new or changed hooks with `/hooks` before they run.

## Parallel Closeout Contract

Each Worker uses a separate branch or worktree and creates exactly one new `reports/runs/<task-id>-attempt-N.md`. Run reports are immutable after entering Git history. Existing legacy ad-hoc reports remain readable, but new business-code execution is Task-backed.

New Task Specs embed `wishgraph:task-state`, Run Reports embed `wishgraph:run-state`, and Project Status embeds `wishgraph:integration-state`. Together they form the checked lifecycle `draft -> approved -> running -> completed|blocked|incomplete -> integrated -> reviewed`. The runtime prefers a valid structured block and falls back to legacy labels when no block exists. A present but invalid block is an error rather than a silent fallback.

Low-risk corrections after completion use `tasks/revisions/<task-id>-rN.md` with `wishgraph:revision-state`, not a copied full Task Spec. The record binds one parent Task, exact request, allowed scope, validation plan, status, and immutable report. A terminal Worker window may be reused only through a rebind that releases the old Claim, clears old scope/validation, acquires a fresh Claim, and persists the new binding. Unsupported host routing outputs only `在任务 <task-id> 的执行窗口执行修订 <revision-id>`.

Task Lifecycle is only one of four orthogonal state dimensions. Git-common-dir runtime state also records `Session Role` (`neutral|discussion|worker`), `Flow Phase`, and one structured `expected_transition`. The pure policy reducer selects the unique next action; host adapters only decide how to realize it.

Discussion may refine a `draft` task before authorization. It sets `worker_creation_authorized: true` only after an explicit human creation command; execution identity becomes immutable at approval except that a blocked or incomplete retry must receive a new Run Report path. Workers move authorized tasks through running and closeout states. Integration moves absorbed tasks to integrated. Discussion records reviewed only after human acceptance. Authorization, retry, and review transitions may omit a Worker report only when surrounding task prose is unchanged; `running` never counts as a completed closeout.

Workers are explicit, user-visible tasks created only after a human creation command. Discussion may create and configure them through a supported host capability; Hooks never start them. Codex uses a visible Worker task. Claude Code, unsupported creation, and failed creation output exactly `执行 <task-id> 任务` and stop. Each task and report records `Work type`, `Batch ID`, and `Integration authorization`. Completed reports also record integration readiness, scope check, conflict status, material new decisions, and machine-readable validation results.

Worker reports use the exact shared-memory rows from `reports/RUN_REPORT.md`:

- Use `Integrate` when the Discussion-local Integration phase should update shared memory.
- Use `N/A` with a concrete reason when no shared update is needed.
- Do not let Workers edit PRD, architecture, CODEMAP, conventions, prompts, or `reports/PROJECT_STATUS.md`.

The Discussion-local Integration phase merges Worker commits with `--no-commit` or an equivalent no-commit cherry-pick while holding a bound Integration lease. It reads every new Run Report, updates affected shared memory, rewrites `reports/PROJECT_STATUS.md` as the current snapshot with only this integration's absorbed report paths, and then refreshes the concise dynamic state block in `prompts/DISCUSSION_AI.md`. Project Status uses Updated or N/A rows and records integration kind and authorization.

Every Worker terminal event first creates `integration_pending`. Safe sequential work and mechanically proven `parallel_independent` batches inherit integration authority from explicit Worker approval and enter Integration automatically. High-risk, conflicting, blocked, competitive, or ambiguous work enters `decision_required` or `blocked`; ask only the concrete product, compatibility, conflict, or recovery question. Hooks calculate this distinction but never grant authority or launch an agent.

Host adapters can evaluate one pure transition with `flow-plan`; the command reads `{"state": {...}, "event": {...}}` from standard input. Apply the returned `host_action.state_patch` atomically with:

```bash
python3 .wishgraph/hooks/memory_sync.py session apply SESSION_ID
```

Pass only the JSON state patch on standard input. `session get` and `session set` provide read/bootstrap operations. Do not persist `waiting_for_worker` until a real visible Worker thread exists and its runtime write succeeds.

## Integration Status

Use the read-only status command from the project root:

```bash
python3 .wishgraph/hooks/memory_sync.py status
```

It scans task specs, the current target branch, and immutable run reports visible on local or remote Git refs. It emits:

```json
{
  "schema_version": 1,
  "kind": "integration_status",
  "pending_integration": true,
  "integration_kind": "parallel_batch",
  "ready_reports": [],
  "waiting_reports": [],
  "blocked_reports": [],
  "work_units": [
    {
      "task_id": "012",
      "lifecycle_status": "completed",
      "worker_creation_authorized": true,
      "integration_policy": "inherited_task_approval"
    }
  ],
  "requires_user_confirmation": true,
  "auto_integration_eligible": false,
  "next_action": "await_user_confirmation",
  "reason": ""
}
```

Explicit Discussion entry or project-state refresh reads the same status. Optional `discussion_summary` compatibility mode may also inject it at SessionStart. Discussion AI combines it with platform thread status when available, presents completed, waiting, and blocked workers, and recommends the next action. The status is evidence, not a semantic review or an instruction to merge.

Treat Integration as an automatically triggered, Discussion-local, safe-when-silent phase. Never launch an Integrator or create a user-visible Integration window. If Discussion is active, evaluate and enter the local phase immediately; otherwise persist `integration_pending` until the next explicit Discussion entry or refresh.

The required mechanical boundary is `write/build gate: required`: business writes and implementation build/test commands require a Worker Claim bound to the current Task, branch, worktree, and session. Merge, combined validation, shared-state writes, and the integration commit require a Discussion-local Integration lease. Source-read enforcement remains `read gate: host capability dependent`; when a host cannot intercept all read tools, describe that limit honestly instead of calling it a hard gate.

New windows remain neutral until the user explicitly says "Start discussion" or an equivalent phrase. Use explicit refresh in a continuously active discussion. Do not rely on SessionStart to select or activate a role.

Run the checker directly when debugging:

```bash
python3 .wishgraph/hooks/memory_sync.py check --scope worktree
python3 .wishgraph/hooks/memory_sync.py check --scope staged
python3 .wishgraph/hooks/memory_sync.py status
```

## Failure and Pause Handling

If worker execution cannot complete, create a Blocked or Incomplete run report with validation and impact proposals. Return it to discussion for user judgment; do not auto-integrate it.

If a hook rule is incorrect for the repository, switch the project to `warn` while adjusting `.wishgraph/config.json`. Do not bypass enforcement by fabricating Updated entries or empty N/A reasons.
