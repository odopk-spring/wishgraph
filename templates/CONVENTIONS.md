# CONVENTIONS

This file defines how humans and AI agents collaborate in this repository.

## Roles

### Planning Agent

The planning agent turns human intent into durable task specs.

Responsibilities:

- Start from `prompts/DISCUSSION_AI.md` when opening a fresh planning window.
- Read project docs before asking questions.
- Establish or update `PRD.md` before asking an execution agent to restructure architecture or implement feature work.
- For a new or vague project, start with one question about the user's idea and grill one decision at a time before writing implementation tasks.
- Ask only for decisions that materially change scope.
- Write self-contained task specs in the visible `tasks/build/` directory. Preserve `.tasks/build/` only for an existing project that already uses it.
- Classify work as discussion, sequential, parallel_batch, or high_risk before creating workers. Recommend the execution shape; the project owner confirms it.
- Check task dependencies, file and core-module overlap, independent validation and rollback, cross-task contamination, and unresolved product or architecture decisions before recommending parallel work.
- Do not change business code unless the project owner explicitly approves a trivial direct-edit exception.
- A direct-edit exception may omit a task file, but not validation, a unique run report, or the normal commit boundary.
- Read `reports/PROJECT_STATUS.md` before presenting integrated execution results.
- Maintain the concise dynamic handoff in `prompts/DISCUSSION_AI.md` during discussion and after human review; do not copy the full Project Status into it.
- After showing the approved task and work classification, ask whether to create the execution window. Only an explicit human command authorizes creation. Then create and configure one user-visible Worker task per authorized spec with `prompts/EXECUTION_AI.md` and the task file already handed off. Use `<task-id> · <short title> · WG Worker` so task identity appears first. Manual copying is only the fallback when the platform cannot create visible tasks. Do not require users to edit memory or integration files.

### Execution Agent

The execution agent implements approved task specs.

Responsibilities:

- Start from `prompts/EXECUTION_AI.md` and the specific task file.
- Treat the task file as the only formal requirement source. For an explicitly approved direct edit, treat the bounded user instruction as the requirement source.
- Keep the patch minimal and scoped.
- Run the validation commands listed in the task.
- Update task status when present and create exactly one new immutable `reports/runs/<work-unit-id>.md`.
- Record `Integrate` or `N/A` proposals for shared memory. Do not edit `PRD.md`, `ARCHITECTURE.md`, `CODEMAP.md`, `CONVENTIONS.md`, `reports/PROJECT_STATUS.md`, or any prompt file.
- Fill the Run Report's versioned `wishgraph:run-state` JSON block for machine lifecycle facts. Keep evidence, risks, and impact reasoning in Markdown.
- Use the versioned task-state lifecycle `draft -> approved -> running -> completed|blocked|incomplete -> integrated -> reviewed`. Discussion records explicit Worker authorization and human review, Workers record execution states, and Integration records `integrated`.
- Create one atomic commit per completed task unless the project owner explicitly says not to commit.
- Never start workers in the background by default.

### Integration Agent

The integration agent is the single writer for shared project state.

It is an event-triggered temporary role, not a permanent window.

Responsibilities:

- Merge worker branches with `--no-commit` or use an equivalent no-commit cherry-pick so new run reports and code remain visible in one integration diff.
- Read every new `reports/runs/*.md` report before resolving conflicts.
- Rewrite `reports/PROJECT_STATUS.md` as the current integrated snapshot, retaining current facts and unresolved items but no integration history.
- Fill its versioned `wishgraph:integration-state` JSON block with the current integration ID, status, kind, authorization, and absorbed Run Reports.
- List only this integration's absorbed run reports in `reports/PROJECT_STATUS.md`; preserve detailed history in immutable run reports and Git.
- After the Project Status is complete, refresh the concise dynamic state in `prompts/DISCUSSION_AI.md`.
- Run integration validation and create the integration commit.
- For a safe sequential result, use the integration authority inherited when the task was approved; do not ask twice.
- For parallel_batch or high_risk work, require explicit user approval naming the reports to integrate.
- Use a platform background task or independent thread only when that capability exists and authorization permits it. Otherwise switch the current main agent explicitly or provide a one-time launch instruction; never claim fictitious background execution.
- Return integration status and results to discussion AI, then end the temporary role.

## Task File Rules

- Path: `tasks/build/NNN-short-slug.md`.
- Use a stable task number. For follow-ups in the same feature line, use a suffix such as `003b` or `014c`.
- A task must be executable without chat history.
- Anchor by symbols, modules, routes, APIs, or tests. Do not rely on line numbers.
- Include a "Do Not Do" section to stop scope drift.
- Record Work type, Batch ID, Integration authorization, and the unique Run report path.

## Launch Prompt Files

- `prompts/DISCUSSION_AI.md` is concise mutable discussion state. Discussion AI maintains it during planning and after human review; Integration AI refreshes it after absorbing Worker reports.
- `prompts/EXECUTION_AI.md` is stable. It tells an execution agent how to start, what files to read, and how to verify. Do not pack task-specific requirements into it; those belong in `tasks/build/*.md`.
- Users should be able to paste either prompt into any agent interface and get a coherent continuation without relying on previous chat context.
- Keep project memory in the language chosen by the user. If bilingual output is requested, write key user-facing explanations in Chinese first, then English. Do not translate file paths, commands, code identifiers, symbols, routes, package names, or environment variables.
- If the user asks to migrate or continue the discussion in another window, update `prompts/DISCUSSION_AI.md` and output its full content for copying.

## External Memory Update Rule

Worker agents propose shared-memory impact in their own immutable run report. Integration agents apply those proposals and update shared project truth.

- Update `PRD.md` when product goals, scope, roadmap, user-visible behavior, accepted tradeoffs, or current progress changes.
- Update `ARCHITECTURE.md` when dependencies, module ownership, service boundaries, data flow, or framework choices change.
- Update `CODEMAP.md` when feature status, file locations, public contracts, runtime probes, or validation surfaces change.
- Update the dynamic handoff state in `prompts/DISCUSSION_AI.md` after integrating one or more completed execution units so a new or resumed planning window can receive the result.
- Update `tasks/build/*.md` in the worker branch when a task file exists.
- Add one `reports/runs/<work-unit-id>.md` file after every formal or ad-hoc worker execution. Never overwrite an earlier run report.
- Rewrite `reports/PROJECT_STATUS.md` only during integration. It is the current snapshot, not an append-only log.
- If an agent cannot update a required file, it must report the exact text that should be added.

## Memory Sync Hooks

- Project-local hooks may enforce this closeout through `.wishgraph/config.json`, `.codex/hooks.json`, and `.claude/settings.json`.
- Hooks inspect and block; they do not invent semantic PRD, architecture, CODEMAP, or handoff content.
- Before completion or commit, run `python3 .wishgraph/hooks/memory_sync.py check --scope worktree` when hooks are installed.
- Worker run reports use `Integrate` or `N/A`. Project Status snapshots use `Updated` or `N/A`.
- Ad-hoc work does not require a task file, but it needs a unique run-report ID.
- New windows are neutral. By default SessionStart performs safety checks only; enter Discussion only after the user explicitly says "Start discussion" or equivalent. Refresh is explicit in an already-running window.
- Hooks may expose pending integration, integration kind, ready, waiting, and blocked reports, confirmation requirement, and a reason. They do not choose parallelism, start agents, merge code, write semantic memory, or replace human review.

## Validation

Every execution task must state:

- Build command.
- Relevant tests.
- Manual checks, if needed.
- Docs or maps that must be updated.
- Known checks that cannot run and why.

## Git

- One completed execution task should produce one atomic commit unless the project owner explicitly says not to commit.
- Parallel workers must use separate branches or worktrees and unique work-unit IDs.
- Discussion AI recommends sequential or parallel work; the project owner makes the final choice.
- Only the integration agent updates shared memory. Do not resolve this rule by letting workers race on the same files.
- Do not stage unrelated user changes.
- Do not rewrite history unless the project owner explicitly asks.
- Keep commit messages understandable to a future reviewer.

## Empty Project Rule

- Do not start coding from a vague idea.
- First turn the idea into `PRD.md`, `ARCHITECTURE.md`, `CODEMAP.md`, and a bounded first task.
- Ask one question at a time and include a recommended default with each question.
- After the first task is approved, ask whether to create the execution window. On explicit authorization, create the user-visible Worker and hand off `prompts/EXECUTION_AI.md` plus the task file; never create it silently or replace it with a hidden subagent.

## Debugging Discipline

For regressions, trace:

```text
Error -> State -> Code -> Spec
```

Do not guess files from memory. Use `CODEMAP.md`, logs, tests, and the task history to find the earliest polluted assumption or state transition.

## Direct-Edit Exception

A planning agent may directly edit only when all are true:

- The change is tiny.
- The risk is low.
- The project owner explicitly accepts direct edit.
- The change does not alter public interfaces, persistent schema, security behavior, billing, data deletion, or architecture boundaries.
- The agent performs the normal validation and external-memory closeout before finishing.
