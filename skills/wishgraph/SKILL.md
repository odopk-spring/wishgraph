---
name: wishgraph
description: Create and maintain file-backed governance for AI-assisted software projects. Use when the user explicitly names WishGraph for installation or project activation, or when the current Git project already has an active .wishgraph/config.json and needs durable PRDs, architecture, code maps, bounded Task Specs, inspectable Worker execution, validation evidence, immutable Run Reports, Discussion-local integration, cross-session handoff, causal debugging, or WishGraph commands in Chinese, English, or bilingual projects.
---

# WishGraph

## Overview

Use WishGraph to compile human intent into an auditable project-state graph:

```text
Wish -> Spec -> Task -> Worker -> Validation -> Run Report -> Integration -> Review
```

Keep uncertainty, authority, evidence, and current project truth in repository files so work can
continue without chat history.

## Project Activation

- Treat global Skill installation as availability, never project activation.
- Before routing generic entry phrases, read only the current Git root's `.wishgraph/config.json`.
- WishGraph is active only when that file exists and `mode` is `warn` or `enforce`; missing config or `mode: off` means inactive.
- In an inactive project, do not reinterpret `开始讨论`, `刷新项目状态`, or `执行 NNN 任务` as WishGraph commands. Do not read References, create project files, or install hooks.
- Only an explicit request naming WishGraph, such as `使用 WishGraph` or `Use WishGraph`, may begin first-time project setup.
- First-time activation completes setup but keeps the window `neutral`. Tell the user to reopen the current Agent session. Require a later explicit `开始讨论` / `Start discussion` event to enter Discussion.
- Keep Doctor out of the normal first-use path. Route an explicit `检查 WishGraph 状态` / `Check WishGraph status`, or a reopened session that still does not respond, to the read-only Doctor before loading workflow context.
- Route an explicit project update to the fingerprinted safe-upgrade path; preserve unknown or locally modified runtime files and ask before any forced replacement.
- In an active project with a current runtime, repair only the current host's missing or outdated adapter; never install the other host as a side effect.

## Role Boundaries

- Treat every new host window as `neutral` until the user explicitly enters Discussion or runs an exact Task command.
- Use `discussion` for planning, Task creation, Worker routing, integration, and result presentation.
- Use `worker` only in a separate user-visible and inspectable Agent thread or window bound to one Task or Revision.
- Treat Integration as an automatically triggered, Discussion-local Flow Phase, never a role or separate window.
- Treat Review as result presentation inside Discussion, never a fourth Agent.
- A Formal Worker is authorized, Claim-bound, gated, inspectable, controllable, and produces structured terminal evidence. A Helper Subagent is read-only exploration, retrieval, log analysis, or review. A Hidden/Internal Agent cannot become a Worker.
- Agent or subagent identity never creates authority. Never give Explorer, Reviewer, Helper, or Hidden/Internal Agents a Worker Claim.
- Never let Discussion implement business code, run implementation builds/tests, or become the Worker fallback.

## Core Workflow

1. Inspect the repository and reuse compatible project truth instead of creating parallel memory.
2. Compile intent into observable behavior, acceptance criteria, non-goals, and material decisions.
3. Create only the minimum durable project-state graph and bounded executable work units.
4. Classify work, record one exact expected transition, and obtain the required human authority.
5. Route each authorized unit to a separate user-visible and inspectable Worker thread or window; Discussion stops execution after handoff.
6. Require scoped implementation, prescribed validation, immutable evidence, and safe Claim closeout.
7. Send every terminal result to Discussion-local integration automatically; ask only material decisions.
8. Present the integrated result, evidence, residual risk, and next action without erasing history.

## Mandatory Gates

- Resolve IDs exactly from structured state. Never prefix-match `012`, `012b`, and `012ba`.
- Interpret short approvals only when one unique structured `expected_transition` exists; explicit commands take priority.
- Require explicit human authority before creating a Formal Worker. Persist `waiting_for_worker` only after a real stable thread/session ID is saved. Host limitations never expand Discussion authority.
- Require a live Worker Claim bound to work unit, session, branch, absolute worktree, scope, and validation before implementation.
- Release or revoke the old Claim before Worker rebind. Never let one window hold two active work units or inherit stale scope.
- Require a Discussion-local Integration lease before merge resolution, combined validation, shared-state writes, or integration commit.
- Keep shared project memory single-writer: Workers propose updates in Run Reports; Integration applies them.
- Preserve immutable Task, attempt, Claim, Revision, Run Report, and losing competitive evidence.
- Use `write/build gate: required`. Describe source-read enforcement as `read gate: host capability dependent` unless the host can intercept every read path.
- Treat hooks as mechanical gates and state readers, never as product decision-makers or hidden executors.
- Run prescribed validation and the WishGraph checker before claiming completion; record skipped checks and residual risk.
- Keep routine non-commit `PreToolUse` bounded to configured state and the requested operation; never enumerate the business source tree.

## Reference Routing

Read only the references required for the current request:

- Installation, prerequisites, safe/strict mode, upgrade, or recovery: `references/installation.md`.
- Project concepts, naming, or public explanation: `references/core-concepts.md`.
- New or existing project adoption, governance layout, templates, or bilingual memory: `references/project-bootstrap.md`.
- Roles, phases, Task lifecycle, exact commands, approvals, and pure transitions: `references/orchestration-state-machine.md`.
- Visible Worker routing, host fallback, Claims, closeout, recovery, or rebind: `references/worker-execution.md`.
- Formal Task structure, quality criteria, and worked example: `references/task-spec.md`.
- Clear low-risk correction: read only `references/task-revisions.md`; expand only through its exception table.
- Multiple candidates for the same goal, scorecards, winner selection, and loser closeout: `references/competitive-execution.md`.
- Automatic integration, leases, combined validation, shared-memory writeback, material decisions, or result presentation: `references/integration-flow.md`.
- Bug triage or regression diagnosis: `references/debug-causality.md`.
- Hook events, checker commands, host limits, performance baseline, or runtime troubleshooting: `references/memory-sync-hooks.md`.
