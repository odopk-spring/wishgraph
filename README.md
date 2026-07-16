# WishGraph

[English](README.md) | [简体中文](README.zh-CN.md)

[![CI](https://github.com/odopk-spring/wishgraph/actions/workflows/ci.yml/badge.svg)](https://github.com/odopk-spring/wishgraph/actions/workflows/ci.yml)
![Status](https://img.shields.io/badge/status-v0.1%20public%20beta-625DF1)
![Python](https://img.shields.io/badge/Python-3.9%2B-2D72E8)
![Codex](https://img.shields.io/badge/agent-Codex-172033)
![Claude Code](https://img.shields.io/badge/agent-Claude%20Code-172033)
![License](https://img.shields.io/badge/license-PolyForm%20Noncommercial-14A878)

**Let AI move fast without turning the project into a mystery.**

As coding agents get stronger, projects can become harder to understand: a small request spreads across more files, a new window needs the whole story again, and every handoff starts with another code scan and progress summary.

WishGraph adds a clear project interface between natural language and code. It turns an open-ended wish into a bounded task, constrains execution, and writes verified results back into current project state:

```text
Wish → Spec → Task → Worker → Validation → Run Report → Integration → Current State
```

Goals, architecture, tasks, evidence, and progress live in the repository instead of one chat. You keep speaking naturally; Codex and Claude Code continue from the same compact facts.

![Discuss, execute, integrate, and continue](docs/assets/wishgraph-simple-loop-en.svg)

[See one complete run](#one-minute-tour) · [Install in 60 seconds](#install-in-60-seconds) · [FAQ](#faq) · [Safety boundaries](#safety-boundaries) · [Detailed docs](#go-deeper)

## The framework

WishGraph is not about making every agent read more documentation. Each phase reads only what it needs.

| Part | Responsibility |
| --- | --- |
| **Project memory** | Keeps product rules, architecture, code locations, and current state without storing whole chat transcripts. |
| **Discussion** | Clarifies intent, sets boundaries, and writes Tasks. It does not implement business code. |
| **Worker** | Executes one authorized Task in an independent, inspectable Agent thread or window and leaves validation evidence. |
| **Integration** | Evaluates the result inside Discussion and updates shared state. It proceeds automatically when safe and asks only for a material decision. |

The default read scope stays small:

- Discussion starts with the concise handoff, `reports/PROJECT_STATUS.md`, and active state.
- A Worker reads its exact Task or Revision, execution rules, necessary status, and source files inside scope.
- Integration reads this run's reports and only the shared files they actually affect.

Historical reports remain available without accumulating in the current-state file or being reread at every start.

> WishGraph is opt-in per project. A global Skill installation means “available,” not “active in every folder.”

## One-minute tour

Suppose you want to add dark mode to a reading screen.

### 1. Start the discussion

In a project where WishGraph is already enabled, say:

```text
Start discussion
```

Then speak normally: “I want dark mode on the reading screen.” Discussion uses current project state to ask only the questions that change the outcome—reading screen or whole app, system-controlled or manual, and what proves the feature works.

Once the boundary is clear, it creates a self-contained Task such as `012b`, including scope, non-goals, allowed files, and validation.

### 2. Authorize execution

Say:

```text
Execute task 012b
```

WishGraph lets the current host choose the best inspectable Worker it can genuinely provide:

- If the host supports a native Agent thread or background session, it creates an independent Worker and saves the real thread/session ID.
- If native creation is unavailable or fails, Discussion prints one line—`执行 012b 任务`—for you to enter in a new execution window.

The Worker changes code only after exact Task preflight and Claim acquisition. It does not read unrelated Tasks, all historical reports, or the complete source tree.

### 3. Validate and update the project

The Worker writes an immutable Run Report describing the patch, checks, and remaining risk. On its next activation, Discussion receives a completion reminder and enters local Integration:

- Complete evidence and no conflict: integrate and refresh current project state automatically.
- Missing report or failed validation: mark the work blocked instead of pretending it is done.
- Public API, product, or conflict decision: ask only that concrete question.

When you later switch windows, models, or even between Codex and Claude Code, there is no full prompt to copy. Open the same Git project and say `Start discussion`; the new agent resumes from project files.

### 4. Keep small changes small

Feedback such as “I dislike this blue; make it warm gray” becomes a lightweight Revision of the original Task, not another long spec. It becomes a formal follow-up Task only when it reaches a public API, schema, persistence, dependency, security boundary, or new product decision.

## Install in 60 seconds

WishGraph requires Git and Python 3.9+ and installs no Python packages. These commands install the Skill and enable safe-mode Hooks in the **current Git project**.

### Codex · macOS / Linux

Run inside the target project:

```bash
curl -fsSL https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.sh | bash -s -- codex --setup-project
```

### Claude Code CLI · macOS / Linux

Run inside the target project:

```bash
curl -fsSL https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.sh | bash -s -- claude-user --setup-project
```

### Windows PowerShell

Codex:

```powershell
& ([scriptblock]::Create((irm 'https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.ps1'))) codex -SetupProject
```

Claude Code:

```powershell
& ([scriptblock]::Create((irm 'https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.ps1'))) claude-user -SetupProject
```

After installation:

```text
1. Reopen the current Agent session
2. Say: Start discussion
```

The default `warn` mode reports problems without blocking completion or commits. After one successful full run, enable strict gates with `--strict` on Bash or `-Strict` on PowerShell if you want them.

For an Agent-guided setup, install this repository's `skills/wishgraph` with `$skill-installer` in Codex, or invoke `/wishgraph` after installing it in Claude Code, then say:

```text
Use WishGraph for this project.
```

See [Getting Started](GETTING_STARTED.md) for existing-project adoption, other install modes, and recovery.

## FAQ

### Does installing the Skill activate WishGraph in every project?

No. The Skill may be global, but every project must opt in explicitly. In an inactive project, `Start discussion` is ordinary text and does not create files or enter the workflow.

### Do I need to copy a migration prompt when I change windows or agents?

No. WishGraph handoff state lives in project files and the Git-common runtime, not in the previous conversation. Open the same project and say `Start discussion`. When switching hosts, install or repair only the current host's Skill and project adapter. Copying a full prompt is not the normal handoff and is not a Claude Code migration requirement.

### What do the three common commands mean?

- `Start discussion` moves the current neutral window into Discussion and loads compact current state.
- `Execute task 012` authorizes and routes exactly Task `012`; it never prefix-matches `012b` or `012ba`.
- `Refresh project status` refreshes active state and relevant terminal evidence without scanning the whole source tree or report history by default.

### Is the Codex experience identical to Claude Code?

The user commands and project state are the same; the Worker container is host-specific. Codex prefers the project `wishgraph-worker` when the current surface supports an inspectable Agent thread. Claude Code CLI uses the following command only after capability, managed-Agent, worktree, authorization, and current-`HEAD` checks pass:

```text
claude --bg --agent wishgraph-worker "执行 <task-id> 任务"
```

Any failed native launch falls back to the one-line execution command. It never authorizes Discussion to implement the Task.

### Does a completed background Worker pop up the Discussion window?

No. WishGraph runs no daemon, terminal polling loop, or cross-window IPC service. A normal Worker closeout writes a pending notification; Discussion consumes it on the next SessionStart, prompt, or explicit refresh.

### Will WishGraph fill my repository with process files?

Existing repositories use native-lite adoption by default: reuse current README, product, architecture, conventions, and tests, then add only missing entry state. Task, Revision, and report directories appear when first needed. Immutable history stays in Run Reports while `PROJECT_STATUS.md` remains a current snapshot.

### Does every small correction need a full Task?

No. A clear, low-risk correction linked to the original Task uses a lightweight Revision. Public API, schema, persistence, dependency, permission, security, privacy, or new product decisions return to Discussion as a formal Task.

### Can I switch between Codex and Claude Code?

Yes. PRDs, Tasks, reports, and project state are portable inside the Git project. Host thread/session IDs are not shared across platforms, so the new agent establishes its own valid Worker binding and Claim before execution.

### Is WishGraph a sandbox?

No. Hooks can gate writes, builds, commits, and lifecycle events exposed by the host, but they do not replace operating-system permissions or container isolation. Complete read interception also depends on host capabilities.

## Safety boundaries

- **Explicit authority:** a Formal Worker must be bound to one exact Task or Revision; vague conversation does not grant execution authority.
- **Role separation:** Discussion handles planning, Tasks, Integration, and presentation. It does not implement business code or run Worker validation.
- **Bound Claims:** business writes and builds require a Claim bound to Task, session, branch, absolute worktree, scope, and validation plan.
- **Inspectable Workers:** only an Agent with a stable thread/session ID, independent context, and inspect/stop/steer controls can become a Formal Worker. Hidden subagents remain Helpers.
- **Single-writer project state:** Workers propose shared updates in Run Reports; only Discussion-local Integration with a bound lease updates shared project truth.
- **Evidence-based completion:** a natural-language “done” message is insufficient. Task state, Run Report, validation, and Claim closeout must agree.
- **Local coordination boundary:** Claims coordinate worktrees sharing one local Git common directory; they are not distributed locks across machines.

WishGraph is a **v0.1 public beta**. Automated tests cover installation, state transitions, Claims, Revisions, Codex/Claude Worker routing, notifications, and performance gates. Broader real-project and host-version testing is still required before calling it a stable v1.

## Where project memory lives

| File | Human meaning |
| --- | --- |
| `PRD.md` | Goals: what the project is doing, why, and what is out of scope. |
| `ARCHITECTURE.md` | Structure: modules, dependencies, data flow, and boundaries. |
| `CODEMAP.md` | Address book: where features, state, storage, and tests live. |
| `CONVENTIONS.md` | Working rules: collaboration, validation, Git, and state writeback. |
| `tasks/build/*.md` | Formal Tasks with scope, non-goals, validation, and rollback boundaries. |
| `tasks/revisions/*.md` | Lightweight, low-risk corrections. |
| `reports/runs/*.md` | Immutable Worker execution and validation evidence. |
| `reports/PROJECT_STATUS.md` | Current dashboard: latest result, risk, active work, and next action. |

Existing projects do not need to create every file mechanically. WishGraph reuses native documents that already own the same truth.

## Go deeper

| What you need | Document |
| --- | --- |
| Installation through the first complete run | [Getting Started](GETTING_STARTED.md) |
| Method and project-compression idea | [WishGraph Method](docs/wishgraph-method.en.md) |
| Roles, states, and command parsing | [Orchestration state machine](docs/orchestration-state-machine.md) |
| Hooks, gates, performance, and host limits | [External-Memory Hooks](docs/memory-sync-hooks.md) |
| Current Claude Code CLI adaptation | [Claude Code adapter](adapters/claude-code/README.md) |
| Hosts without native Skills | [Generic Agent adapter](adapters/generic/README.md) |
| Repository templates | [Templates](templates/README.md) |

```text
skills/wishgraph/   Installable Skill and bundled runtime
templates/          Human-readable English and Chinese templates
adapters/           Claude Code and generic Agent guidance
docs/               Method, state machine, and Hook references
scripts/            Bash and PowerShell installers
tests/              Installer and runtime regression tests
```

## License

WishGraph uses the [PolyForm Noncommercial License 1.0.0](LICENSE). You may download, study, modify, and redistribute it for noncommercial purposes. Commercial use requires separate written permission. It is a source-available noncommercial license, not an OSI open-source license.
