# Orchestration State Machine

Use this reference for roles, lifecycle states, flow phases, exact commands, contextual approvals, and the pure next-action decision.

## Contents

- State dimensions
- Command recognition risk classes
- Authorization parsing
- Task identity and lifecycle
- Core transitions
- Host action boundary
- Acceptance invariants

## Project Activation Gate

Evaluate project activation before Session Role or command parsing:

```text
inactive = missing .wishgraph/config.json or mode: off
active   = mode: warn or mode: enforce
```

- `use_wishgraph` must come from a user request that explicitly names WishGraph. It may start safe project setup, but successful setup leaves the session `neutral`.
- `start_discussion` is accepted only for an active project and changes `neutral -> discussion`.
- An exact `执行 NNN 任务` in Discussion authorizes and routes an independent Formal Worker. The same exact command in an ordinary neutral session authorizes the Run and binds that current inspectable window as the Formal Worker after Claim acquisition; it must not create another Worker.
- In an inactive project, generic `开始讨论`, `刷新项目状态`, and `执行 NNN 任务` text must not become WishGraph events.
- Global Skill availability, a governance-looking repository, or pre-existing project documents do not imply activation.
- This gate reads only the exact config path. It never scans the repository to guess whether WishGraph should be active.

## Command Recognition Risk Classes

Use bounded tolerance only where a false positive cannot authorize implementation or mutate Task ownership.

### Low-Risk Entry And Refresh

`start_discussion` and `refresh_project_status` may normalize English case, whitespace, surrounding quotes, terminal punctuation, and a small allowlist of polite wrappers. Match the normalized result against a finite alias set using full-string equality.

Examples include `进入讨论模式`, `回到 Discussion`, and `请刷新一下项目状态`. A conversational or compound sentence such as `我们讨论一下颜色` or `刷新项目状态并执行 012` must not match. Never use substring search, semantic similarity, or arbitrary intent inference in the Hook.

### Exact Task And Authority Commands

Task-scoped commands retain exact action and exact structured ID matching. Do not apply the low-risk politeness normalizer to `执行`, `继续执行`, `停止`, `重新执行`, `接管`, or their English forms. Read-only Task inspection also keeps exact ID matching so `012`, `012b`, and `012ba` cannot collide.

When no exact command exists, produce no Hook event or authority. The Agent may ask what the user intended. The one exception is a pending, unique `approve_worker_launch`: a bounded contextual affirmative reply can consume that already-persisted transition. It cannot name a different Task, change scope, or give Discussion implementation authority.

## State Dimensions

Keep four orthogonal dimensions. Do not overload Task status with session or routing meaning.

### Session Role

```text
neutral
discussion
worker
```

Integration is not a role. It is a temporary Discussion-local phase.

### Durable Task Lifecycle

```text
draft -> approved -> integrated -> reviewed
```

Task files use only `draft -> approved -> integrated -> reviewed` and do not mirror transient execution progress. The canonical Run owns `dispatching -> running -> succeeded|failed|decision_required -> integrating -> integrated`. Preserve terminal audit evidence in immutable Runs, reports, Claims, and Git.

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
2. Interpret a bounded contextual affirmative reply only when exactly one current `expected_transition` exists. This includes common replies such as `行，就按推荐执行吧`, `没问题，开始执行`, or `Sounds good, go ahead`; reject questions, negations, conditions, scope changes, and competing Task references.
3. Ask for the exact Task or action when more than one interpretation remains.

Inspect, observe, status, and refresh are read-only. They do not consume `expected_transition` or grant Worker authority.

Never produce an authorization result that allows Discussion to implement business code.

### Optional Execution Profile

Profile is a host-adapter preference, not an authority event. After an exact Task command, accept compact bilingual aliases such as `执行 012b terra 极高` or `execute 012b sonnet high`. During one pending authorization, accept the same profile after an affirmative reply, such as `批准，用 sonnet 高`.

Before requesting authorization, Discussion recommends per Task from the user's quality, speed, cost, quota, and availability constraints plus Task complexity and risk. Persist grounded host-specific choices in the Task state's `worker_execution_profiles`; omit any host for which only its current default is known. Then display the current-host recommendation, for example: `将执行 012b 任务，建议 terra / 极高。回复“批准”使用本次建议，或回复“执行 012b sol 高”覆盖。` A plain approval or exact Task command without a profile uses that Task recommendation, falling back to the actual host default only when none exists. Reject unknown suffix text instead of silently turning it into authority. Never infer a profile from unrelated discussion text or translate a model between hosts.

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

- `neutral + exact Task authority -> current window routing_worker`; no prior `start_discussion` command and no nested Worker are required.
- `discussion + exact Task authority -> routing_worker + independent Worker launch`.
- Explicit authority atomically creates one canonical Run; no authorization commit is required.
- `authorized Run + exact inspectable Worker binding + acquired Claim -> Run running`.
- `Run running + committed immutable report + released Claim -> Run succeeded|failed|decision_required`.
- Any Worker terminal result first enters `integration_pending`.
- Safe completed evidence produces a one-time reducer transition grant, then the bound Discussion acquires the lease and enters local `integrating`.
- Material risk or ambiguity enters `decision_required` with one concrete question.
- Missing evidence or failed validation enters Worker repair rather than integration.
- Successful integration moves the durable Task from `draft` or `approved` to `integrated`; human acceptance moves it to `reviewed`.
- A Revision integrates without regressing an already integrated or reviewed parent Task.

Do not persist `waiting_for_worker` until a real Worker exists and the runtime write succeeds. If host creation fails, persist `waiting_for_user_launch` and give a host-neutral handoff containing the exact project directory, copy-ready `codex` and `claude` startup commands with their resolved profiles, and the final `执行 <task-id>` line. Model selection happens in the startup command; the Task command remains stable.

## Host Action Boundary

Map semantic actions without changing authority:

| Semantic action | Codex | Claude Code | Unsupported host |
| --- | --- | --- | --- |
| `launch_worker` | Prepare and create a native inspectable `wishgraph-worker` Agent thread, then persist its real ID | Ask the Host Adapter to use a native background session; never launch from a Hook | Show the cross-host manual handoff |
| launch failure | Show the cross-host manual handoff | Show the cross-host manual handoff | N/A |
| `route_revision` | Send to an eligible inspectable Worker thread or create one | Use an eligible Worker route or output the exact Revision command | Output the exact Revision command |
| `auto_integrate` | Enter current Discussion phase | Persist pending until Discussion resumes | Persist pending until Discussion resumes |
| `decision_required` | Ask the material question | Ask the same material question | Ask the same material question |

Stop Discussion execution after a manual fallback. Never append an offer to implement directly.

Represent host mechanics with orthogonal capabilities rather than reducer branches:

```text
can_spawn_execution_thread
can_inspect_execution_thread
can_bind_thread_id
can_stop_or_steer_thread
can_isolate_worktree
can_observe_terminal_result
can_gate_writes
can_gate_builds
can_deliver_result_to_discussion
```

The reducer asks whether the Formal Worker contract can be met. The Host Adapter chooses Codex, Claude, or manual mechanics. A capability never grants Task authorization or Discussion implementation rights. Parallel writing requires distinct worktrees even when the host can create several Agent threads.

## Acceptance Invariants

- Two pending Tasks make a short approval ambiguous.
- First activation and Discussion entry are separate explicit events.
- Inactive projects ignore generic WishGraph-shaped entry phrases.
- Low-risk aliases require full normalized equality; conversational and compound prose stays unmatched.
- High-risk commands never inherit low-risk politeness stripping.
- Exact ID parsing prevents prefix collisions.
- Discussion business writes and implementation builds are denied.
- A Worker session can never transition to Discussion; public `session set/apply` cannot write role, phase, expected transition, Worker identity, or Integration authority.
- Worker entry requires approval, dependency checks, correct branch/worktree, and a fresh Claim.
- Integration lease acquisition requires the bound Discussion's unconsumed transition grant plus fresh Task, Report, released-Claim, branch, and worktree evidence.
- Integration never creates a user-visible window.
- Safe integration never asks permission twice.
- High-risk integration asks about the risk, not whether to start the process.
