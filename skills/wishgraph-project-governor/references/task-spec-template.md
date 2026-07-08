# WishGraph Task Spec Template

Use this structure when creating `.tasks/build/NNN-short-slug.md`.

```markdown
# NNN - Task Title

Status: Pending
Spec source:
Dependencies:

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
- [ ] CODEMAP updated:
- [ ] Dev Report updated:

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

## Split A Task When

- It touches unrelated modules.
- It needs two different validation strategies.
- It mixes schema or API changes with UI polish.
- It includes unresolved product intent.
- The rollback unit is unclear.
