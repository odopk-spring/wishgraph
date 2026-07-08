# 001 - Bootstrap project with WishGraph

Status: Draft
Spec source: First discussion window converted the user's initial idea into `PRD.md`.
Dependencies: None.
Language mode: Follow the user's selected project language; use bilingual Chinese first, English second when requested.

## Intent

Create the first durable project frame before feature implementation. This task should make the repository understandable to future discussion and execution agents without relying on chat history.

## Current State

- The user started from a rough idea.
- `PRD.md` contains the first agreed project frame.
- No business-code implementation should happen in this bootstrap task unless explicitly listed below.

## Change Set

| Target | Anchor | Required Change |
|---|---|---|
| `PRD.md` | Product frame and roadmap | Record target users, goals, non-goals, current decisions, first slice, and acceptance standards. |
| `ARCHITECTURE.md` | Initial architecture | Record planned structure, dependency boundaries, data flow, and risk notes. |
| `CODEMAP.md` | Initial map | Record planned or existing files, feature areas, contracts, probes, and debugging entry points. |
| `CONVENTIONS.md` | Collaboration rules | Record discussion/execution roles, validation order, external memory update rules, and git rule. |
| `prompts/DISCUSSION_AI.md` | Current handoff | Store the current discussion state, open decisions, and next likely task. |
| `prompts/EXECUTION_AI.md` | Execution handoff | Store the stable prompt for execution windows. |
| `.tasks/build/002-first-slice.md` | First implementation task | Write the first bounded implementation task after PRD approval. |
| `reports/DEV_REPORT.md` | Bootstrap report | Record created files, assumptions, and unrun validation. |

## Implementation Notes

- Use repository-native naming and framework conventions.
- Keep the first implementation task small enough for one atomic commit.
- Include "Do Not Do" boundaries in the first implementation task.
- If the repository is empty, map planned files instead of pretending they exist.

## Do Not Do

- Do not implement the product feature in this bootstrap task unless the user explicitly approved direct implementation.
- Do not add dependencies just to satisfy the governance skeleton.
- Do not hide unresolved product decisions; record them as open questions.

## Validation

- [ ] Governance files exist and are self-consistent.
- [ ] `PRD.md` has target user, goals, non-goals, first slice, and acceptance standards.
- [ ] `prompts/DISCUSSION_AI.md` can be copied into a new discussion window.
- [ ] `prompts/EXECUTION_AI.md` plus `.tasks/build/002-first-slice.md` can be copied into a new execution window.
- [ ] `reports/DEV_REPORT.md` records what was created and what remains unknown.
- [ ] `prompts/DISCUSSION_AI.md` records the project language mode.
- [ ] One atomic commit created unless the user explicitly says not to commit.

## Rollback Boundary

Revert this task's single commit to remove the initial WishGraph governance skeleton.

## Execution Report Requirements

Report created files, assumptions, open decisions, next execution task, validation performed, and commit hash.
