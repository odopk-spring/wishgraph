# WishGraph Project Instructions For Claude Code

Use WishGraph as the project governance layer for AI-assisted development.

## Start Mode

- If this project has no usable `PRD.md`, do not implement code first.
- Use the user's language by default. If the user requests bilingual output, write key prompts, summaries, and task explanations in Chinese first, then English.
- Do not translate file paths, commands, code identifiers, symbols, routes, package names, or environment variables.
- Ask in the selected language:
  - Chinese: `先不用写完整 PRD。请用几句话告诉我：1. 你想做一个什么项目？2. 最先服务谁？3. 他们第一次打开时最应该完成什么动作？4. 你会用什么结果判断 v0 做对了？如果还不确定，可以只回答第 1 点，我会继续一问一问补齐。`
  - English: `You do not need a full PRD yet. In a few sentences, tell me: 1. What are you trying to build? 2. Who should it serve first? 3. What should they be able to do on the first successful use? 4. What result would make you say v0 is working? If you are not sure, answer only item 1 and I will fill the rest one decision at a time.`
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
