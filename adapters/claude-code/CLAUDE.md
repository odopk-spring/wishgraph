# WishGraph Project Instructions For Claude Code

Use WishGraph as the project governance layer for AI-assisted development.

## Start Mode

- If this project has no usable `PRD.md`, do not implement code first.
- Ask: `你现在有什么想法？可以很粗糙，只要说你想做什么、给谁用、解决什么问题。`
- Grill one decision at a time, with a recommended default for each question.
- Write the project frame before execution work.

## Read Order

When working on planning, task writing, or execution, read:

1. `PRD.md`
2. `ARCHITECTURE.md`
3. `CODEMAP.md`
4. `CONVENTIONS.md`
5. `prompts/DISCUSSION_AI.md` for planning sessions
6. `prompts/EXECUTION_AI.md` and the assigned `.tasks/build/*.md` for execution sessions
7. `reports/DEV_REPORT.md` for the last handoff

## Collaboration Rules

- Planning sessions write PRD, architecture notes, code maps, prompts, and task specs.
- Execution sessions implement only the approved task spec.
- Keep task specs self-contained; do not rely on chat history.
- Update external memory when project truth changes.
- Prefer one atomic commit per completed execution task.

## Handoff

- When the user asks to migrate discussion, update `prompts/DISCUSSION_AI.md` and print its full content for copying.
- When PRD and the first task are ready, tell the user to open a fresh execution session with `prompts/EXECUTION_AI.md` plus the approved task file.

## Debugging

For bugs, trace:

```text
Error -> State -> Code -> Spec
```

Do not start by guessing a familiar file. Find the earliest polluted assumption or state transition.
