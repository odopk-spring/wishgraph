---
name: wishgraph
description: Create and maintain a WishGraph project-governance system for AI-assisted software work, with Chinese, English, or bilingual project prompts. Use when Codex needs to start a project from a vague idea, grill the user into a usable PRD, create auditable specs, task files, code maps, architecture constraints, validation gates, causal debugging notes, execution reports, cross-session handoff documents, or low-friction cross-platform Skill and hook setup from natural-language choices; especially useful for first-time project bootstrap, multi-agent collaboration, long-running repositories, discussion-window migration, bug triage that must trace Error to State to Code to Spec, and projects that need externalized memory instead of relying on chat context.
---

# WishGraph

## Overview

Use this skill to turn a repository into a WishGraph: a file-backed system where human intent is compiled into specs, tasks, code changes, validation evidence, and review reports. Keep the agent work auditable, scoped, and recoverable across sessions.

WishGraph is not autonomous magic. It is a governance layer that makes AI collaboration legible: what the user wants, what the agent plans to change, why those files are in scope, how the work will be verified, and what state future agents must read before continuing.

## Explicit Window Roles

Treat every newly opened window as neutral until the user names its role. `SessionStart` performs safety checks only by default and must not silently activate Discussion AI or inject the full discussion prompt.

- When the user says "开始讨论", "开启讨论", "继续讨论", "start discussion", or an equivalent phrase, enter Discussion mode in that same visible window. Read `prompts/DISCUSSION_AI.md`, `reports/PROJECT_STATUS.md`, and the read-only WishGraph status before responding with the current focus and recommended next action.
- When the user says "刷新项目状态", "刷新 WishGraph 项目状态", "refresh project state", or equivalent, refresh those sources without requiring a new window.
- Do not treat unrelated natural-language conversation as permission to activate a role.
- Hosts that cannot route these phrases automatically should execute the same read sequence in the current visible window. Hooks only check and expose state; they never start hidden agents.

## Task IDs And Natural-Language Routing

Use a structured Task ID matching `^\d{3,}[a-z]*$`. Root tasks are at least three digits (`012`, `1000`). Follow-ups use an unbounded lower-case Excel-style suffix (`012a` through `012z`, then `012aa`); the suffix is a sequence, not hierarchy. Record hierarchy in `parent_task_id` and ordering in `dependencies`. Keep the readable slug only in the filename, for example `tasks/build/012a-refresh-cache.md`; resolve commands against the JSON `task_id` exactly.

Recognize compact or explicit natural-language actions such as `执行012b`, `执行012b号任务`, `继续执行012号任务`, `查看012号任务`, `观察012号任务`, `停止012号任务`, `重新执行012号任务`, `接管012号任务`, and `查看012系列任务`. Inspect and observe are read-only. Execute is explicit Worker authority, but it must still pass Task completeness, dependency, status, Claim, and worktree checks. Never let `012` select `012a`, or `012b` select `012ba`, and report duplicate IDs or a missing exact match instead of guessing from a filename.

Retries after `blocked` or `incomplete` retain the same Task ID, increment `attempt`, and allocate a new immutable path such as `reports/runs/012-attempt-2.md`. Follow-up IDs are for new goals, never attempts. Task IDs are never reused; an approved Task Spec filename is immutable.

## Worker Claims And Worktrees

Before formal execution, run the execution preflight and atomically acquire a Worker Claim. Claims live under the repository's Git common directory so every local worktree sees the same runtime lock; they are not committed as business files. Bind each Claim to one Task attempt, worker, branch, and absolute worktree. Default `execution_mode: exclusive` permits only one active Claim for a Task. `competitive` is allowed only after explicit user choice and still requires a distinct worktree per candidate.

Use the project runtime for `claim acquire`, `inspect`, `heartbeat`, `release`, and explicit `revoke`. A Worker must heartbeat and must not continue after a branch or worktree mismatch. Treat an expired heartbeat as stale evidence, not permission to overwrite it silently: preserve the old attempt, revoke after user authority or proven abandonment, and acquire a new Claim and Run Report. When an active exclusive Claim exists, offer observation, continuing the original Worker, stop-and-retry, explicit takeover, or competitive execution; never silently create a second Worker.

This filesystem Claim is atomic across processes and worktrees sharing one local Git common directory. It does not guarantee mutual exclusion between different machines that only share a remote; document that boundary and use host coordination or another distributed lock when multi-machine execution is required.

## Micro Changes, Stop, And Competitive Execution

Allow `change_class: micro` without a Task Spec only when the goal and scope are explicit, validation exists, one atomic commit can fully roll it back, and all API, schema, persistence, security, permission, billing, deletion, migration, dependency, and cross-module-contract flags are false. It still needs a unique ad-hoc ID, `changed_paths`, one immutable Run Report, Integrate/N/A decisions, and normal integration. Any risk flag promotes the request to a formal Task. A micro change unrelated to the active Task is a separate work unit and commit, never a side edit hidden in the formal report.

On stop, preserve the branch, worktree, Claim, and report evidence long enough to close safely. Before integration, a rejected or abandoned attempt can be released/revoked and retried under the same Task ID with an incremented attempt and new report. After integration, never erase history; create a replacement or rollback follow-up Task. `revoke` requires explicit user authority.

When the user explicitly requests multiple Agents to solve the same goal and compare them, create candidate follow-ups (`012a`, `012b`) with `parent_task_id: 012`, `execution_mode: competitive`, and `comparison_group: 012`. Each gets its own Claim, branch/worktree, and report. Integrate exactly one winner. A complete objective scorecard may select a unique winner automatically; ties or product/architecture preferences return a compressed comparison and recommendation to Discussion. Mark losing candidates `rejected` or `superseded`, preserve their evidence, and release their Claims.

## Natural-Language Installation

When the user asks to install, configure, enable, or set up WishGraph, read `references/installation.md` and translate their words into one of these outcomes:

- Skill only: phrases such as "只安装 Skill", "先不要 Hooks", or "Skill only".
- Safe setup, recommended: phrases such as "帮我配置好", "默认安装", "安全模式", or "set it up for me". Install current-host project hooks in `warn` mode.
- Strict setup: phrases such as "严格模式", "强制同步", "不要允许漏记忆", or "strict enforcement". Install `enforce` mode plus the Git pre-commit fallback.

Do not merely list these outcomes. Inspect the current context and proactively recommend one with a short reason and rough WishGraph-only cost. Recommend safe setup for a first project, Skill only when there is no current project or the user is only evaluating WishGraph, and strict setup only after the repository is clean and has completed a successful safe-mode closeout. If the user already made a clear choice, do not reconfirm it. Otherwise ask exactly one short question in the user's language and put the recommendation first. Accept natural replies such as "按推荐来", "先只装", or "直接严格模式".

Guide setup as a four-stage conversation: choice, prerequisites, installation, verification. State the current stage briefly, continue through all safe local steps without asking again, and pause only for missing system dependencies, permission to initialize Git, a required restart, or another external action. At a pause, explain what is missing, why it is needed, rough disk and time cost, the recommended next action, and the exact short reply that will resume setup. Re-check and continue from that stage when the user returns.

Do not ask the user to choose a host, operating system, path, hook event, or command-line flag when those can be detected.

Before writing installation files, check the operating system, active host, Git, Python 3.9 or newer, and the Git repository root. Do not install system dependencies without explicit approval. When one is missing, stop before configuration, give the platform-appropriate command or official download route, state the rough disk and time estimate from `references/installation.md`, and re-check after the user installs it.

After setup, verify the installed mode and host files, run the memory checker once, and report only what was selected, what was installed, whether a restart or Codex `/hooks` review is needed, and any unresolved prerequisite. Keep advanced flags hidden unless the user asks.

## Quick Start

When the user asks to "set up WishGraph", "make this project AI-agent friendly", "create an AI collaboration system", "start a project from scratch", or "make future agents understand this repo":

1. Inspect the target repository before writing files.
2. Detect the user's preferred language. Use that language by default; if the user asks for bilingual output, write key user-facing prompts and summaries in Chinese first, then English.
3. If the project has no usable PRD, enter zero-project bootstrap mode and ask the first intake prompt in the selected language:
   - Chinese: "先不用写完整 PRD。请用几句话告诉我：1. 你想做一个什么项目？2. 最先服务谁？3. 他们第一次打开时最应该完成什么动作？4. 你会用什么结果判断 v0 做对了？如果还不确定，可以只回答第 1 点，我会继续一问一问补齐。"
   - English: "You do not need a full PRD yet. In a few sentences, tell me: 1. What are you trying to build? 2. Who should it serve first? 3. What should they be able to do on the first successful use? 4. What result would make you say v0 is working? If you are not sure, answer only item 1 and I will fill the rest one decision at a time."
   - Bilingual: ask both lines together.
4. Grill the idea one decision at a time until it can become a PRD.
5. Reuse existing docs if they already serve the same purpose.
6. Create only the minimum governance files needed for the project:
   - `PRD.md`
   - `CODEMAP.md`
   - `CONVENTIONS.md`
   - `ARCHITECTURE.md`
   - `prompts/DISCUSSION_AI.md`
   - `prompts/EXECUTION_AI.md`
   - `prompts/INTEGRATION_AI.md`
   - `tasks/build/001-bootstrap-project.md` or the first implementation task
   - `reports/PROJECT_STATUS.md`
   - `reports/RUN_REPORT.md`
7. Use the bundled templates under `assets/templates/` as structure, then adapt them to the repository. For Chinese-first projects, use `assets/templates/zh-CN/` as the source template set. For bilingual projects, start from the user's primary language template and add bilingual user-facing explanations only where useful.
8. For Skill or hook installation, follow **Natural-Language Installation** and `references/installation.md`. Adapt the required governance files before enabling strict mode, preserve unrelated hook configuration, and tell Codex users to review `/hooks`.
9. When the PRD and first task are ready, classify the work, explain the sequential or parallel recommendation, name the approved tasks, and ask whether the user wants the execution window or windows created. Only after an explicit command, create one user-visible Worker task per authorized spec, inject `prompts/EXECUTION_AI.md` plus the named `tasks/build/*.md`, and apply the naming and fallback rules in `references/worker-window-launch.md`. Tell the user to return to discussion after workers finish; do not require them to copy prompts by default or edit memory files.
10. Finish with a short review summary listing files created or updated, assumptions, hook mode when installed, and next recommended task.

## Workflow

1. **Ground the repository**
   - Read existing docs first: `README`, architecture notes, task folders, tests, CI files, package manifests, and code ownership hints.
   - Identify what already acts as Spec Graph, Dependency Map, Causal Log, Probe, and review report.
   - Do not invent governance files before checking whether equivalents already exist.

2. **Compile intent**
   - Restate the user's wish as observable behavior and acceptance criteria.
   - Separate product intent from implementation guesses.
   - Ask only for decisions that cannot be derived from the repo and would materially change scope.
   - For new projects or vague ideas, use grill-first intake: ask one question at a time, provide a recommended default, and keep drilling until target user, core workflow, first slice, non-goals, validation, and risks are explicit.

3. **Produce or update the governance skeleton**
   - Use the repository's native structure if it exists.
   - If missing, create the minimum useful set:
     - `PRD.md` for product goals, scope, roadmap, current decisions, and current progress.
     - `CODEMAP.md` for feature-to-file lookup and current status.
     - `CONVENTIONS.md` for collaboration roles, task rules, verification, and git discipline.
     - `ARCHITECTURE.md` for dependency boundaries and ownership.
     - `prompts/DISCUSSION_AI.md` as the mutable launch prompt for planning or discussion agents.
     - `prompts/EXECUTION_AI.md` as the stable launch prompt for execution agents.
     - `prompts/INTEGRATION_AI.md` as the stable launch prompt for the shared-state integration agent.
     - `tasks/build/NNN-short-slug.md` for visible, self-contained execution specs.
     - `reports/PROJECT_STATUS.md` for the current integrated project snapshot.
     - `reports/RUN_REPORT.md` as the template for immutable worker reports under `reports/runs/`.
   - Use `assets/templates/` as the file-shape source, but remove generic placeholder content that does not fit the target repo.

4. **Write task specs**
   - A task spec must be executable without chat history.
   - Include goal, context summary, anchored files/symbols, implementation instructions, "do not do" boundaries, validation commands, rollback boundary, and required report format.
   - Follow the project's language mode for human-facing explanations. Do not translate file paths, commands, code identifiers, symbols, routes, package names, or environment variables.
   - Prefer small atomic tasks. Split any task whose validation, risk, or rollback boundary is unclear.
   - Fill the versioned `wishgraph:task-state` block with task ID, `draft` status, work type, batch ID, unique Run Report path, `worker_creation_authorized: false`, and the integration policy. Use `requires_explicit_user_confirmation` for parallel or high-risk integration.

5. **Classify work and obtain the right authority**
   - Use `discussion` while requirements or architecture remain unclear; start no worker or integration.
   - Use `sequential` for one task or ordered dependencies. The user explicitly authorizes Worker creation; task approval also authorizes a later safe integration when every gate passes.
   - Use `parallel_batch` only for two or more independently testable and revertible tasks. Show the batch first; the user explicitly authorizes exactly which visible Worker tasks to create. Mark mechanically independent work `parallel_independent`; it may integrate silently only after all expected Workers are terminal and overlap, dependency, interface, risk, merge, and combined-validation gates pass.
   - Use `high_risk` for product or architecture decisions, data migration, conflict, failed validation, unsafe rollback, or scope drift. Return to the user; do not auto-integrate.
   - Check dependencies, shared files or core modules, validation and rollback independence, cross-task contamination, and unresolved decisions. Discussion AI recommends; the user decides. Hooks and integration agents do not choose parallelism.
   - After an explicit Worker-creation command, change only the authorized task-state blocks from `draft` to `approved` and set `worker_creation_authorized: true` before launching Workers.

6. **Separate planning, worker, and integration roles**
   - Planning agents grill the intent and write specs.
   - Worker execution agents use separate branches or worktrees, verify task-state authorization, move `approved -> running -> completed|blocked|incomplete`, implement only the approved spec or bounded ad-hoc instruction, and create one immutable `reports/runs/<work-unit-id>.md`.
   - Workers record `Integrate` or `N/A` proposals and never edit shared project memory.
   - The integration agent merges workers with `--no-commit`, reads every new run report, resolves conflicts, updates affected shared memory, rewrites `reports/PROJECT_STATUS.md`, and then refreshes the concise dynamic state in `prompts/DISCUSSION_AI.md`.
   - Keep `prompts/EXECUTION_AI.md` stable; put task-specific instructions in `tasks/build/*.md`.
   - For trivial one-line changes, allow direct execution only if the repo conventions explicitly permit it.
   - Never start Workers without an explicit human creation command. When the platform supports user-visible task or thread creation, the discussion agent creates and configures those visible tasks; it must not use hidden subagents. Manual prompt copying is only the truthful fallback when visible task creation is unavailable or fails.

7. **Close every execution unit**
   - Formal tasks and approved ad-hoc edits use the same validation and external-memory closeout. Only the task file is optional for ad-hoc work.
   - Create one new immutable run report for every worker execution. Use the task ID or a unique timestamped ad-hoc ID.
   - In new Run Reports, fill the versioned `wishgraph:run-state` JSON block as the lifecycle source for status, work type, authorization, readiness, safety gates, and validation results. Keep summaries, evidence, risks, and shared-memory impact in normal Markdown. Preserve label-based legacy reports when adapting an existing project; do not add a malformed structured block.
   - Record Integrate or N/A with a concrete reason for each managed shared-memory file.
   - When project hooks are installed, run `.wishgraph/hooks/memory_sync.py check` before claiming completion. Hooks inspect and block; they do not invent semantic memory content.

8. **Integrate worker results**
   - Keep shared memory single-writer. Do not let workers race on PRD, architecture, CODEMAP, prompts, or Project Status.
   - Merge or cherry-pick worker commits without committing, so their new run reports remain visible in the integration diff.
   - Read the old `reports/PROJECT_STATUS.md`, preserve current facts and unresolved items, absorb this integration's Run Reports, and rewrite the complete snapshot. Never append integration history; list only reports absorbed this time and leave detail in `reports/runs/*.md` and Git.
   - Fill the versioned `wishgraph:integration-state` JSON block with the integration ID, status, kind, authorization, and exactly the Run Reports absorbed this time. Treat the block as workflow truth and the surrounding Markdown as the human review view.
   - Move each absorbed structured task from `completed` to `integrated`. After the human accepts the result, discussion moves only that task-state block from `integrated` to `reviewed`.
   - Keep Project Status within configured line and character limits without deleting unresolved risks, conflicts, or pending decisions.
   - After Project Status is complete, update only the concise dynamic state block in `prompts/DISCUSSION_AI.md`: latest integration ID, discussion focus, result to present, pending decisions, next action, and the Project Status pointer. Discussion AI maintains this block during planning and after human review; Workers never edit it.
   - Run `.wishgraph/hooks/memory_sync.py status` when available and show ready, waiting, and blocked reports plus pending integration and the next action.
   - For one safe sequential result, use the authority inherited from task approval without asking twice. Require Completed and ready metadata, passing prescribed validation, bounded scope, no conflict or new product/architecture/data decision, and a safe target worktree.
   - For high-risk, conflicting, blocked, competitive, or mechanically ambiguous results, return to Discussion and request the required decision. Do not ask again for safe sequential or proven `parallel_independent` integration.
   - Treat integration as a temporary event task. If the platform exposes an authorized background-task or independent-thread tool, launch a temporary integration agent with `prompts/INTEGRATION_AI.md`, report Waiting/Running/Blocked/Completed, return the result, and end it. Otherwise explicitly switch the current main agent or give one natural-language launch instruction; never pretend background execution exists.
   - Do not describe this as real-time push. An already-running discussion window receives results only after a supported resume/start event or an explicit refresh.

9. **Handle discussion-window migration**
   - If the user says they want to migrate, hand off, continue in another agent, open a new discussion window, or copy the discussion prompt, update `prompts/DISCUSSION_AI.md` first if it is stale.
   - Then output the full current discussion prompt in a fenced code block for direct copying.
   - Do not replace the prompt with a summary unless the user asks for a shorter version.

10. **Debug through causality**
   - For bugs, trace `Error -> State -> Code -> Spec`.
   - Do not start by guessing the most familiar file.
   - Find the earliest polluted assumption, state transition, cache, persisted field, or spec ambiguity.
   - Prefer the minimal patch set that repairs the causal chain without expanding behavior.

## Reference Loading

- Read `references/installation.md` before installing the Skill, configuring project hooks, checking prerequisites, or recovering from installation failures.
- Read `references/core-concepts.md` when the user asks about WishGraph concepts, naming, or public explanation.
- Read `references/bilingual-operation.md` when the user asks for Chinese, English, bilingual output, mixed-language handoff, or language rules for generated project memory.
- Read `references/zero-project-bootstrap.md` when the user is starting from a vague idea, has no PRD, wants the first project conversation, or asks for grill-style project shaping.
- Read `references/worker-window-launch.md` before offering, creating, naming, or falling back from a user-visible Worker task or thread.
- Read `references/task-spec-template.md` before creating or revising task files.
- Read `references/good-execution-spec.md` when creating the first task spec for a project, reviewing whether a task spec is good enough, or showing the user an example.
- Read `references/review-window.md` before producing human-facing review summaries, Project Status snapshots, or single-window status digests.
- When adapting an existing project, if only `reports/DEV_REPORT.md` exists, read it, check Git state, use `git mv` to rename it to `reports/PROJECT_STATUS.md`, and update project references. If both names exist, stop and ask which current facts are authoritative; never maintain both.
- Read `references/debug-causality.md` before triaging bugs, regressions, failed validation, or hidden state corruption.
- Read `references/memory-sync-hooks.md` before installing, configuring, or debugging Codex / Claude Code external-memory hooks.

## Template Mapping

Use bundled templates as starting points, then adapt them to the target repository:

For English or language-neutral projects, use the root files under `assets/templates/`. For Chinese-first projects, use the mirrored files under `assets/templates/zh-CN/` and copy them to the same target paths.

| Skill Asset | Target Path |
|---|---|
| `assets/templates/PRD.md` | `PRD.md` |
| `assets/templates/CODEMAP.md` | `CODEMAP.md` |
| `assets/templates/CONVENTIONS.md` | `CONVENTIONS.md` |
| `assets/templates/ARCHITECTURE.md` | `ARCHITECTURE.md` |
| `assets/templates/DISCUSSION_AI.md` | `prompts/DISCUSSION_AI.md` |
| `assets/templates/EXECUTION_AI.md` | `prompts/EXECUTION_AI.md` |
| `assets/templates/INTEGRATION_AI.md` | `prompts/INTEGRATION_AI.md` |
| `assets/templates/001-bootstrap-project.md` | `tasks/build/001-bootstrap-project.md` when setting up a new project |
| `assets/templates/NNN-task.md` | `tasks/build/001-first-task.md` or the next task number |
| `assets/templates/EXAMPLE-good-task.md` | Optional example for humans and planning agents |
| `assets/templates/PROJECT_STATUS.md` | `reports/PROJECT_STATUS.md` |
| `assets/templates/RUN_REPORT.md` | `reports/RUN_REPORT.md` |

Chinese mirror:

| Skill Asset | Target Path |
|---|---|
| `assets/templates/zh-CN/PRD.md` | `PRD.md` |
| `assets/templates/zh-CN/CODEMAP.md` | `CODEMAP.md` |
| `assets/templates/zh-CN/CONVENTIONS.md` | `CONVENTIONS.md` |
| `assets/templates/zh-CN/ARCHITECTURE.md` | `ARCHITECTURE.md` |
| `assets/templates/zh-CN/prompts/DISCUSSION_AI.md` | `prompts/DISCUSSION_AI.md` |
| `assets/templates/zh-CN/prompts/EXECUTION_AI.md` | `prompts/EXECUTION_AI.md` |
| `assets/templates/zh-CN/prompts/INTEGRATION_AI.md` | `prompts/INTEGRATION_AI.md` |
| `assets/templates/zh-CN/tasks/build/001-bootstrap-project.md` | `tasks/build/001-bootstrap-project.md` |
| `assets/templates/zh-CN/tasks/build/NNN-task.md` | `tasks/build/001-first-task.md` or the next task number |
| `assets/templates/zh-CN/tasks/build/EXAMPLE-good-task.md` | Optional example for humans and planning agents |
| `assets/templates/zh-CN/reports/PROJECT_STATUS.md` | `reports/PROJECT_STATUS.md` |
| `assets/templates/zh-CN/reports/RUN_REPORT.md` | `reports/RUN_REPORT.md` |

## Output Rules

- Keep governance changes close to the current project; do not impose source-project-specific domain rules unless the target project explicitly asks for them.
- Do not include the creator's personal content, social media drafts, or private case-study language when adapting a user's project.
- Treat project files as external memory. Update them when the state changes.
- Do not force meaningless memory-file edits. Require an explicit N/A reason when a managed file did not need a change.
- Do not let an ad-hoc edit bypass validation, a unique run report, or memory-impact review merely because it has no task file.
- Do not let worker agents update shared memory. Integrate their reports through a single integration writer.
- Do not let hooks choose parallelism, launch agents, merge code, write semantic project memory, or replace human review.
- Do not integrate parallel results unless existing Worker authority and every `parallel_independent` mechanical gate are proven; otherwise return to Discussion.
- For a brand-new project, do not start implementation until the PRD is concrete enough to write a bounded first task.
- For discussion migration requests, show the copyable prompt itself, not only a description of where it lives.
- Make scope boundaries explicit. Every task should say what it will not do.
- Include validation evidence. If a command cannot run, say why and record the residual risk.
- Never claim full autonomy. WishGraph keeps AI work inspectable; the human remains the final evaluator.
