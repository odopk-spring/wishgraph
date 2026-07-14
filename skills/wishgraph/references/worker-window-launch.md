# Worker Routing And Discussion-Local Integration

Use this protocol after Discussion has produced a bounded Task and the workflow must decide what happens next.

## Window / Role / Phase / Host Action

- A **Window** is a user-visible host session.
- A **Role** is `neutral`, `discussion`, or `worker`.
- A **Phase** is a temporary flow step such as `routing_worker` or `integrating`.
- A **Host Action** is how Codex, Claude Code, or another host realizes an authorized `FlowPlan`.

Discussion is the long-lived planning and review role. Worker is an independent execution-window role. Integration is a Discussion-local phase, not a separate role or window. Review is the `presenting_result` phase in Discussion.

## Authority And Expected Transition

Discussion moves a ready Task to `awaiting_worker_authorization` and records one structured transition:

```text
approve_worker_launch(<task-id>)
```

When that transition is unique, short replies such as `可以`, `开始吧`, `执行吧`, `继续`, `按这个做`, and `创建吧` authorize the named Worker launch. They never authorize Discussion to implement the Task. If two Tasks are waiting, ask for the exact ID.

Explicit commands such as `执行 002 任务` take priority, but still require an exact structured ID and all Task, dependency, Claim, branch, and worktree checks. `002`, `002b`, and `002ba` never prefix-match one another. Inspect, Observe, and Refresh are read-only and do not consume `expected_transition`.

Persist authorization by moving the exact Task from `draft` to `approved` and setting `worker_creation_authorized: true`. Then move the flow from `awaiting_worker_authorization` to `routing_worker`.

## Worker Payload

A real Worker must remain visible, user-owned, inspectable, and controllable. Use the title:

```text
<task-id> · <short title> · WG Worker
```

Give it the repository, exact Task ID and spec, `prompts/EXECUTION_AI.md`, isolated branch/worktree requirement, authorization, Claim protocol, validation, immutable Run Report path, shared-state restrictions, and atomic-commit requirement.

No Discussion-executes fallback exists. Do not use a hidden subagent as the Worker and do not create unapproved Workers.

## Host Routing

### Codex

When visible task/thread creation is available, use `automatic_thread` and create the Worker. Record only the real returned thread ID. After success, move to `waiting_for_worker` and stop Discussion execution actions.

If creation fails, move to `waiting_for_user_launch` and output exactly:

```text
执行 <task-id> 任务
```

### Claude Code

Use `/task` when it creates a genuinely separate session; otherwise require a new user-opened window. Move to `waiting_for_user_launch` and output only:

```text
执行 <task-id> 任务
```

Do not print the full execution prompt or Task Spec. The new Worker reads them from the repository. Do not claim the Worker is running until a real session exists and has acquired its Claim.

### Unknown Hosts

Use the same one-line `manual_window` fallback. Host limitations never authorize Discussion implementation.

## Neutral Worker Entry

A neutral window receiving `执行 <task-id> 任务` reads `CONVENTIONS.md`, `prompts/EXECUTION_AI.md`, and the exact Task. It verifies approval, authorization, dependencies, attempt, branch/worktree, and existing Claims; atomically acquires the Worker Claim; changes its role to `worker`; moves the Task to `running`; then implements, validates, reports, and commits.

## Completion And Integration

Every Worker terminal event enters `integration_pending` and triggers integration evaluation. Discussion does not ask whether to start integration.

- Safe evidence enters automatic, Discussion-local, safe-when-silent Integration.
- A material API, schema, security, migration, conflict, or product/architecture choice enters `decision_required` and asks only the concrete decision.
- Missing evidence or failed validation becomes `blocked` or `incomplete` and returns to Worker repair.

Before `integrating`, Discussion atomically acquires an Integration lease bound to its session, base branch, worktree, selected Task IDs, and Run Reports. Integration may merge, resolve bounded merge conflicts, run combined validation, update shared state, and create the integration commit. It may not implement new product work.

Integration is a Discussion-local phase. Never create a user-visible Integration window. When Discussion is inactive, persist `integration_pending`; resume automatic evaluation when Discussion next starts or refreshes.
