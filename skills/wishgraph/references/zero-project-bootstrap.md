# Zero Project Bootstrap

Use this reference when a user starts with a vague idea, opens an empty project, has no PRD, or asks WishGraph to start a project from scratch.

## Principle

The first conversation is not an execution window. It is a grill-first discussion window whose job is to turn a low-bandwidth idea into a PRD and a first executable task.

Do not start by writing app code. Start by asking:

```text
你现在有什么想法？可以很粗糙，只要说你想做什么、给谁用、解决什么问题。
```

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

If the user wants to continue discussing instead, continue in the discussion window and keep `prompts/DISCUSSION_AI.md` current.

## Discussion Window Migration

When the user says any equivalent of "迁移讨论窗口", "换一个窗口继续", "给我交接提示词", "复制讨论 prompt", or "handoff this discussion":

1. Read current project files if needed.
2. Update `prompts/DISCUSSION_AI.md` if current progress, roadmap, open decisions, or risks changed.
3. Output the full content of `prompts/DISCUSSION_AI.md` in a fenced code block.
4. Prepend one short instruction: "Copy this into the new discussion agent."

Do not merely summarize. The purpose is copy-paste continuity across agents.
