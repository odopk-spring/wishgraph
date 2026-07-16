# Worker Execution And Claim Lifecycle

Use this reference for Formal Worker launch, host fallback, preflight, Claim/worktree binding, closeout, stop/retry/takeover, or Worker-thread reuse. Ordinary Revision work uses `task-revisions.md` instead; return here only for Worker recovery or abnormal rebind.

## Contents

- Authority and visible routing
- Host fallback
- Entry preflight
- Claim contract
- Execution rules
- Closeout
- Stop and recovery
- Worker rebind
- Locality boundary

## Authority And Visible Routing

Discussion records one exact `approve_worker_launch(<task-id>)`. A unique contextual reply may authorize that transition; two eligible Tasks require an exact choice. Explicit `执行 <task-id> 任务` commands take priority but still require structured Task, dependency, branch, worktree, and Claim checks.

Persist authority by moving the exact Task from `draft` to `approved` and setting `worker_creation_authorized: true`. Then enter `routing_worker`.

Create only a separate user-visible and inspectable Worker thread or window. A native Agent becomes a Formal Worker only when it has a stable ID, independent context, user-visible activity, inspect/stop/steer controls, exact Task/Claim/branch/worktree binding, write/build gates, and structured terminal evidence. Never substitute a hidden subagent or let Discussion implement the Task. Use the title:

```text
<task-id> · <short title> · WG Worker
```

Give the Worker the repository, exact durable record, `prompts/EXECUTION_AI.md`, branch/worktree requirement, Claim protocol, validation, immutable Run Report path, shared-state restriction, and atomic-commit requirement.

After real creation, store the returned thread/window reference, enter `waiting_for_worker`, and stop Discussion execution actions. If runtime persistence fails, revoke the new Claim or record launch failure; never report an intended Worker as running.

Classify Agent containers before giving them authority:

| Kind | Allowed use | Claim and business writes |
| --- | --- | --- |
| Formal Worker | One authorized Task or Revision in an inspectable, controllable thread/window | Allowed only after exact preflight and Claim acquisition |
| Helper Subagent | Exploration, retrieval, logs, review, or bounded validation assistance | No Worker Claim; read-only by default |
| Hidden/Internal Agent | Host-internal work without an independently inspectable thread | Never a Worker; no Claim or business writes |

Agent identity does not authorize execution. Built-in Codex `explorer`, reviewer-style Agents, Claude Explore/Plan Agents, `/fork`, and hidden subagents remain Helpers unless the host container independently satisfies every Formal Worker condition and the normal Task authorization and Claim path is completed. A Formal Worker must not create another Formal Worker.

## Host Fallback

### Codex

Use the project-scoped `.codex/agents/wishgraph-worker.toml` custom Agent in a user-visible and inspectable Agent thread. The App surfaces subagent threads, CLI provides `/agent`, and supported IDE views expose background Agent activity. Hooks never spawn the Agent.

After authorization, the Host Adapter prepares the exact Task path, scope, validation, report path, and Claim requirements. The active Codex host starts `wishgraph-worker`, then registers the real returned thread ID. Keep the Discussion in `routing_worker` until that registration succeeds; only then enter `waiting_for_worker`. Observe completion only from structured host thread state plus durable Task, Run Report, and released Claim evidence.

If creation or registration fails, enter `waiting_for_user_launch` and output exactly:

```text
执行 <task-id> 任务
```

### Claude Code

Detect one host-only capability tier without changing the reducer or authority:

| Tier | Formal Worker behavior |
| --- | --- |
| `background_session` | After authorization, run `claude --bg --agent wishgraph-worker "执行 <task-id> 任务"` and persist the returned Claude session ID. |
| `forked_subagent` | Use only as a Helper for short, low-risk checks with no durable ownership; formal business work still uses the manual command. |
| `manual_command_only` | Output exactly `执行 <task-id> 任务` and stop Discussion execution. |

Require the managed `wishgraph-worker` Agent definition before background launch. Claude Code silently falls back to a default template when an Agent name is missing, so an absent or unrecognized definition is a launch failure, not permission to use the default Agent.

The background Worker acquires its own Claim after Claude has placed it in its actual branch/worktree. Require the authorized Task record to match current `HEAD`, use Claude Worktree `baseRef: head`, and expose the project runtime through `.wishgraph` in `worktree.symlinkDirectories`; otherwise use the manual command. Persist `claude_session_id`, Task ID, capability tier, launch state, and initial branch/worktree immediately; copy Claim ID and its bound branch/worktree into the Discussion runtime only after structured refresh observes the real Claim. Do not move the Task to `running` merely because `claude --bg` returned.

Refresh with `claude agents --json --all --cwd <project>`. Use only structured state plus the durable Task, Run Report, and released Claim to enter `integration_pending`; logs are diagnostic text and never completion evidence. Expose `claude logs <id>` and `claude attach <id>` for inspection or recovery. A failed, blocked, missing, or unknown session without complete durable evidence becomes `manual_intervention_required` rather than a guessed terminal result.

`/tasks` displays background work associated with the current Claude session. It does not create a WishGraph Task, authorize a Worker, acquire a Claim, or replace the project Task record. `/fork`, Explore, Plan, ordinary background subagents, and hidden agents are Helpers unless they expose a stable independent session, inspect/control surface, exact binding, gates, and structured terminal evidence. They are never the default Formal Worker implementation and cannot bypass scope, validation, report, or Claim gates.

### Unknown Hosts

Require a new user-opened inspectable window. Output the same one-line command and stop. Do not print the full prompt or Task Spec and do not offer direct implementation.

### Neutral Entry

A neutral window receiving the exact command reads `CONVENTIONS.md`, `prompts/EXECUTION_AI.md`, and the exact Task, then performs preflight and Claim acquisition before becoming `worker`.

## Entry Preflight

Before implementation:

1. Read `CONVENTIONS.md`, `prompts/EXECUTION_AI.md`, and the exact Task or Revision record.
2. Verify structured ID, lifecycle, Worker authority, dependencies, attempt, report path, allowed scope, and validation plan.
3. Verify the intended branch and absolute worktree.
4. Inspect active and stale Claims across the repository's Git common directory.
5. Atomically acquire a Claim for the exact work unit.
6. Persist the Worker session binding before moving the work to `running`.

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

Heartbeat during long work. Stop immediately after branch or worktree mismatch. Treat expired heartbeats as stale evidence, not free authority.

## Execution Gates

Require the bound active Claim for:

- Business-file writes.
- Implementation builds and tests.
- Dependency installation.
- The Worker's atomic commit.
- Updates to its own Task or Revision lifecycle and Run Report.

Restrict writes to `allowed_scope`. Restrict gated build/test operations to `validation_plan`. Escalate when the implementation needs a public API, schema, persistence, migration, dependency, security, privacy, or product decision not present in the durable record.

Allow Workers to read shared memory but not rewrite it. Record proposed updates as `Integrate` or concrete `N/A` rows in the Run Report.

## Closeout

For every execution unit:

1. Run prescribed build, test, lint, manual, and WishGraph checks.
2. Create exactly one new immutable `reports/runs/<work-unit>-attempt-N.md`.
3. Record files changed, behavior, validation evidence, scope check, conflicts, material decisions, risks, and shared-memory impact.
4. Move the Task or Revision to `completed`, `blocked`, or `incomplete` from real evidence.
5. Create one bounded atomic commit unless the user explicitly forbids it.
6. Release the Claim only after durable terminal state and report evidence exist.
7. Let Claim release write one idempotent pending notification under the Git common directory. `Stop` / `TaskCompleted` may retry the same notification key, but cannot create a duplicate.
8. End the Worker. Do not wait for, poll, or directly contact Discussion.

Bind the notification to the originating Discussion session when available. A Worker opened from a neutral window may leave the target empty; the next explicit Discussion entry adopts it. Keep pending notifications in one runtime inbox rather than creating project files per event. The inbox preserves all unread records, only a small recent-read window, and durable notification IDs for deduplication.

Block a normal Worker `Stop` / `TaskCompleted` while its Claim is still active. A host process forcibly killed before any terminal Hook or Claim release cannot write a notification under this no-daemon design; preserve the stale Claim as recovery evidence and surface it on the next Discussion inspection instead of pretending real-time delivery.

Never modify an immutable report after it enters Git history. A retry gets a new attempt and new report path.

## Stop, Retry, And Takeover

Preserve branch, worktree, Claim, and report evidence long enough to close safely.

- `blocked` or `incomplete`: retain the Task ID, increment `attempt`, allocate a new report, and reacquire authority.
- `rejected` or `abandoned` before integration: preserve the attempt, release or explicitly revoke its Claim, then retry if authorized.
- Integrated work: create a rollback or replacement Task; never erase the integrated attempt.
- Stale Claim: require explicit revoke authority or proven abandonment. Do not overwrite it silently.
- Active exclusive Claim: offer observation, continuation in the original Worker, stop-and-retry, explicit takeover, or competitive execution. Do not spawn a duplicate.

`revoke` is an audit action and requires explicit user authority.

## Worker Window Rebind

Treat a user-visible and inspectable Worker thread or window as a reusable container, not permanent Task ownership. Allow only one active work unit at a time.

Use this order:

```text
old work terminal or explicitly stopped
-> old Claim released
-> old scope and validation cleared
-> next Task or Revision read
-> new branch/worktree/work identity verified
-> fresh Claim acquired with new scope and validation
-> session binding persisted atomically
-> next work starts
```

Deny rebind when old work is running, the old Claim remains active, or the new record lacks scope or validation. If new Claim acquisition fails after release, keep the window idle and unbound; never restore old permissions.

Parse formal Task scope from the standard `Change Set` table's `Target` column and validation from its checklist without Markdown checkbox markers. For a Revision, use the structured `allowed_scope` and `validation_plan` arrays.

Do not route work to a historical Worker thread that currently holds another active Claim.

For the normal low-risk Revision path, `task-revisions.md` contains the complete rebind subset so the Agent does not load this file. Use this section only for failed Claim release/acquisition, stale ownership, takeover, or a non-Revision Task switch.

## Locality Boundary

Filesystem Claims are atomic only across processes and worktrees sharing one local Git common directory. They do not coordinate two machines that share only a remote. State this boundary and use host coordination or a distributed lock for multi-machine execution.
