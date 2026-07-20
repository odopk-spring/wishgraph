# Task Revision Fast Path

Use this reference for a clear, low-risk correction to a running or completed Task. For the normal path, read only this file. Do not load the state-machine, Worker, formal-Task, or Integration references unless an exception listed below actually occurs.

## Contents

- User experience and eligibility
- Running or completed parent handling
- Fast routing and Worker work
- Automatic integration
- One-question rule
- Exception routing

## User Experience

Keep the visible flow short:

```text
user requests a small correction
-> acknowledge it as part of the parent result
-> route or create the lightweight Worker automatically
-> run targeted validation
-> auto-integrate when safe
-> present the corrected result
```

Do not ask whether to create the Revision Worker or whether to begin safe integration. The user's concrete correction request supplies Revision routing authority under the already approved parent Task.

Respond once at start and once at completion. Example:

```text
收到，这是 012 的小范围修订。我会调整颜色并做局部验证。
```

## Eligibility

Use the fast path only when every condition is known true:

- One exact parent Task owns the result.
- The request is concrete.
- Scope is small, explicit, and related to the parent result.
- Validation is targeted and available.
- The change is independently revertible.
- It adds no new product feature or architecture direction.
- It changes no public API, schema, persistence, migration, dependency, permission, security, or privacy contract.

Typical fast-path changes: color, spacing, copy, icon, corner radius, animation timing, or a precise local visual defect.

A global theme system, new setting, cross-module contract, storage change, new dependency, permission/security change, or unclear product choice is not a Revision.

## Running Parent

When the original Task's Run is still running and the feedback fits its current scope:

1. Send the feedback to that active Worker.
2. Append the request to the current Task context and Run Report.
3. Keep the current Claim, attempt, and final report.
4. Extend targeted validation only as needed.
5. Do not create a Revision record or request new authority.

Never mix the feedback into an unrelated Worker.

## Completed Or Presented Parent

Before allocating an ID, inspect Revisions for the exact parent. If one Revision is already `pending` or `running`, append compatible feedback to that record and route it to the same Worker; do not create another file or report. More than one open Revision for one parent is an invalid state that must be repaired rather than guessed.

Allocate the next exact ID:

```text
<parent-task-id>-rN
012-r1
012-r10
```

Use `^\d{3,}[a-z]*-r[1-9]\d*$` and exact matching. Create only `tasks/revisions/<revision-id>.md` from `assets/templates/TASK_REVISION.md` or its `zh-CN` mirror:

```json
{
  "schema_version": 1,
  "kind": "revision",
  "revision_id": "012-r1",
  "parent_task_id": "012",
  "status": "pending",
  "user_request": "Change the reading-page theme from bright blue to warm gray.",
  "allowed_scope": ["ui/ReaderTheme.swift"],
  "validation_plan": ["Reader preview"],
  "run_report": "reports/runs/012-r1-attempt-1.md",
  "worker_creation_authorized": true
}
```

Do not create a full Task Spec, repeat product context, or request Worker authority again.

## Fast Routing

Prefer the original user-visible and inspectable Worker thread or window when it is idle:

1. Confirm the parent work is terminal and its old Claim is released.
2. Confirm the historical Worker thread holds no unrelated active Claim.
3. Clear old scope and validation.
4. Read the new Revision record.
5. Acquire a fresh Claim bound to parent ID, Revision ID, session, branch, absolute worktree, allowed scope, and validation plan.
6. Persist the new binding before implementation.

If the original Worker is closed or busy, ask the active Codex host to create a lightweight visible Revision Worker using inherited Revision authority. It does not ask the user to authorize the same correction again, and it is not considered created until the host returns a real inspectable thread ID.

Claude Code or a host that cannot create/route the Worker outputs only:

```text
在任务 <task-id> 的执行窗口执行修订 <revision-id>
```

Discussion never implements the correction as a fallback.

When installed, use the runtime's exact Revision resolution/routing and Claim acquisition commands rather than reconstructing state from prose. Treat the returned host action as authoritative.

## Worker Work

The Revision Worker:

1. Changes only `allowed_scope`.
2. Runs only the targeted validation plus required repository checks.
3. Stops if scope or risk classification expands.
4. Creates one independent atomic commit.
5. Creates one short immutable Run Report.
6. Releases the Revision Claim after durable terminal evidence.

The report records Revision and parent IDs, user request, changed files, targeted validation, scope/risk check, commit, and shared-memory impact. Do not reproduce a full formal-Task narrative.

## Automatic Integration

Every terminal Revision enters `integration_pending` automatically.

For a safe completed Revision:

1. Discussion acquires the minimum Integration lease bound to its session, integration ID, base branch/worktree, parent Task, Revision, and Revision Run Report.
2. Merge/cherry-pick without committing.
3. Run the targeted or necessary combined validation.
4. Rewrite Project Status for this integration. Update other shared memory only when durable project truth changed; otherwise record concrete `N/A` in the Run Report.
5. Create the integration commit, mark the Revision `integrated`, release the lease, and present the result.

A Revision cannot enter `integrated` unless its Run Report is listed in the Project Status written by the same integration change.

Do not regress a parent Task already marked `integrated` or `reviewed`. Do not ask `是否开始集成？`.

## One-Question Rule

If one local detail is missing but the request remains a Revision, ask only that detail. Example: ask which warm-gray token to use when the repository has two equally plausible existing tokens. Do not enter full planning.

## Exception Routing

Load another reference only for the matching exception:

| Exception | Next action | Load |
| --- | --- | --- |
| Parent or expected transition is ambiguous | Resolve exact state | `orchestration-state-machine.md` |
| Claim release, stale owner, takeover, or rebind fails | Repair Worker ownership | `worker-execution.md` |
| Integration conflict, failed combined validation, or lease recovery | Enter material decision/repair | `integration-flow.md` |
| Scope expands or a material risk appears | Create a formal follow-up | `task-spec.md` |
| User asks for multiple alternative fixes | Create candidates | `competitive-execution.md` |

Missing report or failed targeted validation becomes `blocked` and returns to Revision repair. A material product/API/data/security decision enters `decision_required` and asks only the concrete choice.

Do not load exception references pre-emptively “just in case.”
