# WishGraph Task Spec Template

Use this structure when creating `tasks/build/NNN-short-slug.md`.

For a worked example and review checklist, read `references/good-execution-spec.md`.

```markdown
# NNN - Task Title

Status: Pending
Spec source:
Dependencies:
Language mode:
Run report: `reports/runs/NNN-short-slug.md`
Work type: sequential / parallel_batch / high_risk
Batch ID: N/A or stable batch ID
Integration authorization: Inherited task approval / Requires explicit user confirmation

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
```

## Quality Bar

A good task spec is:

- Self-contained.
- Small enough to implement and verify in one execution pass.
- Explicit about what is out of scope.
- Anchored by stable symbols, routes, APIs, commands, tests, or files.
- Clear about validation and rollback.
- Clear about the language mode for human-facing explanations when the project uses bilingual handoff.
- Clear about why the work is sequential, parallel, or high-risk and who must authorize integration.

## Split A Task When

- It touches unrelated modules.
- It needs two different validation strategies.
- It mixes schema or API changes with UI polish.
- It includes unresolved product intent.
- It overlaps files, core modules, validation state, or rollback with another proposed parallel task.
- The rollback unit is unclear.
