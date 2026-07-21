# Worker Execution And Claim Lifecycle

Use this reference for Formal Worker launch, host fallback, preflight, Claim/worktree binding, closeout, stop/retry/takeover, or Worker-thread reuse. Ordinary Revision work uses `task-revisions.md` instead; return here only for Worker recovery or abnormal rebind.

## Contents

- Fast path
- Authority and visible routing
- Host fallback
- Entry preflight
- Claim contract
- Execution rules
- Closeout
- Stop and recovery
- Worker rebind
- Locality boundary

## Fast Path

For one authorized, low-risk Task, read this section, `Authority And Visible Routing`, `Entry
Preflight`, `Execution Gates`, and `Closeout`. Do not read Host Fallback, Stop/Retry/Takeover,
Worker Rebind, or Locality Boundary unless that event actually occurs.

The normal Worker reads only its exact Task, declared dependencies needed for preflight, the
stable execution prompt, and files explicitly named by its scope. A successful launch is reported
to the user as `<task-id> 已交给独立 Worker 执行。`; internal IDs and capability details stay in
runtime evidence. A safe closeout returns the compact changed/validation/risk result through
Discussion after automatic integration.

## Authority And Visible Routing

Discussion records one exact `approve_worker_launch(<task-id>)`. A unique contextual affirmative reply may authorize that transition; two eligible Tasks require an exact choice. Accept ordinary confirmations such as `行，就按推荐执行吧` or `Sounds good, go ahead`, but never treat a question, negation, condition, scope change, or competing Task reference as approval. Explicit `执行 <task-id> 任务` commands take priority but still require the structured Task, dependency, branch, worktree, and scope checks; Claim checks are mandatory only in `enforce`.

Execution profile is optional. Users may write `执行 012b terra 极高`, `execute 012b sonnet high`, or answer the pending authorization with `批准，用 sonnet 高`. Parse profile aliases only after an exact Task command or while one authorization transition is pending. A plain approval uses the current Task's grounded `worker_execution_profiles` recommendation; if that host has no recommendation, keep its actual current default. A valid current-host choice overrides matching recommended fields; an unknown suffix is not an execution command, and a model belonging to another host is not translated. Profile selection never grants authority or relaxes Task scope, validation, or the gates enabled by the selected mode.

Persist authority by moving the exact Task from `draft` to `approved` and setting `worker_creation_authorized: true`. Then enter `routing_worker`.

Create only a separate user-visible and inspectable Worker thread or window. It requires an exact approved Task, independent context, bounded scope and validation, user-visible activity, and structured terminal evidence. In `enforce`, also require stable identity, Claim/branch/worktree binding, and write/build gates. Never substitute a hidden subagent or let Discussion implement the Task. Use the title:

```text
<task-id> · <short title> · WG Worker
```

Give the Worker the repository, exact durable record, branch/worktree requirement, validation, immutable Run Report path, and shared-state restriction. Include the Claim protocol only when available or required by `enforce`. Stable Worker rules come from the installed Skill and Host Adapter rather than a project prompt file.

After real creation, store the returned thread/window reference when runtime automation is available, enter `waiting_for_worker`, and stop Discussion execution actions. If runtime persistence fails, revoke any acquired Claim or record launch failure. In `warn`, continue the exact handoff through the visible Worker without retrying setup; never report an intended Worker as running.

Classify Agent containers before giving them authority:

| Kind | Allowed use | Claim and business writes |
| --- | --- | --- |
| Formal Worker | One authorized Task or Revision in an inspectable, controllable thread/window | Exact preflight is required; `enforce` also requires Claim acquisition |
| Helper Subagent | Exploration, retrieval, logs, review, or bounded validation assistance | No Worker Claim; read-only by default |
| Hidden/Internal Agent | Host-internal work without an independently inspectable thread | Never a Worker; no Claim or business writes |

Agent identity does not authorize execution. Built-in Codex `explorer`, reviewer-style Agents, Claude Explore/Plan Agents, `/fork`, and hidden subagents remain Helpers unless the host container independently satisfies every Formal Worker condition and exact Task authorization. `enforce` also requires the Claim path. A Formal Worker must not create another Formal Worker.

## Host Fallback

### Codex

Use the project-scoped `.codex/agents/wishgraph-worker.toml` custom Agent in a user-visible and inspectable Agent thread. The App surfaces subagent threads, CLI provides `/agent`, and supported IDE views expose background Agent activity. Hooks never spawn the Agent.

After authorization, use the Host Adapter when available. In `warn`, if Hook routing or registration is unavailable, Discussion may start the managed user-visible `wishgraph-worker` directly with the exact Task, scope, validation, and report path. In `enforce`, keep the existing prepare, real-ID registration, Claim, and structured observation contract.

If creation or registration fails, enter `waiting_for_user_launch` and give a host-neutral handoff instead of assuming which terminal the user will open next:

```text
cd "<project-root>"
# start either claude or codex with the displayed model and effort flags
执行 <task-id>
```

### Claude Code

Detect one host-only capability tier without changing the reducer or authority:

| Tier | Formal Worker behavior |
| --- | --- |
| `background_session` | After authorization, run the managed Claude background Agent in a unique Worktree and persist the returned Claude session ID. |
| `forked_subagent` | Use only as a Helper for short, low-risk checks with no durable ownership; formal business work still uses the manual command. |
| `manual_command_only` | Give the same host-neutral `cd` + chosen-Agent + `执行 <task-id>` handoff and stop Discussion execution. |

Require the managed `wishgraph-worker` Agent definition before background launch. Claude Code silently falls back to a default template when an Agent name is missing, so an absent or unrecognized definition is a launch failure, not permission to use the default Agent.

In `enforce`, the background Worker acquires its own Claim after Claude has placed it in its actual branch/worktree. Require the Task content fingerprint and base commit recorded by the authorized Run to match the current baseline. The Host Adapter adds a unique `--worktree` name and passes the minimal `baseRef: head` plus `.wishgraph` symlink contract through per-launch `--settings`; it does not overwrite global or project Claude settings and does not require a project `.claude/settings.json`. This needs local Git history, not GitHub or a remote. Persist the stable session ID and actual branch/worktree before strict `waiting_for_worker`; otherwise use the host-neutral handoff. In `warn`, the exact approved Task may proceed in the visible Worker even when Claim automation is unavailable.

Refresh with `claude agents --json --all --cwd <project>`. In `enforce`, structured host state plus the durable Task, Run Report, result commit, and released Claim enter `integration_pending`; conversation text is never completion evidence. In `warn`, incomplete runtime observation stays advisory and Discussion uses the visible Worker report and result commit. For the current CLI, open `claude agents --cwd <project>` for inspection/control and use `claude --resume <full-session-id>` only when conversation recovery is appropriate.

`/tasks` displays background work associated with the current Claude session. It does not create a WishGraph Task, authorize a Worker, acquire a Claim, or replace the project Task record. `/fork`, Explore, Plan, ordinary background subagents, and hidden agents are Helpers unless they expose a stable independent session, inspect/control surface, exact binding, gates, and structured terminal evidence. They are never the default Formal Worker implementation and cannot bypass scope, validation, report, or Claim gates.

### Unknown Hosts

Require a new user-opened inspectable window. Output the same bounded cross-host startup handoff and stop. Do not print the full Task Spec and do not offer direct implementation.

### Neutral Direct-Worker Entry

An ordinary neutral window receiving an exact `执行 <task-id> 任务` command becomes the Worker container for that Task. It does not create a second background Worker. In `warn`, the exact approved Task may authorize execution when Run or Claim automation is unavailable. In `enforce`, it must create the authorized Run and acquire the Claim before writes or builds. A Discussion receiving the same command keeps its Discussion role and routes an independent Worker.

A Worker container reads the exact Task or Revision and performs preflight. In `enforce`, native registration or exact current-window authorization plus Claim acquisition remains required. In `warn`, an unavailable host runtime does not invalidate the user's explicit Task approval.

## Entry Preflight

Before implementation:

1. Verify one local `HEAD` commit exists for the worktree baseline. A remote is optional; a repository with no first commit must establish its intended local baseline before Formal Worker launch.
2. Read `CONVENTIONS.md` when present and relevant, then the exact Task or Revision record.
3. Verify structured ID, authorized Run, dependencies, attempt, report path, allowed scope, and validation plan.
4. Verify the intended branch and absolute worktree.
5. Inspect active and stale Claims when runtime automation is available.
6. In `enforce`, atomically acquire and persist the exact Claim before moving the Run to `running`; in `warn`, continue from the approved Task if this automation is unavailable.

Do not infer permission from a window title, chat history, branch name, or unstructured task prose.

## Claim Contract

Bind every Claim to:

```text
task_id
revision_id             # optional
work_unit_id
attempt
worker/session identity
host thread reference   # when available
branch
absolute worktree
allowed_scope
validation_plan
execution_ownership
lease status and heartbeat
```

Store Claims under the repository's Git common directory so sibling worktrees share the lock without committing runtime files.

Use `exclusive` for ordinary Tasks. Allow only one active exclusive Claim for a Task. Use `competitive` only after the user chooses candidate execution, and require a distinct worktree for each candidate.

Heartbeat during long work when a Claim exists. Stop after a real branch or worktree mismatch. Treat expired heartbeats as preserved evidence, but do not let them lock a replacement Worker.

## Execution Gates

In `enforce`, require the bound active Claim for:

- Business-file writes.
- Implementation builds and tests.
- Dependency installation.
- The Worker's bounded commits.
- Creation of its immutable Run Report. The Worker does not rewrite the formal Task merely to mirror transient progress.

In `warn`, the approved Task supplies the same scope and validation boundaries without mechanical denial. Escalate when the implementation needs a public API, schema, persistence, migration, dependency, security, privacy, or product decision not present in the durable record.

Allow Workers to read shared memory but not rewrite it. Record proposed updates as `Integrate` or concrete `N/A` rows in the Run Report.

## Closeout

For every execution unit:

1. Run prescribed build, test, lint, manual, and WishGraph checks.
2. Create exactly one new immutable `reports/runs/<work-unit>-attempt-N.md`.
3. Record files changed, behavior, validation evidence, scope check, conflicts, material decisions, risks, and shared-memory impact.
4. Create one or more bounded linear commits unless the user explicitly forbids commits. The result must descend from the Run baseline without merge commits and contain the Run Report at the allocated repository-relative path.
5. Release an acquired Claim only after the runtime can read that exact report from `result_commit:report_path`. In `warn`, when no Claim exists, return the report path and result commit directly to Discussion.
6. When a Claim exists, let release write one idempotent pending notification. Otherwise the visible Worker result is the `warn` handoff to Discussion.
7. End the Worker. Do not wait for, poll, or directly contact Discussion.

Bind the notification to the originating Discussion session when available. A Worker opened from a neutral window may leave the target empty; the next explicit Discussion entry adopts it. Keep pending notifications in one runtime inbox rather than creating project files per event. The inbox preserves all unread records, only a small recent-read window, and durable notification IDs for deduplication.

In `enforce`, block a normal Worker `Stop` / `TaskCompleted` while its Claim is still active. In `warn`, keep the event non-blocking and return the visible Worker result directly when notification automation is unavailable. A host process forcibly killed before any terminal Hook or Claim release cannot write a notification under this no-daemon design; preserve the stale Claim as recovery evidence and surface it on the next Discussion inspection instead of pretending real-time delivery.

Never modify an immutable report after it enters Git history. A retry gets a new attempt and new report path.

## Stop, Retry, And Takeover

Preserve branch, worktree, Claim, and report evidence long enough to close safely.

- `blocked` or `incomplete`: retain the Task ID, increment `attempt`, allocate a new report, and reacquire authority.
- `rejected` or `abandoned` before integration: preserve the attempt, release or explicitly revoke its Claim, then retry if authorized.
- Integrated work: create a rollback or replacement Task; never erase the integrated attempt.
- Stale Claim: preserve it as evidence and allow a replacement Claim; do not delete or rewrite the old record.
- Active exclusive Claim: offer observation, continuation in the original Worker, stop-and-retry, explicit takeover, or competitive execution. Do not spawn a duplicate.

`revoke` is an audit action and requires explicit user authority.

## Worker Window Rebind

Treat a user-visible and inspectable Worker thread or window as a reusable container, not permanent Task ownership. Allow only one active work unit at a time.

Use this order:

```text
old work terminal or explicitly stopped
-> any live acquired Claim released
-> old scope and validation cleared
-> next Task or Revision read
-> new branch/worktree/work identity verified
-> fresh Claim acquired in enforce, attempted in warn
-> session binding persisted atomically
-> next work starts
```

Deny rebind when old work is running, a non-stale Claim remains active, or the new record lacks scope or validation. Preserve stale Claims as evidence without blocking replacement. In `enforce`, failed new Claim acquisition leaves the window idle and unbound; in `warn`, continue only with the new exact scope and never restore old permissions.

Parse formal Task scope from the standard `Change Set` table's `Target` column and validation from its checklist without Markdown checkbox markers. For a Revision, use the structured `allowed_scope` and `validation_plan` arrays.

Do not route work to a historical Worker thread that currently holds another active Claim.

For the normal low-risk Revision path, `task-revisions.md` contains the complete rebind subset so the Agent does not load this file. Use this section only for failed Claim release/acquisition, stale ownership, takeover, or a non-Revision Task switch.

## Locality Boundary

Filesystem Claims are atomic only across processes and worktrees sharing one local Git common directory. They do not coordinate two machines that share only a remote. State this boundary and use host coordination or a distributed lock for multi-machine execution.
