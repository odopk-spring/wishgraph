# Orchestration State Machine

Use this reference for roles, lifecycle states, flow phases, exact commands, contextual approvals, and the pure next-action decision.

## Contents

- State dimensions
- Authorization parsing
- Task identity and lifecycle
- Core transitions
- Host action boundary
- Acceptance invariants

## State Dimensions

Keep four orthogonal dimensions. Do not overload Task status with session or routing meaning.

### Session Role

```text
neutral
discussion
worker
```

Integration is not a role. It is a temporary Discussion-local phase.

### Task Lifecycle

```text
draft -> approved -> running -> completed|blocked|incomplete -> integrated -> reviewed
```

Also preserve terminal audit states such as `rejected`, `abandoned`, `superseded`, and `cancelled` where applicable.

### Flow Phase

```text
planning
awaiting_worker_authorization
routing_worker
waiting_for_user_launch
waiting_for_worker
integration_pending
integrating
decision_required
presenting_result
```

### Expected Transition

Persist at most one structured transition, for example:

```text
approve_worker_launch
launch_worker_manually
wait_for_worker
route_revision
rebind_worker
auto_integrate
resolve_conflict
accept_result
```

Bind it to the exact Task, report, Revision, decision, or integration identifier required by that transition.

## Authorization Parsing

Apply this priority:

1. Parse explicit commands such as `执行 002`, `停止 002`, `重新执行 002`, `接管 002`, `查看 002`, or `查看 002 系列任务`.
2. Interpret contextual replies such as `可以`, `开始吧`, `执行吧`, or `按这个做` only when exactly one current `expected_transition` exists.
3. Ask for the exact Task or action when more than one interpretation remains.

Inspect, observe, status, and refresh are read-only. They do not consume `expected_transition` or grant Worker authority.

Never produce an authorization result that allows Discussion to implement business code.

## Task Identity

Use `^\d{3,}[a-z]*$` for formal Task IDs. Use at least three digits for roots and unbounded lower-case Excel-style suffixes for follow-ups:

```text
012
012a ... 012z
012aa ...
```

Treat suffixes as unique sequences, not hierarchy. Store hierarchy in `parent_task_id` and ordering in `dependencies`. Resolve commands from the structured `task_id`, never from filename prefixes. Report duplicates or missing exact matches instead of guessing.

Use `^\d{3,}[a-z]*-r[1-9]\d*$` for Revision IDs. Never let `012-r1` match `012-r10`.

Retain the same Task ID for retries after `blocked` or `incomplete`; increment `attempt` and allocate a new immutable Run Report. Use a follow-up Task ID only for a new goal. Never reuse an allocated Task ID or rename an approved Task Spec file.

## Pure Transition Boundary

Compute one plan:

```text
FlowPlan = reduce(current_state, user_event, host_capability)
```

Let the reducer choose the semantic next action. Let the Host Adapter decide only how the current host realizes it. Prompts may explain a `FlowPlan`; they may not override it.

Events must come from structured user commands, persisted runtime facts, validated Worker terminal evidence, or real host results. Do not turn arbitrary prose into a forged safe-completion or low-risk event.

## Core Transitions

- `draft + explicit Worker authority -> approved + routing_worker`.
- `approved + real visible Worker + acquired Claim -> running + waiting_for_worker`.
- `running + valid terminal report + released Claim -> completed|blocked|incomplete`.
- Any Worker terminal result first enters `integration_pending`.
- Safe completed evidence enters Discussion-local `integrating` after lease acquisition.
- Material risk or ambiguity enters `decision_required` with one concrete question.
- Missing evidence or failed validation enters Worker repair rather than integration.
- Successful integration moves formal Tasks to `integrated`; human acceptance moves them to `reviewed`.
- A Revision integrates without regressing an already integrated or reviewed parent Task.

Do not persist `waiting_for_worker` until a real Worker exists and the runtime write succeeds. If host creation fails, persist `waiting_for_user_launch` and use the exact manual command.

## Host Action Boundary

Map semantic actions without changing authority:

| Semantic action | Codex | Claude Code / unsupported host |
| --- | --- | --- |
| `launch_worker` | Create a visible Worker task | Output `执行 <task-id> 任务` |
| launch failure | Output the same one-line command | N/A |
| `route_revision` | Send to an eligible visible Worker or create one | Output the exact Revision command |
| `auto_integrate` | Enter current Discussion phase | Persist pending until Discussion resumes |
| `decision_required` | Ask the material question | Ask the same material question |

Stop Discussion execution after a manual fallback. Never append an offer to implement directly.

## Acceptance Invariants

- Two pending Tasks make a short approval ambiguous.
- Exact ID parsing prevents prefix collisions.
- Discussion business writes and implementation builds are denied.
- Worker entry requires approval, dependency checks, correct branch/worktree, and a fresh Claim.
- Integration never creates a user-visible window.
- Safe integration never asks permission twice.
- High-risk integration asks about the risk, not whether to start the process.
