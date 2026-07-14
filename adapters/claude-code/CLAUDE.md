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
6. `prompts/EXECUTION_AI.md` and the assigned `tasks/build/*.md` for execution sessions; accept `.tasks/build/*.md` in an existing legacy project
7. `reports/PROJECT_STATUS.md` for the current integrated Project Status

## Collaboration Rules

- Planning sessions write PRD, architecture notes, code maps, prompts, and task specs.
- Planning sessions classify work as discussion, sequential, parallel_batch, or high_risk, recommend the execution shape, and let the user confirm it.
- Execution sessions implement only the approved task spec.
- Keep task specs self-contained; do not rely on chat history.
- Worker sessions use separate branches or worktrees, create one immutable `reports/runs/<work-unit-id>.md`, and record Integrate or N/A proposals without editing shared memory.
- An integration session merges with `--no-commit`, rewrites `reports/PROJECT_STATUS.md` as the current snapshot, updates affected shared memory, and then refreshes the concise dynamic handoff in `prompts/DISCUSSION_AI.md`.
- Worker creation requires an explicit human command. When the host supports user-visible task or session creation, the planning agent creates one visible Worker per authorized spec, hands off the execution prompt and task file, and names it `<task-id> · <short title> · WG Worker`. Never create Workers silently or use hidden subagents; manual copying is the fallback when this capability is unavailable.
- Persist that command in task-state before creation: `draft -> approved` and `worker_creation_authorized: true`. Workers record execution states, Integration records `integrated`, and discussion records `reviewed` after human acceptance.
- Integration is temporary. Safe sequential task approval includes normal integration authority; parallel_batch and high_risk require explicit user confirmation. Use background execution only when the host supports it, otherwise switch roles or provide a one-time launch instruction truthfully.
- Hooks expose status and enforce boundaries; they do not choose parallelism, launch agents, merge code, write semantic memory, or replace review.
- SessionStart may inject latest integrated results into new or resumed sessions; this is not a live push into a continuously running window.
- Prefer one atomic commit per completed execution unit. A tiny approved ad-hoc edit may omit a task file, but not closeout.
- When `.wishgraph/hooks/memory_sync.py` exists, run its worktree check before claiming completion.

## Handoff

- When the user asks to migrate discussion, update `prompts/DISCUSSION_AI.md` and print its full content for copying.
- When PRD and the first task are ready, ask whether to create the execution session. After explicit authorization, create and configure the user-visible Worker when supported; otherwise provide the complete prompt and approved task file as a manual fallback.

## Debugging

For bugs, trace:

```text
Error -> State -> Code -> Spec
```

Do not start by guessing a familiar file. Find the earliest polluted assumption or state transition.
