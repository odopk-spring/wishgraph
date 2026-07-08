# Zero Project Bootstrap

Use this reference when a user starts with a vague idea, opens an empty project, has no PRD, or asks WishGraph to start a project from scratch.

## Principle

The first conversation is not an execution window. It is a grill-first discussion window whose job is to turn a low-bandwidth idea into a PRD and a first executable task.

Do not start by writing app code. Start with a light intake prompt:

```text
先不用写完整 PRD。请用几句话告诉我：
1. 你想做一个什么项目？
2. 最先服务谁？
3. 他们第一次打开时最应该完成什么动作？
4. 你会用什么结果判断 v0 做对了？
如果还不确定，可以只回答第 1 点，我会继续一问一问补齐。
```

English:

```text
You do not need a full PRD yet. In a few sentences, tell me:
1. What are you trying to build?
2. Who should it serve first?
3. What should they be able to do on the first successful use?
4. What result would make you say v0 is working?
If you are not sure, answer only item 1 and I will fill the rest one decision at a time.
```

If the user asks for bilingual output, ask both lines together. Then keep important user-facing prompts and summaries in Chinese first, then English. Do not translate file paths, commands, code identifiers, symbols, routes, package names, or environment variables.

Then ask one question at a time. Each question must include a recommended default so the user can move forward without designing everything alone.

## Grill Loop

Resolve these branches in order. Skip a branch only when the answer is already clear from repository files or prior user text.

1. Product outcome: what should exist when this works?
2. Target user: who uses it first?
3. Core workflow: what is the first repeated user action?
4. Platform and constraints: web, mobile, desktop, CLI, local-only, cloud, cost, privacy, latency.
5. Non-goals: what must not be built in v0?
6. First thin slice: the smallest useful end-to-end behavior.
7. Acceptance: how the user will judge that the slice works.
8. Validation: build/test/manual checks that prove it.
9. Risk boundary: what decisions need explicit human approval before execution.

## Question Format

Use this shape:

```text
问题 N：<one concrete decision>

我建议先选：<recommended default>。
原因：<one sentence>.
如果你不同意，可以直接改成你的版本。
```

English:

```text
Question N: <one concrete decision>

Recommended default: <recommended default>.
Reason: <one sentence>.
If you disagree, replace it with your version.
```

Bilingual:

```text
问题 N / Question N: <one concrete decision>

我建议先选 / Recommended default: <recommended default>.
原因 / Reason: <one sentence>.
如果你不同意，可以直接改成你的版本。 / If you disagree, replace it with your version.
```

Do not ask a list of many questions at once. Do not turn the first conversation into a long questionnaire.

## Convergence Criteria

Stop grilling and write files when the agent can fill:

- `PRD.md` product frame, goals, non-goals, current decisions, roadmap, acceptance standards.
- `ARCHITECTURE.md` first plausible architecture and dependency boundaries.
- `CODEMAP.md` initial feature-to-file map or planned file map.
- `CONVENTIONS.md` collaboration and validation rules.
- `prompts/DISCUSSION_AI.md` current state, open decisions, and next likely task.
- `prompts/EXECUTION_AI.md` stable execution prompt.
- `.tasks/build/001-*.md` first bounded execution task.
- `reports/DEV_REPORT.md` empty or bootstrap report template.

## After PRD Completion

When the PRD and first task are ready, tell the user:

```text
下一步请新开一个执行窗口。复制 `prompts/EXECUTION_AI.md` 的内容，再附上 `.tasks/build/<task>.md`，让执行 AI 只按这个任务实现。
```

English:

```text
Next, open a new execution window. Copy the content of `prompts/EXECUTION_AI.md`, then attach `.tasks/build/<task>.md`, and ask the execution AI to implement only that task.
```

If the user wants to continue discussing instead, continue in the discussion window and keep `prompts/DISCUSSION_AI.md` current.

## Discussion Window Migration

When the user says any equivalent of "迁移讨论窗口", "换一个窗口继续", "给我交接提示词", "复制讨论 prompt", or "handoff this discussion":

1. Read current project files if needed.
2. Update `prompts/DISCUSSION_AI.md` if current progress, roadmap, open decisions, or risks changed.
3. Output the full content of `prompts/DISCUSSION_AI.md` in a fenced code block.
4. Prepend one short instruction: "Copy this into the new discussion agent."

Do not merely summarize. The purpose is copy-paste continuity across agents.
