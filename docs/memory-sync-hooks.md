# WishGraph External-Memory Hooks

WishGraph hooks make parallel worker closeout and single-writer integration enforceable without asking a script to understand product semantics.

## Why these events

```text
SessionStart -> run neutral safety checks without choosing a window role
UserPromptSubmit -> route exact entry, refresh, and Task commands
PreToolUse   -> gate supported writes/builds and unsynchronized commits
Stop         -> continue an agent that tries to finish before closeout
```

Claude Code also supports `TaskCompleted`, so its adapter runs the same checker there. The portable core does not depend on that host-specific event.

## Install into a project

The runtime requires Git and Python 3.9 or newer and has no third-party Python dependencies.

### Simplest option

If the skill is already installed, ask the agent:

```text
Use $wishgraph to enable automatic memory sync for this project in safe mode.
```

The agent selects the current host and installs non-blocking `warn` hooks without asking the user to learn installer flags.

Natural-language choices are:

```text
Install only the Skill; do not enable hooks.
Set up WishGraph safely for this project. (Recommended.)
Set up WishGraph strictly and block missing memory sync.
```

If the request is ambiguous, the agent asks only this choice and detects the host, operating system, path, Git, and Python automatically.

The agent recommends the best fit before asking, then guides four short stages: choice, prerequisites, installation, and verification. After the user accepts a mode, setup continues automatically and pauses only for a missing system dependency, permission to initialize Git, or a required restart. Each pause gives one recommended action, its rough cost, and an exact resume phrase.

For a first-time Codex installation, run this from the target project to install the skill and hooks together:

```bash
curl -fsSL https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.sh | bash -s -- codex --setup-project
```

Use `claude-user` instead of `codex` for Claude Code. After one successful closeout, add `--strict` to use `enforce` mode and request the Git pre-commit fallback.

Windows PowerShell has a native entry point:

```powershell
& ([scriptblock]::Create((irm 'https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.ps1'))) codex -SetupProject
```

Preflight runs before installation. The WishGraph Skill uses about 0.5 MB and project hooks about 0.3 MB. Missing Git commonly adds about 200-500 MB and 2-10 minutes; missing Python commonly adds about 100-300 MB and 2-10 minutes. The Apple Command Line Tools route for Git is larger, roughly 1-3 GB and 5-30 minutes. These are broad estimates.

### Custom option

From this repository:

```bash
python3 skills/wishgraph/scripts/install_project_hooks.py \
  --target /path/to/project \
  --host all \
  --mode warn
```

From a Codex user-skill installation:

```bash
python3 ~/.codex/skills/wishgraph/scripts/install_project_hooks.py \
  --target /path/to/project \
  --host codex \
  --mode warn
```

From a Claude Code user-skill installation:

```bash
python3 ~/.claude/skills/wishgraph/scripts/install_project_hooks.py \
  --target /path/to/project \
  --host claude \
  --mode warn
```

The installer creates the common runtime under `.wishgraph/` and safely merges project-level Codex or Claude Code JSON configuration. It does not replace unrelated existing hooks.

The installer writes the exact Python executable used during setup into the host commands and `.wishgraph/config.json`, avoiding later `python3` versus `py -3` path drift.

For an enabled project, the bundled installer also provides three bounded maintenance actions: `--doctor --json` performs a fixed-path read-only health check; `--upgrade --json` repairs missing metadata for current files or atomically replaces a bundled-known generated runtime and rolls back on failure; `--repair-host-adapter --host codex|claude --json` repairs only the selected current-host adapter while preserving unrelated hooks. Unknown or locally modified runtime files stop for review instead of being overwritten.

`memory_sync.py` is a stable entrypoint over four explicit boundaries: `workflow_state.py` defines Session Role, Task Lifecycle, Flow Phase, Expected Transition, events, and plans; `policy.py` implements the pure `reduce(current_state, user_event, host_capability)` transition function; `host_adapter.py` maps one authorized next action to Codex, Claude Code, CLI, and Hook behavior; `git_state.py` persists Git facts, session runtime, Worker Claims, and the Discussion-local Integration lease. Semantic project truth remains in Markdown and Git.

Start with `warn`. After one successful Task-backed Worker closeout and one Discussion-local integration, change `.wishgraph/config.json` to `enforce`.

Codex users must trust the repository and review new hook definitions with `/hooks`. Project hooks do not run in an untrusted repository.

## Parallel closeout rules

Every worker uses a separate branch or worktree and creates one new immutable report:

```text
reports/runs/<work-unit-id>.md
```

New Task Specs contain `wishgraph:task-state`, Run Reports contain `wishgraph:run-state`, and Project Status snapshots contain `wishgraph:integration-state`. Hooks check `draft -> approved -> running -> completed|blocked|incomplete -> integrated -> reviewed`, including explicit Worker-creation authority and integration policy. Drafts remain editable until approval; execution identity is then fixed except for a new retry report path. Authorization, retry, and review transitions may omit a Worker report only when surrounding task prose is unchanged; `running` is not a valid closeout. Legacy label-based files remain readable; a present but invalid block is an error.

Completed-Task corrections may use `tasks/revisions/<task-id>-rN.md` with a `wishgraph:revision-state` block. This is intentionally smaller than a Task Spec: parent Task, exact request, allowed scope, targeted validation, status, and one immutable report. A Revision report uses `change_class: revision`, the parent `task_id`, and the exact `revision_id`. Any recorded API, schema, persistence, migration, dependency, permission, security, privacy, or product-decision risk requires a formal follow-up Task.

Task Lifecycle is only one state dimension. Session Role (`neutral|discussion|worker`), Flow Phase, and one structured `expected_transition` are stored separately under the Git common directory. A short reply such as `可以` or `执行吧` is actionable only when that transition is unique.

Worker reports use `Integrate` or `N/A` and do not edit shared project memory:

```markdown
| File | Result | Reason |
|---|---|---|
| `PRD.md` | N/A | User-visible behavior did not change |
| `CODEMAP.md` | Integrate | New source anchor must enter the project map |
| `prompts/DISCUSSION_AI.md` | Integrate | Present the completed result after merge |
```

The Discussion-local Integration phase holds a bound lease, merges Worker commits with `--no-commit`, reads all new Run Reports, updates affected shared memory, rewrites `reports/PROJECT_STATUS.md` as the current snapshot, and then refreshes the concise dynamic handoff in `prompts/DISCUSSION_AI.md`. Project Status lists only reports absorbed by this integration and uses Updated or N/A rows.

Default size controls keep the snapshot usable: Project Status is limited to 160 lines and 12,000 characters, the discussion dynamic block to 30 lines, and optional compatibility-mode SessionStart context to 2,000 characters. If either Project Status limit is exceeded, `warn` reports the need to compress without blocking, while `enforce` blocks integration completion and commit. Move historical detail to Run Reports and Git history; never remove unresolved risks, conflicts, or pending decisions just to meet the limit.

Existing `paths.dev_report` settings migrate to `paths.project_status` while preserving custom path values. An old-only `reports/DEV_REPORT.md` remains readable with a migration warning. If old and new standard files both exist, WishGraph reports an ambiguous truth source and strict mode blocks integration until the project keeps one authoritative `reports/PROJECT_STATUS.md`.

Task and run-report metadata distinguish `sequential`, `parallel_batch`, and `high_risk`, while execution mode distinguishes `exclusive`, `parallel_independent`, and `competitive`. Every Worker terminal event first enters `integration_pending`. Safe sequential results and mechanically proven independent parallel batches enter Discussion-local Integration automatically under existing Worker authority. High-risk, conflicting, blocked, competitive, or mechanically ambiguous results enter a concrete `decision_required` or `blocked` state. Hooks calculate and enforce recorded gates but do not grant authority or launch Agents.

Worker creation always requires an explicit human command. Codex may then create a user-visible Worker task. Claude Code, unsupported creation, and failed creation output exactly `执行 <task-id> 任务` and stop. Hidden subagents are not Worker windows. Integration is an automatically triggered, Discussion-local, safe-when-silent phase: it never creates a user-visible window. If Discussion is inactive, persist `integration_pending` until the next Discussion entry or refresh.

New sessions are neutral. With the default `session_start_context_mode: safety_only`, hooks emit context only when they find safety or synchronization issues; they do not load the discussion prompt or activate a role. Say `Start discussion` to load Discussion state in the current visible window, or `Refresh WishGraph project state and present the latest integrated results` to refresh an active discussion. Existing installations that explicitly retain `discussion_summary` compatibility mode can still receive the old concise injection.

In a continuously running discussion window, say: `Refresh WishGraph project state and present the latest integrated results.`

Existing legacy ad-hoc reports remain readable, but new business-code work runs in a claimed Worker. Existing `.tasks/build/*.md` projects remain supported.

## Direct checks

```bash
python3 .wishgraph/hooks/memory_sync.py check --scope worktree
python3 .wishgraph/hooks/memory_sync.py check --scope staged
python3 .wishgraph/hooks/memory_sync.py status
python3 .wishgraph/hooks/memory_sync.py status --task 012
python3 .wishgraph/hooks/memory_sync.py status --full
```

The default status command emits a compact active view and resolves only current candidate report paths on visible refs. `--task` selects one exact Task; `--full` is the explicit historical scan. No mode writes a shared queue file. Discussion entry and refresh use the active view; SessionStart only includes it in opt-in compatibility mode.

It also emits `auto_integration_eligible` and one of `nothing_to_integrate`, `wait_for_worker`, `auto_integrate`, `await_user_confirmation`, `discuss_blocker`, or `compare_candidates` as `next_action`. These are internal routing fields; normal users should see only Discussion and explicit Worker windows.

The host adapter can evaluate the pure reducer through `flow-plan`, which reads `{"state": {...}, "event": {...}}` from standard input. Persist the returned `host_action.state_patch` with `session apply SESSION_ID`, also via JSON standard input. `session get` and `session set` support inspection and initial role setup. A host must not persist `waiting_for_worker` until a real visible Worker ID exists and runtime persistence succeeds.

Hosts can select a truthful silent fallback without launching anything from a Hook:

```bash
python3 .wishgraph/hooks/memory_sync.py integration-plan --host-capability background
python3 .wishgraph/hooks/memory_sync.py integration-plan --host-capability active_agent
python3 .wishgraph/hooks/memory_sync.py integration-plan --host-capability inactive
```

Both `background` and `active_agent` return `enter_discussion_local_integration`; `inactive` returns `persist_integration_pending_until_discussion_resume`. No result creates an Integration window. The command is read-only; Hooks never call `subprocess.Popen`, merge branches, or write semantic state.

The read-only task router is also available to host adapters:

```bash
python3 .wishgraph/hooks/memory_sync.py task route "执行012号任务"
python3 .wishgraph/hooks/memory_sync.py task resolve 012
python3 .wishgraph/hooks/memory_sync.py task family 012
```

It matches structured IDs exactly, reports duplicate declarations, and never executes a nearby or filename-prefix match. Task IDs follow `^\d{3,}[a-z]*$`; retries retain the ID and increment the attempt while follow-up goals allocate the next suffix.

Formal execution uses repository-wide runtime Claims stored below `git rev-parse --git-common-dir`, outside business commits:

```bash
python3 .wishgraph/hooks/memory_sync.py claim acquire 012 --worker-id worker-012 --session-id worker-012 --host codex
python3 .wishgraph/hooks/memory_sync.py claim inspect 012
python3 .wishgraph/hooks/memory_sync.py claim heartbeat CLAIM_ID
python3 .wishgraph/hooks/memory_sync.py claim release CLAIM_ID
python3 .wishgraph/hooks/memory_sync.py claim revoke CLAIM_ID
```

Acquisition uses an atomic filesystem operation, defaults to one exclusive active Claim per Task, and records attempt, worker, branch, absolute worktree, timestamps, lease status, execution mode, and optional host thread reference. With `--session-id`, Claim acquisition also persists the Worker runtime; persistence failure revokes the new Claim. Heartbeat and release enforce branch/worktree binding; explicit revoke is the takeover control path. Stale detection preserves old records. This coordinates processes and worktrees sharing one local Git common directory; it is not a distributed lock across machines that only share a remote.

A terminal Worker window may be rebound with `claim rebind`. Rebind releases the old Claim before acquiring a new Claim carrying a fresh `task_id`, optional `revision_id`, `allowed_scope`, `validation_plan`, and execution ownership. If new acquisition or runtime persistence fails, the window remains idle/unbound and old authority is not restored. A running old Task is never eligible.

Use `revision next 012` to allocate the next exact Revision ID, `revision resolve 012-r1` to inspect its lightweight record, and `revision route 012-r1 --host codex|claude` to calculate the host action. Codex returns an existing-worker target when a reusable visible Worker is recorded, otherwise a visible Revision Worker action; Claude Code returns only the shortest manual command.

Discussion-local Integration first persists `phase: integrating`, then acquires a lease bound to the session, integration ID, Task IDs, reports, branch, and worktree:

```bash
python3 .wishgraph/hooks/memory_sync.py integration-lease acquire \
  --session-id discussion-1 \
  --integration-id integration-012 \
  --task-id 012 \
  --report reports/runs/012-attempt-1.md
```

Supported native writes, recognized shell build/write commands, and MCP tools with write-like names require a live matching Worker Claim. Merge, combined validation, shared-state writes, and the integration commit require the Discussion-local Integration lease. An opaque script or MCP tool can conceal side effects, so this is a host-tool gate rather than an OS sandbox. Complete read interception remains `host capability dependent`, not a universal hard gate.

`claim revoke` returns `explicit_user_authorization_required` unless the host passes `--authorized-by-user`. Stopping or rejecting unintegrated work preserves its branch/report, then a retry keeps the Task ID and increments the attempt. Integrated history is replaced only through a new rollback or follow-up Task.

Competitive execution is planned read-only with:

```bash
python3 .wishgraph/hooks/memory_sync.py competitive-plan 012 --candidates 2
```

It proposes `012a`, `012b`, shared `comparison_group: 012`, separate Claims/worktrees/reports, and exactly one winner. Status publishes only the unique objective winner in `selected_reports`; a tie or `selection_requires_judgment` routes to `compare_candidates`. Losing candidates remain unmerged and become `rejected` or `superseded`.

Legacy `micro` Run Reports remain readable for compatibility, but no new ad-hoc micro unit is created. A clear correction uses a Task Revision; new or expanded work uses a formal Task. Neither authorizes Discussion to edit business code.

For strict `enforce` mode, add `--git-hook` so commits made outside an agent and tool paths that lifecycle hooks cannot intercept are also checked. The installer refuses to overwrite an existing Git pre-commit hook and prints chaining guidance instead.

## Boundaries

- Hooks do not generate PRD, architecture, CODEMAP, or handoff prose.
- Hooks do not stage, commit, or amend files.
- Hooks ignore their own generated runtime and host configuration.
- Hooks do not choose parallelism, start Workers, create Integration windows, merge code, or replace human review.
- A blocked or incomplete worker can stop after creating a unique Blocked or Incomplete run report with validation and impact proposals.
- Set mode to `warn` while adapting rules for a repository; do not satisfy the hook with false Updated claims.
