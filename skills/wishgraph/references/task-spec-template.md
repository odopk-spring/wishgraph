# WishGraph Task Spec Template

Use this structure when creating `.tasks/build/NNN-short-slug.md`.

For a worked example and review checklist, read `references/good-execution-spec.md`.

```markdown
# NNN - Task Title

Status: Pending
Spec source:
Dependencies:
Language mode:
Run report: `reports/runs/NNN-short-slug.md`

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

## Split A Task When

- It touches unrelated modules.
- It needs two different validation strategies.
- It mixes schema or API changes with UI polish.
- It includes unresolved product intent.
- The rollback unit is unclear.
