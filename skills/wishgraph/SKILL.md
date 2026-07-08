---
name: wishgraph
description: Create and maintain a WishGraph project-governance system for AI-assisted software work. Use when Codex needs to start a project from a vague idea, grill the user into a usable PRD, create auditable specs, task files, code maps, architecture constraints, validation gates, causal debugging notes, execution reports, or cross-session handoff documents; especially useful for first-time project bootstrap, multi-agent collaboration, long-running repositories, discussion-window migration, bug triage that must trace Error to State to Code to Spec, and projects that need externalized memory instead of relying on chat context.
---

# WishGraph

## Overview

Use this skill to turn a repository into a WishGraph: a file-backed system where human intent is compiled into specs, tasks, code changes, validation evidence, and review reports. Keep the agent work auditable, scoped, and recoverable across sessions.

WishGraph is not autonomous magic. It is a governance layer that makes AI collaboration legible: what the user wants, what the agent plans to change, why those files are in scope, how the work will be verified, and what state future agents must read before continuing.

## Quick Start

When the user asks to "set up WishGraph", "make this project AI-agent friendly", "create an AI collaboration system", "start a project from scratch", or "make future agents understand this repo":

1. Inspect the target repository before writing files.
2. If the project has no usable PRD, enter zero-project bootstrap mode: ask the user "你现在有什么想法？可以很粗糙，只要说你想做什么、给谁用、解决什么问题。" and grill the idea one decision at a time until it can become a PRD.
3. Reuse existing docs if they already serve the same purpose.
4. Create only the minimum governance files needed for the project:
   - `PRD.md`
   - `CODEMAP.md`
   - `CONVENTIONS.md`
   - `ARCHITECTURE.md`
   - `prompts/DISCUSSION_AI.md`
   - `prompts/EXECUTION_AI.md`
   - `.tasks/build/001-bootstrap-project.md` or the first implementation task
   - `reports/DEV_REPORT.md`
5. Use the bundled templates under `assets/templates/` as structure, then adapt them to the repository.
6. When the PRD and first task are ready, tell the user to open a new execution window and copy `prompts/EXECUTION_AI.md` plus the chosen `.tasks/build/*.md`.
7. Finish with a short review summary listing files created or updated, assumptions, and next recommended task.

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
     - `.tasks/build/NNN-short-slug.md` for self-contained execution specs.
     - `reports/DEV_REPORT.md` for execution summaries.
   - Use `assets/templates/` as the file-shape source, but remove generic placeholder content that does not fit the target repo.

4. **Write task specs**
   - A task spec must be executable without chat history.
   - Include goal, context summary, anchored files/symbols, implementation instructions, "do not do" boundaries, validation commands, rollback boundary, and required report format.
   - Prefer small atomic tasks. Split any task whose validation, risk, or rollback boundary is unclear.

5. **Separate planning and execution roles**
   - Planning agents grill the intent and write specs.
   - Execution agents implement only the approved spec, run validation, update `CODEMAP.md` and task status, and report evidence.
   - Keep `prompts/DISCUSSION_AI.md` current after each completed task so users can paste it into any agent interface to resume planning.
   - Keep `prompts/EXECUTION_AI.md` stable; put task-specific instructions in `.tasks/build/*.md`.
   - When execution changes product scope, dependencies, architecture, or file ownership, update `PRD.md`, `ARCHITECTURE.md`, and `CODEMAP.md` before closing the task.
   - For trivial one-line changes, allow direct execution only if the repo conventions explicitly permit it.

6. **Handle discussion-window migration**
   - If the user says they want to migrate, hand off, continue in another agent, open a new discussion window, or copy the discussion prompt, update `prompts/DISCUSSION_AI.md` first if it is stale.
   - Then output the full current discussion prompt in a fenced code block for direct copying.
   - Do not replace the prompt with a summary unless the user asks for a shorter version.

7. **Debug through causality**
   - For bugs, trace `Error -> State -> Code -> Spec`.
   - Do not start by guessing the most familiar file.
   - Find the earliest polluted assumption, state transition, cache, persisted field, or spec ambiguity.
   - Prefer the minimal patch set that repairs the causal chain without expanding behavior.

## Reference Loading

- Read `references/core-concepts.md` when the user asks about WishGraph concepts, naming, or public explanation.
- Read `references/zero-project-bootstrap.md` when the user is starting from a vague idea, has no PRD, wants the first project conversation, or asks for grill-style project shaping.
- Read `references/task-spec-template.md` before creating or revising task files.
- Read `references/good-execution-spec.md` when creating the first task spec for a project, reviewing whether a task spec is good enough, or showing the user an example.
- Read `references/review-window.md` before producing human-facing review summaries, Dev Reports, or single-window status digests.
- Read `references/debug-causality.md` before triaging bugs, regressions, failed validation, or hidden state corruption.

## Template Mapping

Use bundled templates as starting points, then adapt them to the target repository:

| Skill Asset | Target Path |
|---|---|
| `assets/templates/PRD.md` | `PRD.md` |
| `assets/templates/CODEMAP.md` | `CODEMAP.md` |
| `assets/templates/CONVENTIONS.md` | `CONVENTIONS.md` |
| `assets/templates/ARCHITECTURE.md` | `ARCHITECTURE.md` |
| `assets/templates/DISCUSSION_AI.md` | `prompts/DISCUSSION_AI.md` |
| `assets/templates/EXECUTION_AI.md` | `prompts/EXECUTION_AI.md` |
| `assets/templates/001-bootstrap-project.md` | `.tasks/build/001-bootstrap-project.md` when setting up a new project |
| `assets/templates/NNN-task.md` | `.tasks/build/001-first-task.md` or the next task number |
| `assets/templates/EXAMPLE-good-task.md` | Optional example for humans and planning agents |
| `assets/templates/DEV_REPORT.md` | `reports/DEV_REPORT.md` |

## Output Rules

- Keep governance changes close to the current project; do not impose source-project-specific domain rules unless the target project explicitly asks for them.
- Do not include the creator's personal content, social media drafts, or private case-study language when adapting a user's project.
- Treat project files as external memory. Update them when the state changes.
- For a brand-new project, do not start implementation until the PRD is concrete enough to write a bounded first task.
- For discussion migration requests, show the copyable prompt itself, not only a description of where it lives.
- Make scope boundaries explicit. Every task should say what it will not do.
- Include validation evidence. If a command cannot run, say why and record the residual risk.
- Never claim full autonomy. WishGraph keeps AI work inspectable; the human remains the final evaluator.
