# WishGraph

[English](README.md) | [简体中文](README.zh-CN.md)

[![CI](https://github.com/odopk-spring/wishgraph/actions/workflows/ci.yml/badge.svg)](https://github.com/odopk-spring/wishgraph/actions/workflows/ci.yml)
![Status](https://img.shields.io/badge/status-v0.1%20public%20beta-625DF1)
![Python](https://img.shields.io/badge/Python-3.9%2B-2D72E8)
![Codex](https://img.shields.io/badge/agent-Codex-172033)
![Claude Code](https://img.shields.io/badge/agent-Claude%20Code-172033)
![License](https://img.shields.io/badge/license-PolyForm%20Noncommercial-14A878)

**Durable project memory and execution boundaries for AI coding agents.**

WishGraph records product intent, architecture, task scope, execution evidence, and the latest project state in the repository. Codex and Claude Code can then resume from compact, shared facts instead of treating chat history—or a fresh scan of the entire source tree—as project memory.

![Discuss, run a visible Worker, integrate, and discuss again](docs/assets/wishgraph-simple-loop-en.svg)

[Start in 60 seconds](#start-in-60-seconds) · [Understand the workflow](#one-project-three-responsibilities) · [Browse the docs](docs/README.md) · [中文说明](README.zh-CN.md)

> WishGraph is opt-in per project. Installing the Skill makes it available globally; a project remains an ordinary agent project until you explicitly enable WishGraph there.

First use stays the same on every supported host:

```text
1. Enable WishGraph in the project
2. Reopen the current Agent session
3. Say: Start discussion
```

## What using it feels like

After enabling WishGraph in a project, the normal entry points are short natural-language commands:

```text
Start discussion.
Execute task 012.
Refresh project status.
```

- **Start discussion** loads the compact current-state entry points and opens planning.
- **Execute task 012** starts or routes one authorized, user-visible Worker for that exact Task.
- **Refresh project status** reads the current project snapshot and relevant terminal reports; it does not traverse the whole source tree by default.

Low-risk English entry aliases are also accepted, including `Begin discussion`, `Open discussion`, `Enter discussion mode`, `Continue discussion`, `Resume discussion mode`, `Check project status`, `Update project status`, and `Reload project status`.

Clear, low-risk feedback such as “change this button to warm gray” becomes a lightweight Revision of the original Task. A Worker window can also be reused after it releases the old Task and binds a new Claim. Small corrections stay small without losing validation or history.

## Start in 60 seconds

### Codex

Ask Codex to install the Skill:

```text
Use $skill-installer to install https://github.com/odopk-spring/wishgraph/tree/main/skills/wishgraph
```

Then open the target project and enable it:

```text
Use WishGraph for this project.
```

Reopen the Codex session and say `Start discussion`.

To install the Skill and safe project Hooks from a terminal instead:

```bash
curl -fsSL https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.sh | bash -s -- codex --setup-project
```

### Claude Code

Run this inside the target project, reopen the Claude Code CLI session, and say `Start discussion`:

```bash
curl -fsSL https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.sh | bash -s -- claude-user --setup-project
```

### Windows PowerShell

```powershell
& ([scriptblock]::Create((irm 'https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.ps1'))) codex -SetupProject
```

Safe setup uses `warn` mode and does not block commits. After one successful end-to-end run, enable strict checks with `--strict` on Bash or `-Strict` on PowerShell. See [Getting Started](GETTING_STARTED.md) for other installation targets and recovery steps.

If `Start discussion` does not respond after reopening the session, run WishGraph Doctor. Claude Code CLI users may additionally run `claude doctor`. These are troubleshooting steps, not part of normal setup.

## One project, three responsibilities

| Responsibility | Where it runs | What it does |
| --- | --- | --- |
| **Discussion** | Long-lived user-facing window | Clarifies intent, creates bounded Task Specs, authorizes routing, integrates results, and presents decisions. It does not implement business code. |
| **Worker** | Separate user-visible execution window | Claims one Task or Revision, changes only its allowed scope, validates the result, and writes an immutable Run Report. |
| **Integration** | Temporary phase inside Discussion | Evaluates terminal reports, runs combined checks, updates shared project state, and asks only when a material product or risk decision is required. |

Integration is a phase, not a hidden agent or a fourth window. If Discussion is inactive when a Worker finishes, WishGraph stores `integration_pending` and resumes evaluation when Discussion starts or the project status is refreshed.

Codex can route work to a visible Worker when the host supports it. Claude Code CLI prefers an inspectable native background session through the managed `wishgraph-worker` Agent. If that capability is absent or launch fails, WishGraph prints only `Execute task 012` and Discussion stops execution.

## The files humans and agents share

| Entry point | Purpose |
| --- | --- |
| `PRD.md` | Current goals, scope, roadmap, and product decisions |
| `ARCHITECTURE.md` + `CODEMAP.md` | System boundaries and the map from features to source files |
| `CONVENTIONS.md` | Collaboration, validation, and Git rules |
| `tasks/build/*.md` | Bounded formal Tasks |
| `tasks/revisions/*.md` | Small, parent-linked corrections such as `012-r1` |
| `reports/runs/*.md` | Immutable Worker evidence |
| `reports/PROJECT_STATUS.md` | Current integrated snapshot and the fastest human entry point |

Markdown carries human-readable meaning. Small versioned JSON blocks hold mechanical facts such as authorization, Claims, validation, and integration state. The latest-state file is rewritten as a current snapshot; execution history remains in immutable reports instead of accumulating as noise there.

## Built-in maintenance

In an enabled project, the Skill routes these requests to bounded maintenance actions:

| Request | Result |
| --- | --- |
| `Check WishGraph status` | Read-only diagnosis of installed files and recently observed host execution |
| `Update this project's WishGraph` | Fingerprint-verified safe runtime upgrade with rollback |
| `Repair WishGraph hooks for this host` | Repairs only the current host adapter and preserves unrelated Hooks |

Doctor distinguishes “configured correctly” from “recently invoked by this host.” If execution remains unverified, review Codex Hooks with `/hooks`; Claude Code CLI users can run `claude doctor`.

## Safety and current limits

- A Worker requires explicit human authorization and a live Claim bound to its Task, session, branch, worktree, scope, and validation plan.
- Write/build gates cover supported native tools and recognized commands. Source-read enforcement remains host-capability dependent, and Hooks are not an operating-system sandbox.
- Claims are atomic across local worktrees that share one Git common directory; they are not distributed locks across machines.
- Safe results can integrate without asking “should I start integration?” Conflicts, public API changes, new product decisions, missing evidence, and other material risks return to Discussion as specific questions.
- Hooks expose and enforce workflow state. They do not start Workers, merge code, or decide product meaning by themselves.

WishGraph is a **v0.1 public beta**. The Skill validates, installation and runtime lifecycles have automated coverage, and both Codex and Claude Code paths are documented. Broader real-project and host-version testing is still needed before calling it a stable v1.

## Explore the repository

| Goal | Start here |
| --- | --- |
| Guided setup | [Getting Started](GETTING_STARTED.md) |
| Method and concepts | [WishGraph Method](docs/wishgraph-method.en.md) |
| State machine and role boundaries | [Orchestration state machine](docs/orchestration-state-machine.md) |
| Hook protocol and host limits | [External-Memory Hooks](docs/memory-sync-hooks.md) |
| Claude Code adaptation | [Claude Code adapter](adapters/claude-code/README.md) |
| Manual templates | [Templates](templates/README.md) |

```text
skills/wishgraph/   Installable Skill and bundled runtime
templates/          English and Chinese project-memory templates
adapters/           Claude Code and generic agent instructions
docs/               Method, protocol, and workflow documentation
scripts/            Bash and PowerShell installers
tests/              Runtime and installer regression tests
```

WishGraph supports English, Simplified Chinese, and bilingual project memory. Commands, paths, identifiers, and structured state remain language-neutral.

## License

WishGraph is released under the [PolyForm Noncommercial License 1.0.0](LICENSE). You may download, study, modify, and redistribute it for noncommercial purposes. Commercial use requires separate written permission. This is a source-available noncommercial license, not an OSI open-source license.
