# Formal Task Specification

Use this reference when creating, reviewing, or splitting `tasks/build/NNN-short-slug.md`. Keep legacy `.tasks/build/` when an existing project already uses it.

## Contents

- Quality and context budget
- Required state and sections
- Review checklist
- Split rules
- Worked-example routing

## Quality And Context Budget

Write a Task that a Worker can execute without chat history. Include only context that changes implementation decisions.

Prefer:

- Observable behavior and acceptance criteria.
- Exact files, symbols, routes, APIs, tests, and commands.
- Anchors instead of pasted code.
- Explicit `Do Not Do` boundaries.
- One validation and rollback unit.

Avoid full chat transcripts, long PRD copies, unrelated roadmap, and undecided alternatives. Resolve product ambiguity in Discussion before authorizing implementation.

## Required Structure

Start from `assets/templates/NNN-task.md` or its `zh-CN` mirror:

````markdown
# NNN - Task Title

Spec source:
Dependencies:
Language mode:

<!-- wishgraph:task-state:start -->
```json
{
  "schema_version": 1,
  "kind": "task",
  "task_id": "001",
  "parent_task_id": null,
  "dependencies": [],
  "status": "draft",
  "work_type": "sequential",
  "batch_id": null,
  "attempt": 1,
  "execution_mode": "exclusive",
  "comparison_group": null,
  "run_report": "reports/runs/001-attempt-1.md",
  "worker_creation_authorized": false,
  "integration_policy": "inherited_task_approval"
}
```
<!-- wishgraph:task-state:end -->

## Intent

## Current State

## Change Set

| Target | Anchor | Required Change |
| --- | --- | --- |

## Implementation Notes

## Do Not Do

## Validation

- [ ] Build:
- [ ] Tests:
- [ ] Manual:
- [ ] One immutable Run Report:
- [ ] Shared-memory impact uses Integrate or justified N/A:
- [ ] Worker did not edit shared project memory:
- [ ] Scope, conflicts, decisions, and readiness recorded:
- [ ] WishGraph worktree check passes when installed:

## Rollback Boundary

## Execution Report Requirements
````

Use exact structured IDs. Start in `draft` with `worker_creation_authorized: false`. Set authority only after the user explicitly authorizes a user-visible and inspectable Worker thread or window.

## Review Checklist

Before Worker authorization, confirm:

- The user-visible outcome is observable.
- Current State comes from repository facts.
- Change Set names stable targets and anchors.
- The implementation surface fits one atomic commit.
- Out-of-scope behavior is explicit.
- Validation commands are concrete and available.
- Rollback is safe and bounded.
- Dependencies and parent identity are exact.
- Work type, execution mode, batch/comparison group, and integration policy are correct.
- The Run Report path is unique for the Task and attempt.
- Shared-memory impact and WishGraph checks are required.
- Human-facing language follows the project mode without translating technical literals.

## Work Classification

- `sequential`: one Task or ordered dependencies; safe integration may inherit Task authority.
- `parallel_batch` / `parallel_independent`: distinct goals that can all integrate after mechanical independence gates.
- `competitive`: alternatives for one goal; read `competitive-execution.md` and integrate one winner.
- `high_risk`: material product, architecture, API, schema, migration, security, or unsafe rollback decision; return to Discussion.

Do not encode a low-risk correction to a completed result as a full Task. Read only `task-revisions.md` for the normal Revision fast path.

## Split A Task When

- It touches unrelated modules.
- It mixes different validation or rollback strategies.
- It combines API/schema work with presentation polish.
- It contains an unresolved product decision.
- Parallel candidates overlap files, contracts, validation state, or rollback.
- One atomic commit cannot express the result safely.

## Worked Example

Use `assets/templates/EXAMPLE-good-task.md` or its `zh-CN` mirror as the canonical compact example. Check that it demonstrates:

- Exact intent and repository facts.
- A three-column Change Set.
- Scope-drift prevention.
- Targeted build/test/manual evidence.
- Immutable report and shared-memory impact.
- One rollback boundary.

Do not paste the example into every generated Task. Adapt its structure to the current repository.
