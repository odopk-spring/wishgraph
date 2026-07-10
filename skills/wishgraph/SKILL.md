---
name: wishgraph
description: Create and maintain a WishGraph project-governance system for AI-assisted software work, with Chinese, English, or bilingual project prompts. Use when Codex needs to start a project from a vague idea, grill the user into a usable PRD, create auditable specs, task files, code maps, architecture constraints, validation gates, causal debugging notes, execution reports, cross-session handoff documents, or low-friction cross-platform Skill and hook setup from natural-language choices; especially useful for first-time project bootstrap, multi-agent collaboration, long-running repositories, discussion-window migration, bug triage that must trace Error to State to Code to Spec, and projects that need externalized memory instead of relying on chat context.
---

# WishGraph

## Overview

Use this skill to turn a repository into a WishGraph: a file-backed system where human intent is compiled into specs, tasks, code changes, validation evidence, and review reports. Keep the agent work auditable, scoped, and recoverable across sessions.

WishGraph is not autonomous magic. It is a governance layer that makes AI collaboration legible: what the user wants, what the agent plans to change, why those files are in scope, how the work will be verified, and what state future agents must read before continuing.

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
   - `.tasks/build/001-bootstrap-project.md` or the first implementation task
   - `reports/DEV_REPORT.md`
   - `reports/RUN_REPORT.md`
7. Use the bundled templates under `assets/templates/` as structure, then adapt them to the repository. For Chinese-first projects, use `assets/templates/zh-CN/` as the source template set. For bilingual projects, start from the user's primary language template and add bilingual user-facing explanations only where useful.
8. For Skill or hook installation, follow **Natural-Language Installation** and `references/installation.md`. Adapt the required governance files before enabling strict mode, preserve unrelated hook configuration, and tell Codex users to review `/hooks`.
9. When the PRD and first task are ready, tell the user to open a new execution window and copy `prompts/EXECUTION_AI.md` plus the chosen `.tasks/build/*.md`.
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
     - `.tasks/build/NNN-short-slug.md` for self-contained execution specs.
     - `reports/DEV_REPORT.md` for the latest integrated project overview.
     - `reports/RUN_REPORT.md` as the template for immutable worker reports under `reports/runs/`.
   - Use `assets/templates/` as the file-shape source, but remove generic placeholder content that does not fit the target repo.

4. **Write task specs**
   - A task spec must be executable without chat history.
   - Include goal, context summary, anchored files/symbols, implementation instructions, "do not do" boundaries, validation commands, rollback boundary, and required report format.
   - Follow the project's language mode for human-facing explanations. Do not translate file paths, commands, code identifiers, symbols, routes, package names, or environment variables.
   - Prefer small atomic tasks. Split any task whose validation, risk, or rollback boundary is unclear.

5. **Separate planning, worker, and integration roles**
   - Planning agents grill the intent and write specs.
   - Worker execution agents use separate branches or worktrees, implement only the approved spec or bounded ad-hoc instruction, update task status, and create one immutable `reports/runs/<work-unit-id>.md`.
   - Workers record `Integrate` or `N/A` proposals and never edit shared project memory.
   - The integration agent merges workers with `--no-commit`, reads every new run report, resolves conflicts, updates affected shared memory, updates `reports/DEV_REPORT.md`, and updates the dynamic state in `prompts/DISCUSSION_AI.md`.
   - Keep `prompts/EXECUTION_AI.md` stable; put task-specific instructions in `.tasks/build/*.md`.
   - For trivial one-line changes, allow direct execution only if the repo conventions explicitly permit it.

6. **Close every execution unit**
   - Formal tasks and approved ad-hoc edits use the same validation and external-memory closeout. Only the task file is optional for ad-hoc work.
   - Create one new immutable run report for every worker execution. Use the task ID or a unique timestamped ad-hoc ID.
   - Record Integrate or N/A with a concrete reason for each managed shared-memory file.
   - When project hooks are installed, run `.wishgraph/hooks/memory_sync.py check` before claiming completion. Hooks inspect and block; they do not invent semantic memory content.

7. **Integrate worker results**
   - Keep shared memory single-writer. Do not let workers race on PRD, architecture, CODEMAP, prompts, or the project overview.
   - Merge or cherry-pick worker commits without committing, so their new run reports remain visible in the integration diff.
   - Update `reports/DEV_REPORT.md` with the absorbed run-report paths, latest integrated results, validation, risks, and Updated/N/A rows.
   - Update the dynamic state block in `prompts/DISCUSSION_AI.md`. SessionStart can inject a concise overview and handoff into new or resumed agent sessions.
   - Do not describe this as real-time push. An already-running discussion window receives results only after a supported resume/start event or an explicit refresh.

8. **Handle discussion-window migration**
   - If the user says they want to migrate, hand off, continue in another agent, open a new discussion window, or copy the discussion prompt, update `prompts/DISCUSSION_AI.md` first if it is stale.
   - Then output the full current discussion prompt in a fenced code block for direct copying.
   - Do not replace the prompt with a summary unless the user asks for a shorter version.

9. **Debug through causality**
   - For bugs, trace `Error -> State -> Code -> Spec`.
   - Do not start by guessing the most familiar file.
   - Find the earliest polluted assumption, state transition, cache, persisted field, or spec ambiguity.
   - Prefer the minimal patch set that repairs the causal chain without expanding behavior.

## Reference Loading

- Read `references/installation.md` before installing the Skill, configuring project hooks, checking prerequisites, or recovering from installation failures.
- Read `references/core-concepts.md` when the user asks about WishGraph concepts, naming, or public explanation.
- Read `references/bilingual-operation.md` when the user asks for Chinese, English, bilingual output, mixed-language handoff, or language rules for generated project memory.
- Read `references/zero-project-bootstrap.md` when the user is starting from a vague idea, has no PRD, wants the first project conversation, or asks for grill-style project shaping.
- Read `references/task-spec-template.md` before creating or revising task files.
- Read `references/good-execution-spec.md` when creating the first task spec for a project, reviewing whether a task spec is good enough, or showing the user an example.
- Read `references/review-window.md` before producing human-facing review summaries, Dev Reports, or single-window status digests.
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
| `assets/templates/001-bootstrap-project.md` | `.tasks/build/001-bootstrap-project.md` when setting up a new project |
| `assets/templates/NNN-task.md` | `.tasks/build/001-first-task.md` or the next task number |
| `assets/templates/EXAMPLE-good-task.md` | Optional example for humans and planning agents |
| `assets/templates/DEV_REPORT.md` | `reports/DEV_REPORT.md` |
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
| `assets/templates/zh-CN/.tasks/build/001-bootstrap-project.md` | `.tasks/build/001-bootstrap-project.md` |
| `assets/templates/zh-CN/.tasks/build/NNN-task.md` | `.tasks/build/001-first-task.md` or the next task number |
| `assets/templates/zh-CN/.tasks/build/EXAMPLE-good-task.md` | Optional example for humans and planning agents |
| `assets/templates/zh-CN/reports/DEV_REPORT.md` | `reports/DEV_REPORT.md` |
| `assets/templates/zh-CN/reports/RUN_REPORT.md` | `reports/RUN_REPORT.md` |

## Output Rules

- Keep governance changes close to the current project; do not impose source-project-specific domain rules unless the target project explicitly asks for them.
- Do not include the creator's personal content, social media drafts, or private case-study language when adapting a user's project.
- Treat project files as external memory. Update them when the state changes.
- Do not force meaningless memory-file edits. Require an explicit N/A reason when a managed file did not need a change.
- Do not let an ad-hoc edit bypass validation, a unique run report, or memory-impact review merely because it has no task file.
- Do not let worker agents update shared memory. Integrate their reports through a single integration writer.
- For a brand-new project, do not start implementation until the PRD is concrete enough to write a bounded first task.
- For discussion migration requests, show the copyable prompt itself, not only a description of where it lives.
- Make scope boundaries explicit. Every task should say what it will not do.
- Include validation evidence. If a command cannot run, say why and record the residual risk.
- Never claim full autonomy. WishGraph keeps AI work inspectable; the human remains the final evaluator.
