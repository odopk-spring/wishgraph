# WishGraph Agent Instructions

Use WishGraph to manage this project through external memory files instead of chat history.

## First Conversation

If there is no usable `PRD.md`, do not start coding.

Use the user's language by default. If the user requests bilingual output, write key prompts, summaries, and task explanations in Chinese first, then English. Do not translate file paths, commands, code identifiers, symbols, routes, package names, or environment variables.

Ask in the selected language:

```text
先不用写完整 PRD。请用几句话告诉我：
1. 你想做一个什么项目？
2. 最先服务谁？
3. 他们第一次打开时最应该完成什么动作？
4. 你会用什么结果判断 v0 做对了？
如果还不确定，可以只回答第 1 点，我会继续一问一问补齐。
```

```text
You do not need a full PRD yet. In a few sentences, tell me:
1. What are you trying to build?
2. Who should it serve first?
3. What should they be able to do on the first successful use?
4. What result would make you say v0 is working?
If you are not sure, answer only item 1 and I will fill the rest one decision at a time.
```

If bilingual output is requested, ask both lines together.

Then ask one decision at a time. Each question must include a recommended default. Continue until you can write a concrete PRD and a bounded first task.

## Required Project Memory

Create or update:

- `PRD.md`: product goals, users, scope, non-goals, roadmap, current decisions.
- `ARCHITECTURE.md`: dependency boundaries, data flow, ownership, risk notes.
- `CODEMAP.md`: feature-to-file map, contracts, validation surfaces, debug entry points.
- `CONVENTIONS.md`: collaboration rules, validation order, git rule, memory update rule.
- `prompts/DISCUSSION_AI.md`: current planning prompt and handoff state.
- `prompts/EXECUTION_AI.md`: stable execution prompt.
- `prompts/INTEGRATION_AI.md`: stable integration prompt and shared-state single-writer rules.
- `.tasks/build/*.md`: self-contained execution task specs.
- `reports/RUN_REPORT.md`: worker-report template.
- `reports/runs/*.md`: immutable worker execution evidence.
- `reports/DEV_REPORT.md`: latest integrated project overview and next handoff.

## Planning Agent

- Clarify intent.
- Update PRD and architecture before implementation.
- Write self-contained task specs.
- Classify work as discussion, sequential, parallel_batch, or high_risk. Explain the sequential or parallel recommendation; the user confirms it.
- Ask whether to create the approved execution window or windows. Only after an explicit human command, use the host's user-visible task or thread capability to create one Worker per authorized spec, hand off the execution prompt and task file, and name it `<task-id> · <short title> · WG Worker`. Never create Workers silently or use hidden subagents; manual copying is the fallback when the host cannot create visible tasks.
- Do not change business code unless the user explicitly approves a tiny direct edit.
- A tiny direct edit may omit a task file, but it still requires validation, a unique run report, and the normal commit boundary.
- If the user asks to migrate discussion, update `prompts/DISCUSSION_AI.md` and output the full prompt for copying.

## Execution Agent

- Read `prompts/EXECUTION_AI.md` and the assigned task file.
- Implement only the approved task.
- Keep the patch minimal and reversible.
- Run validation listed in the task.
- Update task status and create one new immutable `reports/runs/<work-unit-id>.md`.
- Record Integrate or N/A proposals; do not edit shared project memory.
- If `.wishgraph/hooks/memory_sync.py` exists, run its worktree check before completion.
- Create one atomic commit unless the user explicitly says not to.

## Integration Agent

- Merge workers from separate branches or worktrees with `--no-commit`.
- Read all new run reports and update affected shared project memory.
- Update `reports/DEV_REPORT.md` and `prompts/DISCUSSION_AI.md` as the single shared-state writer.
- New or resumed discussion sessions may receive a concise integrated-result summary from SessionStart; continuously running windows need an explicit refresh.
- Treat integration as temporary. Safe sequential task approval includes normal integration authority; parallel_batch and high_risk integration require explicit user confirmation.
- Use an authorized background task only when the platform supports it. Otherwise switch the main agent explicitly or give one launch command; never claim unsupported background execution.
- Hooks expose ready, waiting, and blocked reports but do not choose parallelism, start agents, merge code, write semantic memory, or replace human review.

## Good Task Spec

Every task file must include:

- intent
- current state
- anchored files, symbols, APIs, commands, routes, or tests
- implementation notes
- "Do Not Do" boundaries
- validation commands and manual checks
- external memory updates
- rollback boundary
- execution report requirements

Do not include long chat transcripts or full implementation code unless the code is itself the product rule.

## Debugging

Trace bugs as:

```text
Error -> State -> Code -> Spec
```

Find the earliest polluted assumption, state transition, cache, persisted field, or spec ambiguity before patching.
