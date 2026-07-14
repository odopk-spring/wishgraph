# WishGraph External-Memory Hooks

WishGraph hooks make parallel worker closeout and single-writer integration enforceable without asking a script to understand product semantics.

## Why three events

```text
SessionStart -> run neutral safety checks without choosing a window role
PreToolUse   -> block an unsynchronized git commit
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

Preflight runs before installation. WishGraph uses about 0.2 MB and project hooks add less than 0.1 MB. Missing Git commonly adds about 200-500 MB and 2-10 minutes; missing Python commonly adds about 100-300 MB and 2-10 minutes. The Apple Command Line Tools route for Git is larger, roughly 1-3 GB and 5-30 minutes. These are broad estimates.

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

`memory_sync.py` is a stable entrypoint over four explicit boundaries: `git_state.py` reads Git and repository state, `workflow_state.py` parses versioned lifecycle blocks and legacy Markdown fields, `policy.py` evaluates lifecycle and closeout rules, and `host_adapter.py` handles CLI and host Hook input/output. Semantic project truth remains in Markdown and Git. Task, Run Report, and Integration blocks cover only machine workflow facts.

Start with `warn`. After one successful formal-task and ad-hoc closeout, change `.wishgraph/config.json` to `enforce`.

Codex users must trust the repository and review new hook definitions with `/hooks`. Project hooks do not run in an untrusted repository.

## Parallel closeout rules

Every worker uses a separate branch or worktree and creates one new immutable report:

```text
reports/runs/<work-unit-id>.md
```

New Task Specs contain `wishgraph:task-state`, Run Reports contain `wishgraph:run-state`, and Project Status snapshots contain `wishgraph:integration-state`. Hooks check `draft -> approved -> running -> completed|blocked|incomplete -> integrated -> reviewed`, including explicit Worker-creation authority and integration policy. Drafts remain editable until approval; execution identity is then fixed except for a new retry report path. Authorization, retry, and review transitions may omit a Worker report only when surrounding task prose is unchanged; `running` is not a valid closeout. Legacy label-based files remain readable; a present but invalid block is an error.

Worker reports use `Integrate` or `N/A` and do not edit shared project memory:

```markdown
| File | Result | Reason |
|---|---|---|
| `PRD.md` | N/A | User-visible behavior did not change |
| `CODEMAP.md` | Integrate | New source anchor must enter the project map |
| `prompts/DISCUSSION_AI.md` | Integrate | Present the completed result after merge |
```

The integration agent merges Worker commits with `--no-commit`, reads all new Run Reports, updates affected shared memory, rewrites `reports/PROJECT_STATUS.md` as the current snapshot, and then refreshes the concise dynamic handoff in `prompts/DISCUSSION_AI.md`. Project Status lists only reports absorbed by this integration and uses Updated or N/A rows.

Default size controls keep the snapshot usable: Project Status is limited to 160 lines and 12,000 characters, the discussion dynamic block to 30 lines, and optional compatibility-mode SessionStart context to 2,000 characters. If either Project Status limit is exceeded, `warn` reports the need to compress without blocking, while `enforce` blocks integration completion and commit. Move historical detail to Run Reports and Git history; never remove unresolved risks, conflicts, or pending decisions just to meet the limit.

Existing `paths.dev_report` settings migrate to `paths.project_status` while preserving custom path values. An old-only `reports/DEV_REPORT.md` remains readable with a migration warning. If old and new standard files both exist, WishGraph reports an ambiguous truth source and strict mode blocks integration until the project keeps one authoritative `reports/PROJECT_STATUS.md`.

Task and run-report metadata distinguish `sequential`, `parallel_batch`, and `high_risk`, while execution mode distinguishes `exclusive`, `parallel_independent`, and `competitive`. Safe sequential results and mechanically proven independent parallel batches are eligible for silent integration under existing Worker authority. High-risk, conflicting, blocked, competitive, or mechanically ambiguous results return to Discussion. Hooks calculate and enforce recorded gates but do not grant authority or launch an Integrator.

Worker creation always requires an explicit human command. The discussion Agent may then create user-visible Worker tasks through a supported host capability; Hooks never do so. Hidden subagents are not Worker windows, and manual copying is the fallback when visible task creation is unavailable. Integration is an invisible temporary control role: use a real background task when available, fall back to an isolated phase in the active Agent, or leave derived work pending until the next Discussion entry/refresh. Never require a user-visible Integration window or claim unsupported background execution.

New sessions are neutral. With the default `session_start_context_mode: safety_only`, hooks emit context only when they find safety or synchronization issues; they do not load the discussion prompt or activate a role. Say `Start discussion` to load Discussion state in the current visible window, or `Refresh WishGraph project state and present the latest integrated results` to refresh an active discussion. Existing installations that explicitly retain `discussion_summary` compatibility mode can still receive the old concise injection.

In a continuously running discussion window, say: `Refresh WishGraph project state and present the latest integrated results.`

An ad-hoc edit may omit `tasks/build/*.md`; it still needs validation, a unique run-report ID, and the normal commit boundary. Existing `.tasks/build/*.md` projects remain supported.

## Direct checks

```bash
python3 .wishgraph/hooks/memory_sync.py check --scope worktree
python3 .wishgraph/hooks/memory_sync.py check --scope staged
python3 .wishgraph/hooks/memory_sync.py status
```

The status command emits machine-readable pending integration, integration kind, ready reports, waiting reports, blocked reports, confirmation requirement, and reason. It scans immutable reports on visible Git refs without writing a shared queue file. Discussion entry and explicit refresh read this status; SessionStart only includes it in opt-in compatibility mode.

It also emits `auto_integration_eligible` and one of `nothing_to_integrate`, `wait_for_worker`, `auto_integrate`, `await_user_confirmation`, `discuss_blocker`, or `compare_candidates` as `next_action`. These are internal routing fields; normal users should see only Discussion and Execution.

Hosts can select a truthful silent fallback without launching anything from a Hook:

```bash
python3 .wishgraph/hooks/memory_sync.py integration-plan --host-capability background
python3 .wishgraph/hooks/memory_sync.py integration-plan --host-capability active_agent
python3 .wishgraph/hooks/memory_sync.py integration-plan --host-capability inactive
```

The returned action is respectively: launch a temporary background Integrator through a real host capability, enter an isolated Integration phase in the active Agent, or keep derived pending state until the next explicit Discussion entry/refresh. The command is read-only; Hooks never call `subprocess.Popen`, merge branches, or write semantic state.

The read-only task router is also available to host adapters:

```bash
python3 .wishgraph/hooks/memory_sync.py task route "执行012号任务"
python3 .wishgraph/hooks/memory_sync.py task resolve 012
python3 .wishgraph/hooks/memory_sync.py task family 012
```

It matches structured IDs exactly, reports duplicate declarations, and never executes a nearby or filename-prefix match. Task IDs follow `^\d{3,}[a-z]*$`; retries retain the ID and increment the attempt while follow-up goals allocate the next suffix.

Formal execution uses repository-wide runtime Claims stored below `git rev-parse --git-common-dir`, outside business commits:

```bash
python3 .wishgraph/hooks/memory_sync.py claim acquire 012 --worker-id worker-012
python3 .wishgraph/hooks/memory_sync.py claim inspect 012
python3 .wishgraph/hooks/memory_sync.py claim heartbeat CLAIM_ID
python3 .wishgraph/hooks/memory_sync.py claim release CLAIM_ID
python3 .wishgraph/hooks/memory_sync.py claim revoke CLAIM_ID
```

Acquisition uses an atomic filesystem operation, defaults to one exclusive active Claim per Task, and records attempt, worker, branch, absolute worktree, timestamps, lease status, execution mode, and optional host thread reference. Heartbeat and release enforce branch/worktree binding; explicit revoke is the takeover control path. Stale detection preserves old records. This coordinates processes and worktrees sharing one local Git common directory; it is not a distributed lock across machines that only share a remote.

`claim revoke` returns `explicit_user_authorization_required` unless the host passes `--authorized-by-user`. Stopping or rejecting unintegrated work preserves its branch/report, then a retry keeps the Task ID and increments the attempt. Integrated history is replaced only through a new rollback or follow-up Task.

Competitive execution is planned read-only with:

```bash
python3 .wishgraph/hooks/memory_sync.py competitive-plan 012 --candidates 2
```

It proposes `012a`, `012b`, shared `comparison_group: 012`, separate Claims/worktrees/reports, and exactly one winner. Status publishes only the unique objective winner in `selected_reports`; a tie or `selection_requires_judgment` routes to `compare_candidates`. Losing candidates remain unmerged and become `rejected` or `superseded`.

A `micro` Run Report is an independent ad-hoc unit, never a shortcut inside a formal Task. It must list changed paths and explicit false API/schema/security/dependency flags, plus the normal validation, immutable report, commit, rollback, and Integrate/N/A evidence. Any risk promotes the request to a formal Task and makes the micro report ineligible.

For strict `enforce` mode, add `--git-hook` so commits made outside an agent and tool paths that lifecycle hooks cannot intercept are also checked. The installer refuses to overwrite an existing Git pre-commit hook and prints chaining guidance instead.

## Boundaries

- Hooks do not generate PRD, architecture, CODEMAP, or handoff prose.
- Hooks do not stage, commit, or amend files.
- Hooks ignore their own generated runtime and host configuration.
- Hooks do not choose parallelism, start workers or integration agents, merge code, or replace human review.
- A blocked or incomplete worker can stop after creating a unique Blocked or Incomplete run report with validation and impact proposals.
- Set mode to `warn` while adapting rules for a repository; do not satisfy the hook with false Updated claims.
