# NNN - Task Title

Status: Pending
Spec source: Link or summarize the approved requirement.
Dependencies: List required prior tasks, migrations, or decisions.
Language mode: Follow `prompts/DISCUSSION_AI.md` unless this task explicitly overrides it.

## Intent

State the user-visible goal in one short paragraph. This section must be understandable without reading chat history.

## Current State

Summarize the relevant repo facts discovered from files, tests, logs, or docs.

## Change Set

| Target | Anchor | Required Change |
|---|---|---|
| `path/to/file` | `SymbolOrRouteName` | Describe the exact behavior change |

## Implementation Notes

- Keep the patch minimal.
- Use existing project patterns and helpers.
- Preserve compatibility unless this task explicitly authorizes a breaking change.

## Do Not Do

- Do not refactor unrelated files.
- Do not introduce new dependencies unless explicitly approved.
- Do not change public APIs, data schema, security, billing, or deletion behavior unless listed in Change Set.

## Validation

- [ ] Build: `<command>`
- [ ] Tests: `<command or test names>`
- [ ] Manual check: `<scenario>`
- [ ] `PRD.md` updated if product scope, roadmap, accepted behavior, or progress changed.
- [ ] `ARCHITECTURE.md` updated if dependencies, structure, data flow, or ownership changed.
- [ ] `CODEMAP.md` updated if files, symbols, contracts, or status changed.
- [ ] `reports/DEV_REPORT.md` updated with evidence.
- [ ] `prompts/DISCUSSION_AI.md` current progress and next-task state updated.
- [ ] `prompts/DISCUSSION_AI.md` language mode updated if preference changed.
- [ ] One atomic commit created for this task, unless the user explicitly requested no commit.
- [ ] No unrelated diffs staged.

## Rollback Boundary

Describe the smallest revertable unit. Name any generated files, migration effects, or external side effects.

## Execution Report Requirements

The final report must include:

- Files changed.
- Behavior changed.
- Validation commands and results.
- Risks or checks not run.
- Any follow-up task candidates.
