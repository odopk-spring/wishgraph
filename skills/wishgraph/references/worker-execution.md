# Worker Execution And Claim Lifecycle

Use this reference for visible Worker launch, host fallback, preflight, Claim/worktree binding, closeout, stop/retry/takeover, or Worker-window reuse. Ordinary Revision work uses `task-revisions.md` instead; return here only for Worker recovery or abnormal rebind.

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

Create only a real user-visible, inspectable, controllable Worker. Never substitute a hidden subagent or let Discussion implement the Task. Use the title:

```text
<task-id> · <short title> · WG Worker
```

Give the Worker the repository, exact durable record, `prompts/EXECUTION_AI.md`, branch/worktree requirement, Claim protocol, validation, immutable Run Report path, shared-state restriction, and atomic-commit requirement.

After real creation, store the returned thread/window reference, enter `waiting_for_worker`, and stop Discussion execution actions. If runtime persistence fails, revoke the new Claim or record launch failure; never report an intended Worker as running.

## Host Fallback

### Codex

Use a visible Worker task/thread when the host exposes that capability. Record only the real returned ID. If creation fails, enter `waiting_for_user_launch` and output exactly:

```text
执行 <task-id> 任务
```

### Claude Code And Unknown Hosts

Use `/task` only when it creates a genuinely separate visible session; otherwise require a new user-opened window. Output the same one-line command and stop. Do not print the full prompt or Task Spec and do not offer direct implementation.

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
7. Emit a Worker terminal event so Discussion enters `integration_pending`.

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

Treat a visible Worker window as a reusable container, not permanent Task ownership. Allow only one active work unit at a time.

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
