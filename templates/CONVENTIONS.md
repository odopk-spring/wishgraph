# CONVENTIONS

This file defines how humans and AI agents collaborate in this repository.

## Roles

### Discussion Role

The planning agent turns human intent into durable task specs.

Responsibilities:

- Enter this role only after the project is enabled and the user separately says "Start discussion"; first-time activation leaves the window neutral.
- Start from `prompts/DISCUSSION_AI.md` when opening a fresh planning window.
- Read project docs before asking questions.
- Establish or update `PRD.md` before authorizing a Worker to restructure architecture or implement feature work.
- For a new or vague project, start with one question about the user's idea and grill one decision at a time before writing implementation tasks.
- Ask only for decisions that materially change scope.
- Write self-contained task specs in the visible `tasks/build/` directory. Preserve `.tasks/build/` only for an existing project that already uses it.
- Classify work as discussion, sequential, parallel_batch, or high_risk before creating workers. Recommend the execution shape; the project owner confirms it.
- Check task dependencies, file and core-module overlap, independent validation and rollback, cross-task contamination, and unresolved product or architecture decisions before recommending parallel work.
- Never change business code, install dependencies, run builds or implementation tests, or validate a Task in Discussion. Those operations require an independent Worker with a bound Claim.
- A request to edit directly in the current window does not override this role boundary.
- Read `reports/PROJECT_STATUS.md` before presenting integrated execution results.
- Maintain the concise dynamic handoff in `prompts/DISCUSSION_AI.md` during discussion and after human review; do not copy the full Project Status into it.
- Move a ready Task to `awaiting_worker_authorization` with one `approve_worker_launch(<task-id>)` expected transition. Recommend model and effort per Task from user constraints, task complexity, risk, and known availability; never hard-code one universal profile. Persist grounded recommendations in `worker_execution_profiles`, show the current-host recommendation before asking, and leave missing hosts on their actual defaults. A short affirmative reply uses that recommendation only when the transition is unique; an exact execution command may override it. Then enter `routing_worker`: Codex prefers a native inspectable `wishgraph-worker` thread; Claude Code prefers its managed background Worker; unknown hosts and failed creation enter `waiting_for_user_launch` and use the Host Adapter's cross-host copy-ready handoff.

### Worker Role

The Worker implements approved Task Specs.

Responsibilities:

- Start from `prompts/EXECUTION_AI.md` and the specific task file.
- Treat the Task file as the only formal requirement source.
- Keep the patch minimal and scoped.
- Run the validation commands listed in the task.
- Update task status when present and create exactly one new immutable `reports/runs/<work-unit-id>.md`.
- Record `Integrate` or `N/A` proposals for shared memory. Do not edit `PRD.md`, `ARCHITECTURE.md`, `CODEMAP.md`, `CONVENTIONS.md`, `reports/PROJECT_STATUS.md`, or any prompt file.
- Fill the Run Report's versioned `wishgraph:run-state` JSON block for machine lifecycle facts. Keep evidence, risks, and impact reasoning in Markdown.
- Use the versioned task-state lifecycle `draft -> approved -> running -> completed|blocked|incomplete -> integrated -> reviewed`. Discussion records explicit Worker authorization and human review, Workers record execution states, and Integration records `integrated`.
- Create one atomic commit per completed task unless the project owner explicitly says not to commit.
- Never create an unauthorized or hidden background Worker. A managed background Agent is allowed only when it is user-visible, inspectable, controllable, bound to a real thread/session ID, and follows the same Claim and closeout gates.

### Discussion-Local Integration Phase

Integration is an event-triggered temporary phase inside the active Discussion window. It is not a separate role or user-visible window. It is the single writer for shared project state.

Responsibilities:

- Merge worker branches with `--no-commit` or use an equivalent no-commit cherry-pick so new run reports and code remain visible in one integration diff.
- Read every new `reports/runs/*.md` report before resolving conflicts.
- Rewrite `reports/PROJECT_STATUS.md` as the current integrated snapshot, retaining current facts and unresolved items but no integration history.
- Fill its versioned `wishgraph:integration-state` JSON block with the current integration ID, status, kind, authorization, and absorbed Run Reports.
- List only this integration's absorbed run reports in `reports/PROJECT_STATUS.md`; preserve detailed history in immutable run reports and Git.
- After the Project Status is complete, refresh the concise dynamic state in `prompts/DISCUSSION_AI.md`.
- Run integration validation and create the integration commit.
- For a safe sequential result, use the integration authority inherited when the task was approved; do not ask twice.
- Under the existing Task approval, let the original Discussion auto-integrate safe sequential and mechanically proven `parallel_independent` results; this grants the Worker no Integration authority. Return high-risk, conflicting, blocked, competitive, or ambiguous results to Discussion.
- Before merging, acquire an exclusive Integration lease bound to the Discussion session, base branch, worktree, selected Task IDs, and Run Reports.
- Every Worker terminal event enters `integration_pending`. Safe evidence enters `integrating` automatically; material risk enters `decision_required`; missing evidence becomes blocked or incomplete.
- Never ask whether to start integration. Ask only a concrete material decision when one is required.
- After the integration commit, release the lease and enter `presenting_result` in the same Discussion window.

## Task File Rules

- Path: `tasks/build/NNN-short-slug.md`.
- The structured Task ID matches `^\d{3,}[a-z]*$`. Use digits for roots and an unbounded Excel-style lower-case suffix for new follow-up goals (`012z`, then `012aa`). The filename slug is descriptive only.
- Record relationships with `parent_task_id` and `dependencies`. Never infer hierarchy from suffix length.
- Never reuse an allocated ID. After approval, neither the Task ID nor Task Spec filename may change.
- Retries keep the Task ID, increment `attempt`, and use a new immutable `reports/runs/<task-id>-attempt-N.md` path.
- Formal execution atomically acquires a Worker Claim stored under the Git common directory. Bind it to the Task attempt, Worker, branch, and absolute worktree; heartbeat it and verify the binding before continuing.
- `exclusive` is the default execution mode. A second Worker requires explicit takeover or competitive authority and a separate worktree. Claims coordinate local worktrees sharing one Git common directory, not separate machines.
- Competitive candidates use child IDs, one comparison group, separate Claims/worktrees/reports, and exactly one integrated winner. Preserve and mark losing evidence `rejected` or `superseded`.
- A task must be executable without chat history.
- Anchor by symbols, modules, routes, APIs, or tests. Do not rely on line numbers.
- Include a "Do Not Do" section to stop scope drift.
- Record Work type, Batch ID, Integration authorization, and the unique Run report path.

## Launch Prompt Files

- `prompts/DISCUSSION_AI.md` is concise mutable discussion state. Discussion maintains it during planning and after human review; Discussion-local Integration refreshes it after absorbing Worker reports.
- `prompts/EXECUTION_AI.md` is stable. It tells a Worker how to start, what files to read, and how to verify. Do not pack task-specific requirements into it; those belong in `tasks/build/*.md`.
- A new supported Agent window should continue from project files after `Start discussion`; users should not need to copy a full prompt or previous chat.
- Keep project memory in the language chosen by the user. If bilingual output is requested, write key user-facing explanations in Chinese first, then English. Do not translate file paths, commands, code identifiers, symbols, routes, package names, or environment variables.
- Before another window continues, keep the concise state in `prompts/DISCUSSION_AI.md` current. The new window uses `Start discussion`; an active Discussion uses `Refresh project status`.

## Orchestration State

- Session Role: `neutral`, `discussion`, or `worker`. Integration is not a role.
- Task Lifecycle: `draft`, `approved`, `running`, `completed`, `blocked`, `incomplete`, `integrated`, `reviewed`.
- Flow Phase: `planning`, `awaiting_worker_authorization`, `routing_worker`, `waiting_for_user_launch`, `waiting_for_worker`, `integration_pending`, `integrating`, `decision_required`, `presenting_result`.
- `expected_transition` is absent or one structured transition. Contextual approvals cannot act when it is missing or ambiguous.
- `reduce(current_state, user_event, host_capability)` produces the unique `FlowPlan`; prompts and Host Adapters cannot override it.

## External Memory Update Rule

Workers propose shared-memory impact in their immutable Run Reports. The original Discussion performs the temporary Integration phase, applies accepted proposals, and updates shared project truth. A Worker cannot promote itself into Discussion or Integration.

- Update `PRD.md` when product goals, scope, roadmap, user-visible behavior, accepted tradeoffs, or current progress changes.
- Update `ARCHITECTURE.md` when dependencies, module ownership, service boundaries, data flow, or framework choices change.
- Update `CODEMAP.md` when feature status, file locations, public contracts, runtime probes, or validation surfaces change.
- Update the dynamic handoff state in `prompts/DISCUSSION_AI.md` after integrating one or more completed execution units so a new or resumed planning window can receive the result.
- Update `tasks/build/*.md` in the worker branch when a task file exists.
- Add one `reports/runs/<work-unit-id>.md` file after every formal or ad-hoc worker execution. Never overwrite an earlier run report.
- Rewrite `reports/PROJECT_STATUS.md` only during integration. It is the current snapshot, not an append-only log.
- If an agent cannot update a required file, it must report the exact text that should be added.

## Memory Sync Hooks

- Hooks may be installed globally or project-locally, but only `.wishgraph/config.json` explicitly activates this project. They enforce closeout and authority gates without overwriting unrelated host settings.
- Hooks inspect and block; they do not invent semantic PRD, architecture, CODEMAP, or handoff content.
- Before completion or commit, run `python3 .wishgraph/hooks/memory_sync.py check --scope worktree` when hooks are installed.
- Worker run reports use `Integrate` or `N/A`. Project Status snapshots use `Updated` or `N/A`.
- Runtime session state, Worker Claims, and Integration leases live under the Git common directory rather than in business files.
- Global Skill installation does not activate this project. `.wishgraph/config.json` with `mode: warn` or `mode: enforce` records explicit project opt-in; missing config or `mode: off` leaves generic entry phrases inactive.
- New windows in an enabled project are neutral. By default SessionStart performs safety checks only; enter Discussion only after the user explicitly says "Start discussion" or equivalent. First-time activation never enters Discussion in the same step. Refresh is explicit in an already-running window.
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
- Only the Discussion-local Integration lease holder updates shared memory. Do not resolve this rule by letting Workers race on the same files.
- Do not stage unrelated user changes.
- Do not rewrite history unless the project owner explicitly asks.
- Keep commit messages understandable to a future reviewer.

## Empty Project Rule

- Do not start coding from a vague idea.
- First turn the idea into `PRD.md`, `ARCHITECTURE.md`, `CODEMAP.md`, and a bounded first task.
- Ask one question at a time and include a recommended default with each question.
- After the first Task is ready, establish its unique expected transition. On authorization, route the independent Worker; never replace it with Discussion implementation or a hidden subagent.

## Debugging Discipline

For regressions, trace:

```text
Error -> State -> Code -> Spec
```

Do not guess files from memory. Use `CODEMAP.md`, logs, tests, and the task history to find the earliest polluted assumption or state transition.

## No Discussion Direct-Edit Path

Discussion never performs Worker implementation. Business-file writes and implementation validation require a Worker Claim. Merge/conflict-resolution writes, combined validation, shared-state updates, and integration commits require a Discussion-local Integration lease. Write/build gating is required; read gating remains host-capability dependent and must not be overstated.
