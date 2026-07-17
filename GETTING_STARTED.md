# Getting Started With WishGraph

[English](GETTING_STARTED.md) | [简体中文](GETTING_STARTED.zh-CN.md)

This guide covers installation, project activation, and the first complete Discussion → Worker → Integration run. For the short explanation, start with the [README](README.md).

## Before you install

WishGraph requires:

- A Git repository.
- Python 3.9 or newer.
- Codex or Claude Code for the supported native paths.

It installs no Python packages. The Skill is roughly 0.5 MB and the project runtime roughly 0.3 MB.

Global installation and project activation are separate:

- **Installed globally:** WishGraph is available to the Agent.
- **Enabled in this project:** `.wishgraph/config.json` exists with `mode: warn` or `mode: enforce`.
- **Discussion active:** an enabled project receives an explicit `Start discussion` command.

Installing WishGraph never opts every folder into the workflow.

## Install in the current project

Run one command from the Git project you want to enable.

### Codex · macOS / Linux

```bash
curl -fsSL https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.sh | bash -s -- codex --setup-project
```

### Claude Code CLI · macOS / Linux

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

The installer checks Git, Python, and the repository root before writing. It keeps the Agent running setup (`current_host`) separate from the project scope (`required_hosts`). By default it atomically installs both Codex and Claude Code adapters, while preserving unrelated Hook groups. The default `warn` mode reports workflow problems without blocking completion or commits.

For a deliberate single-host project, add `--project-hosts codex` or `--project-hosts claude` (PowerShell: `-ProjectHosts codex|claude`). The other Adapter is not required, and ordinary sessions in that host are not protected. Agent-guided setup asks the same three-way question instead of inferring the answer from the current Agent.

For Agent-guided setup, install the Skill first and say:

```text
Use WishGraph for this project.
```

That explicit request authorizes the recommended safe setup. `Start discussion` by itself never activates an unconfigured project.

## Start the first session

After setup succeeds:

```text
1. Reopen the current Agent session
2. Say: Start discussion
```

The new window starts neutral. The command loads only the concise Discussion handoff, current Project Status, and active workflow state.

For an existing project, WishGraph first reuses authoritative files already present in the repository. It should not rename folders, copy existing documents into parallel WishGraph versions, create a fake bootstrap Task, or modify business code merely to prove installation.

For a blank or vague project, the first Discussion starts with a small intake:

```text
You do not need a full PRD yet. In a few sentences, tell me:
1. What are you trying to build?
2. Who should it serve first?
3. What should they be able to do on the first successful use?
4. What result would make you say v0 is working?
If you are not sure, answer only item 1 and I will fill the rest one decision at a time.
```

Discussion asks one material question at a time and gives a recommended default. It builds the project frame before implementation.

## Run the first Task

When the requirement is clear, Discussion writes one self-contained Task with:

- Goal and current state.
- Allowed change scope.
- Explicit non-goals.
- Dependencies and ownership.
- Validation commands or manual checks.
- Shared project-state impact.
- Rollback boundary and Run Report path.

It then asks for execution authority. Use an exact command:

```text
Execute task 012
```

Authorization does not let Discussion implement the Task. It asks the current host for the best valid Worker route.

| Host route | What happens |
| --- | --- |
| Codex surface with inspectable Agent threads | The host creates the project `wishgraph-worker`; WishGraph records success only after receiving a real stable thread ID. |
| Claude Code CLI with compatible background-agent support | The Host Adapter starts the managed background Agent in a unique Worktree, injects only the per-launch Worktree settings, and records the stable session ID. |
| Native creation unavailable or failed | Discussion prints only `执行 012 任务`; open a new inspectable execution window and enter that line. |

The new Worker is not `running` merely because a process or thread was requested. It must pass exact Task preflight and acquire a Claim bound to its session, branch, absolute worktree, allowed scope, and validation plan.

The global Claude Adapter and Worker Agent may serve every explicitly enabled project. A project `.claude/settings.json` is optional; per-launch settings do not overwrite global or project configuration.

## What the Worker reads

A normal Worker starts with:

1. `prompts/EXECUTION_AI.md`.
2. Its exact Task or Revision.
3. The smallest necessary Project Status section.
4. Source files required by its allowed scope.

It does not load unrelated Tasks, historical Run Reports, or the entire source tree by default. If the Task requires a public API, schema, persistence, dependency, permission, security, privacy, or new product decision that was not authorized, the Worker stops and returns the decision to Discussion.

At closeout it runs prescribed validation, creates one immutable Run Report, records project-memory impact, moves the work to a real terminal state, makes a bounded commit unless told otherwise, and releases its Claim.

## Integration and completion

Every Worker terminal event enters `integration_pending`.

For a safe result, Discussion-local Integration obtains a lease, merges without committing first, checks the Run Report and affected files, runs combined validation, updates shared project state, rewrites `reports/PROJECT_STATUS.md`, and creates the integration commit.

The user is not asked “should I start integration?” twice. A question appears only when a concrete conflict, risk, compatibility choice, or product decision needs human judgment.

If Discussion is not active when the Worker finishes, Claim release writes one pending notification in the Git-common runtime. Discussion consumes it on the next SessionStart, prompt, or explicit status refresh. WishGraph does not use a daemon, terminal polling, cross-window IPC, or automatic popup.

## Continue in another window or host

No prompt migration is required.

In a new window on the same project:

```text
Start discussion
```

In an already active Discussion:

```text
Refresh project status
```

When changing from Codex to Claude Code or back, first confirm that host is in `required_hosts`. If it is not, explicitly reactivate with both hosts; then reopen the newly enabled Agent and use the same command. Durable project state is shared; host-specific thread/session IDs are not.

## Revisions and Worker reuse

A clear low-risk correction linked to an existing Task uses `tasks/revisions/<task-id>-rN.md`. It records only the parent Task, exact request, allowed scope, targeted validation, state, and report path.

A Worker thread may be reused after its old work is terminal, its old Claim is released, old scope is cleared, and a fresh Claim binds the new Task or Revision. One Worker can hold only one active work unit at a time.

Any API, schema, persistence, migration, dependency, permission, security, privacy, or new product decision becomes a formal follow-up Task.

## Existing-project file policy

WishGraph uses native-lite adoption by default:

- Reuse an existing product spec instead of creating a competing `PRD.md`.
- Reuse existing architecture, code-map, conventions, issue, Task, and test sources when they already own the truth.
- Add a compact `reports/PROJECT_STATUS.md` and Discussion/Worker entry state only when missing.
- Create Task, Revision, and Run Report directories when first needed.
- Keep current status as a rewritten snapshot; keep history in immutable reports and Git.

The standard file names are defaults, not a demand to duplicate good project documentation.

## Maintenance and recovery

Normal users can use these natural-language requests:

| Request | Effect |
| --- | --- |
| `Check WishGraph status` | Fixed-path, read-only Doctor check. It does not scan business source. |
| `Update this project's WishGraph` | Fingerprint-verified, atomic runtime upgrade with rollback. |
| `Repair WishGraph hooks for this host` | Repairs only the active host adapter and preserves unrelated Hooks. |

If `Start discussion` does not respond after reopening the session, run Doctor first. Check `/hooks` in Codex only when host invocation remains unverified; Claude Code CLI users may additionally run `claude doctor`.

Doctor checks configured `required_hosts` by default. It reports Adapter static state separately from execution receipts, so “adapter current; execution unverified” means installation succeeded but that Agent has not yet been reopened. A single-host project does not fail because the unselected Adapter is absent.

Updating a global Skill does not silently rewrite project-local `.wishgraph/hooks/`. Use the safe project update path for an existing runtime. Locally modified or unknown generated files stop for review instead of being overwritten.

## Strict mode

Start with `warn`. After one clean end-to-end closeout, optionally enable blocking checks:

```bash
curl -fsSL https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.sh | bash -s -- codex --setup-project --strict
```

Use `claude-user` for Claude Code. On PowerShell, add `-Strict`.

Strict setup enables `enforce` and requests a Git pre-commit fallback. The installer never overwrites an existing Git hook; it reports how to chain it instead.

`enforce` works only through an installed, loaded host Adapter; it is not an OS sandbox. Without a Claude Adapter, WishGraph cannot mechanically detect or block a normal Claude Code session. The Git fallback checks commits, not every write.

## First-run success checklist

WishGraph is working when:

- `Start discussion` enters Discussion only in the enabled project.
- A fresh Discussion understands current state without full-tree scanning.
- An exact execution command creates or routes a separate inspectable Worker.
- The Worker cannot write or build before Claim acquisition.
- One immutable Run Report records the real validation result.
- Safe Integration updates affected project facts and rewrites current status.
- A new window can continue with `Start discussion`, without copied chat or prompt text.

For implementation details, see [External-Memory Hooks](docs/memory-sync-hooks.md), the [state-machine specification](docs/orchestration-state-machine.md), and the [Claude Code adapter](adapters/claude-code/README.md).
