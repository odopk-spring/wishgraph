# CONVENTIONS

This file defines how humans and AI agents collaborate in this repository.

## Roles

### Planning Agent

The planning agent turns human intent into durable task specs.

Responsibilities:

- Start from `prompts/DISCUSSION_AI.md` when opening a fresh planning window.
- Read project docs before asking questions.
- Ask only for decisions that materially change scope.
- Write self-contained task specs in `.tasks/build/`.
- Do not change business code unless the task is explicitly a trivial direct-edit exception.
- Keep `prompts/DISCUSSION_AI.md` updated when roadmap, progress, status, or handoff rules change.

### Execution Agent

The execution agent implements approved task specs.

Responsibilities:

- Start from `prompts/EXECUTION_AI.md` and the specific task file.
- Treat the task file as the only requirement source.
- Keep the patch minimal and scoped.
- Run the validation commands listed in the task.
- Update `CODEMAP.md`, task status, `reports/DEV_REPORT.md`, and the current progress section of `prompts/DISCUSSION_AI.md`.
- Commit one atomic change when requested by the project owner.

## Task File Rules

- Path: `.tasks/build/NNN-short-slug.md`.
- Use a stable task number. For follow-ups in the same feature line, use a suffix such as `003b` or `014c`.
- A task must be executable without chat history.
- Anchor by symbols, modules, routes, APIs, or tests. Do not rely on line numbers.
- Include a "Do Not Do" section to stop scope drift.

## Launch Prompt Files

- `prompts/DISCUSSION_AI.md` is mutable. It stores the project structure, outline, current progress, open decisions, handoff rules, and task-spec writing rules. Update it after every completed execution task.
- `prompts/EXECUTION_AI.md` is stable. It tells an execution agent how to start, what files to read, and how to verify. Do not pack task-specific requirements into it; those belong in `.tasks/build/*.md`.
- Users should be able to paste either prompt into any agent interface and get a coherent continuation without relying on previous chat context.

## Validation

Every execution task must state:

- Build command.
- Relevant tests.
- Manual checks, if needed.
- Docs or maps that must be updated.
- Known checks that cannot run and why.

## Git

- Prefer one atomic commit per execution task.
- Do not stage unrelated user changes.
- Do not rewrite history unless the project owner explicitly asks.
- Keep commit messages understandable to a future reviewer.

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
