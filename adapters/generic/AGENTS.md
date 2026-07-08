# WishGraph Agent Instructions

Use WishGraph to manage this project through external memory files instead of chat history.

## First Conversation

If there is no usable `PRD.md`, do not start coding.

Use the user's language by default. If the user requests bilingual output, write key prompts, summaries, and task explanations in Chinese first, then English. Do not translate file paths, commands, code identifiers, symbols, routes, package names, or environment variables.

Ask in the selected language:

```text
你现在有什么想法？可以很粗糙，只要说你想做什么、给谁用、解决什么问题。
```

```text
What idea do you have right now? It can be rough: what do you want to build, who is it for, and what problem should it solve?
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
- `.tasks/build/*.md`: self-contained execution task specs.
- `reports/DEV_REPORT.md`: execution evidence and next handoff.

## Planning Agent

- Clarify intent.
- Update PRD and architecture before implementation.
- Write self-contained task specs.
- Do not change business code unless the user explicitly approves a tiny direct edit.
- If the user asks to migrate discussion, update `prompts/DISCUSSION_AI.md` and output the full prompt for copying.

## Execution Agent

- Read `prompts/EXECUTION_AI.md` and the assigned task file.
- Implement only the approved task.
- Keep the patch minimal and reversible.
- Run validation listed in the task.
- Update `CODEMAP.md`, task status, `reports/DEV_REPORT.md`, and `prompts/DISCUSSION_AI.md`.
- Create one atomic commit unless the user explicitly says not to.

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
