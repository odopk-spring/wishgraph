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

- Discussion sessions write PRD, architecture notes, code maps, prompts, and task specs. They do not write business code or run implementation builds/tests.
- Discussion sessions classify work as discussion, sequential, parallel_batch, or high_risk, recommend the execution shape, and let the user confirm it.
- Execution sessions implement only the approved task spec.
- Keep task specs self-contained; do not rely on chat history.
- Worker sessions use separate branches or worktrees, create one immutable `reports/runs/<work-unit-id>.md`, and record Integrate or N/A proposals without editing shared memory.
- Discussion-local Integration uses a bound lease, merges with `--no-commit`, rewrites `reports/PROJECT_STATUS.md` as the current snapshot, updates affected shared memory, and then refreshes the concise dynamic handoff in `prompts/DISCUSSION_AI.md`.
- Worker creation requires an explicit human command. Claude Code does not create the Worker window automatically: after authorization, output exactly `执行 <task-id> 任务` and stop. The user runs that line in a separate neutral window, which enters the Worker role after preflight.
- Route exact execute/stop/retry/takeover and explicit competitive commands through structured Task IDs and Git-common-dir Claims. Contextual approvals are valid only for one unique `expected_transition`.
- Persist that command in task-state before creation: `draft -> approved` and `worker_creation_authorized: true`. Workers record execution states, Integration records `integrated`, and discussion records `reviewed` after human acceptance.
- Every Worker terminal event enters `integration_pending`. Safe sequential and mechanically proven `parallel_independent` results enter Discussion-local Integration automatically; risk, conflict, blocking, competition, or ambiguity becomes a concrete `decision_required` or `blocked` state. Never create a separate Integration window.
- Hooks expose status and enforce boundaries; they do not choose parallelism, launch agents, merge code, write semantic memory, or replace review.
- New windows are neutral. Default SessionStart is safety-only and does not activate Discussion; explicit Discussion entry or refresh loads current state.
- Prefer one atomic commit per completed Task-backed execution unit.
- When `.wishgraph/hooks/memory_sync.py` exists, run its worktree check before claiming completion.

## Handoff

- When the user asks to migrate discussion, update `prompts/DISCUSSION_AI.md` and print its full content for copying.
- When PRD and the first task are ready, set one exact `expected_transition` and ask for Worker authorization. After authorization, output only `执行 <task-id> 任务`.

## Debugging

For bugs, trace:

```text
Error -> State -> Code -> Spec
```

Do not start by guessing a familiar file. Find the earliest polluted assumption or state transition.
