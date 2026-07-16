# WishGraph Project Instructions For Claude Code

Use WishGraph as the project governance layer for AI-assisted development.

## Start Mode

- Treat a global `/wishgraph` Skill as available, not active in every project. Without an enabled `.wishgraph/config.json`, do not reinterpret generic phrases such as `Start discussion` or `Execute task 012` as WishGraph commands.
- Only an explicit request naming WishGraph activates the project. After safe setup, remain neutral, ask the user to reopen the Claude Code session, and enter Discussion only after the later `Start discussion` command.
- If this project has no usable `PRD.md`, do not implement code first.
- Use the user's language by default. If the user requests bilingual output, write key prompts, summaries, and task explanations in Chinese first, then English.
- Do not translate file paths, commands, code identifiers, symbols, routes, package names, or environment variables.
- Ask in the selected language:
  - Chinese: `先不用写完整 PRD。请用几句话告诉我：1. 你想做一个什么项目？2. 最先服务谁？3. 他们第一次打开时最应该完成什么动作？4. 你会用什么结果判断 v0 做对了？如果还不确定，可以只回答第 1 点，我会继续一问一问补齐。`
  - English: `You do not need a full PRD yet. In a few sentences, tell me: 1. What are you trying to build? 2. Who should it serve first? 3. What should they be able to do on the first successful use? 4. What result would make you say v0 is working? If you are not sure, answer only item 1 and I will fill the rest one decision at a time.`
- Grill one decision at a time, with a recommended default for each question.
- Write the project frame before execution work.

## Role-Specific Read Scope

- **Discussion entry:** read the concise dynamic block in `prompts/DISCUSSION_AI.md`, `reports/PROJECT_STATUS.md`, and the compact active status. Open `PRD.md`, `ARCHITECTURE.md`, `CODEMAP.md`, `CONVENTIONS.md`, or one Task only when the current question needs them.
- **Worker:** read `prompts/EXECUTION_AI.md`, the exact assigned Task or Revision, the smallest necessary Project Status sections, and only References or source files required by its scope. Do not scan unrelated Tasks, historical reports, or the complete source tree.
- **Integration:** read only the selected Run Reports, their Task/Revision records, and shared-memory files affected by those reports.
- Use `.tasks/build/*.md` only as an existing-project compatibility path; new work uses `tasks/build/*.md`.

## Collaboration Rules

- Discussion sessions write PRD, architecture notes, code maps, prompts, and task specs. They do not write business code or run implementation builds/tests.
- Discussion sessions classify work as discussion, sequential, parallel_batch, or high_risk, recommend the execution shape, and let the user confirm it.
- Execution sessions implement only the approved task spec.
- Keep task specs self-contained; do not rely on chat history.
- Worker sessions use separate branches or worktrees, create one immutable `reports/runs/<work-unit-id>.md`, and record Integrate or N/A proposals without editing shared memory.
- Discussion-local Integration uses a bound lease, merges with `--no-commit`, rewrites `reports/PROJECT_STATUS.md` as the current snapshot, updates affected shared memory, and then refreshes the concise dynamic handoff in `prompts/DISCUSSION_AI.md`.
- Worker creation requires an explicit human command. After authorization, prefer the managed native background Worker `claude --bg --agent wishgraph-worker "执行 <task-id> 任务"`. Use a forked subagent only for short low-risk checks. If native launch is unavailable or fails, output exactly `执行 <task-id> 任务` and stop; Discussion never implements as fallback.
- Claude Code cannot automatically deliver a lightweight Revision to an existing Worker. Create the `tasks/revisions/<task-id>-rN.md` record, output only `在任务 <task-id> 的执行窗口执行修订 <revision-id>`, and stop. A reused Worker must release its old Claim and acquire the Revision's new scope/validation binding first.
- Route exact execute/stop/retry/takeover and explicit competitive commands through structured Task IDs and Git-common-dir Claims. Contextual approvals are valid only for one unique `expected_transition`.
- Persist that command in task-state before creation: `draft -> approved` and `worker_creation_authorized: true`. Workers record execution states, Integration records `integrated`, and discussion records `reviewed` after human acceptance.
- Claim release writes one idempotent pending notification in the Git-common runtime. The bound Discussion consumes and marks it read on its next activation; explicit Discussion entry or refresh can adopt it after a host switch. Safe sequential and mechanically proven `parallel_independent` results enter Discussion-local Integration automatically; risk, conflict, blocking, competition, or ambiguity becomes a concrete `decision_required` or `blocked` state. Never create a separate Integration window, daemon, polling loop, IPC service, or popup.
- Hooks expose status and enforce boundaries; they do not choose parallelism, launch agents, merge code, write semantic memory, or replace review.
- New windows are neutral. Default SessionStart is safety-only and does not activate Discussion; explicit Discussion entry or refresh loads current state.
- Prefer one atomic commit per completed Task-backed execution unit.
- When `.wishgraph/hooks/memory_sync.py` exists, run its worktree check before claiming completion.

## Continuation

- A new Claude Code window in the same project continues by saying `Start discussion`; an active Discussion uses `Refresh project status`. Read the persisted handoff and current state instead of printing a full prompt for manual copying.
- A host switch preserves project files but not host-specific thread/session IDs. Repair or install only the current host adapter, then enter Discussion normally.
- When PRD and the first task are ready, set one exact `expected_transition` and ask for Worker authorization. After authorization, use the managed background Worker when available; otherwise output only `执行 <task-id> 任务`.

## Debugging

For bugs, trace:

```text
Error -> State -> Code -> Spec
```

Do not start by guessing a familiar file. Find the earliest polluted assumption or state transition.
