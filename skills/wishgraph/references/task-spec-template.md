# WishGraph Task Spec Template

Use this structure when creating `tasks/build/NNN-short-slug.md`. Existing projects that already use `.tasks/build/` may keep that legacy path.

For a worked example and review checklist, read `references/good-execution-spec.md`.

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
  "task_id": "NNN-short-slug",
  "status": "draft",
  "work_type": "sequential",
  "batch_id": null,
  "run_report": "reports/runs/NNN-short-slug.md",
  "worker_creation_authorized": false,
  "integration_policy": "inherited_task_approval"
}
```
<!-- wishgraph:task-state:end -->

## Intent

## Current State

## Change Set

| Target | Anchor | Required Change |
|---|---|---|

## Implementation Notes

## Do Not Do

## Validation

- [ ] Build:
- [ ] Tests:
- [ ] Manual:
- [ ] Exactly one new immutable run report created:
- [ ] Shared-memory impact records Integrate or N/A with reasons:
- [ ] Worker did not edit shared project memory:
- [ ] Run report records integration readiness, scope, conflicts, and material new decisions:
- [ ] WishGraph worktree memory check passes when hooks are installed:

## Rollback Boundary

## Execution Report Requirements
````

## Quality Bar

A good task spec is:

- Self-contained.
- Small enough to implement and verify in one execution pass.
- Explicit about what is out of scope.
- Anchored by stable symbols, routes, APIs, commands, tests, or files.
- Clear about validation and rollback.
- Clear about the language mode for human-facing explanations when the project uses bilingual handoff.
- Clear about why the work is sequential, parallel, or high-risk and who must authorize integration.
- Starts as `draft` without Worker authority, then follows the checked lifecycle through approval, execution, integration, and human review.

## Split A Task When

- It touches unrelated modules.
- It needs two different validation strategies.
- It mixes schema or API changes with UI polish.
- It includes unresolved product intent.
- It overlaps files, core modules, validation state, or rollback with another proposed parallel task.
- The rollback unit is unclear.
