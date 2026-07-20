# Claude Code CLI Adapter

[English](README.md) | [简体中文](README.zh-CN.md)

WishGraph uses a native Skill, project Hooks, and a managed `wishgraph-worker` Agent in Claude Code. Normal use requires no full-prompt copy and no manual “discussion migration.” Project state lives in the repository; a new session in the same project continues with `Start discussion`.

## Install in 60 seconds

Run inside the target Git project:

```bash
curl -fsSL https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.sh | bash -s -- claude-user --setup-project
```

Windows PowerShell:

```powershell
& ([scriptblock]::Create((irm 'https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.ps1'))) claude-user -SetupProject
```

Then:

```text
1. Reopen the Claude Code session
2. Say: Start discussion
```

The installer:

- Installs the Skill at `~/.claude/skills/wishgraph/`, making `/wishgraph` available.
- Installs the `.wishgraph/` runtime in the current project.
- Defaults the project to `required_hosts: [codex, claude]` and atomically installs both project adapters. Add `--project-hosts claude` only for a deliberate Claude-only project.
- Installs a user-level Adapter that stays silent outside explicitly enabled projects; project-local Hooks remain available for compatibility.
- Installs the managed `.claude/agents/wishgraph-worker.md` definition.
- Passes the minimal Worktree configuration per launch, without rewriting existing user or project settings, and makes the `.wishgraph` runtime available inside isolated worktrees.

The global Adapter and managed Agent may serve every project that explicitly opts in through `.wishgraph/config.json`. A duplicate project `.claude/settings.json` is optional.

The default `warn` mode reports problems without blocking completion or commits. After one successful full run, append `--strict` to the Bash command or `-Strict` on PowerShell if you want blocking gates.

## Everyday use

```text
Start discussion
Execute task 012
Refresh project status
```

- Discussion reads the concise handoff, current Project Status, and active state; it opens other documents only when needed.
- A Worker reads the exact Task or Revision, necessary Project Status sections, and source inside scope. Stable Worker rules come from the installed Adapter and Skill.
- Integration reads this run's reports and only the shared files they actually affect.

To continue in another Claude Code window, open the same project and say `Start discussion`; WishGraph resumes from Project Status and Git-common runtime state. When arriving from Codex, confirm Claude is selected in `required_hosts`, install or repair its Adapter if needed, reopen the session, then use the same entry.

## How Worker launch works

After Discussion receives exact authority, the Host Adapter detects the current Claude CLI's real capabilities and chooses one tier:

| Capability tier | Behavior |
| --- | --- |
| `background_session` | Run the equivalent of `claude --bg --agent wishgraph-worker --worktree <unique> --settings <ephemeral-json> "执行 <task-id> 任务"`, query `claude agents --json --all --cwd <project>`, and persist the stable session ID plus the observed worktree. |
| `forked_subagent` | Use only for short, low-risk, read-only-by-default assistance; it is not a Formal business Worker. |
| `manual_command_only` | Print the project directory, copy-ready Codex/Claude startup commands, and the final `执行 <task-id> 任务` line; then stop Discussion execution. |

`background_session` requires all of the following:

- The current CLI supports `--bg`, `agents --json`, `--worktree`, and `--settings`.
- The managed `wishgraph-worker` Agent definition exists.
- The per-launch Worktree configuration exposes the shared runtime to an isolated Worker.
- The exact Task is authorized and its record matches the current `HEAD`.

A successful `claude --bg` return does not make the Task `running`. WishGraph must persist the real session ID, and the Worker must acquire a Claim bound to Task, session, branch, absolute worktree, scope, and validation plan after entering its actual worktree.

Any detection or launch failure strictly falls back to a copy-ready cross-host handoff whose final line remains:

```text
执行 <task-id> 任务
```

Discussion never implements business code because Claude background support is unavailable.

## Inspect and control a background Worker

```bash
claude agents --json --all --cwd /path/to/project
claude agents --cwd /path/to/project
claude --resume <full-session-id>
```

- `claude agents --json` provides structured session state for WishGraph refresh.
- `claude agents --cwd` opens Claude's native interactive view for inspection and control.
- `claude --resume` continues a selected conversation by its full stable session ID when recovery is appropriate.
- Current Claude Code does not expose `claude logs`, `claude attach`, or `claude stop` subcommands. WishGraph does not call or advertise them; a created session that fails verification is recorded as `manual_intervention_required`.
- `/tasks` only displays background work associated with the current Claude session. It does not create a WishGraph Task or grant a Claim.

WishGraph enters Integration only when terminal Task state, an immutable Run Report, validation, and released Claim evidence agree.

## After a Worker finishes

Normal Claim release writes one pending notification in the shared Git runtime. Discussion consumes and marks it read on the next SessionStart, prompt, or explicit refresh.

This is pull-on-activation, not real-time push. WishGraph runs no daemon, terminal polling, cross-terminal IPC, or automatic popup. Safe results enter Discussion-local Integration automatically; conflict, risk, and product choices return as concrete questions.

## Is `CLAUDE.md` required?

No. The normal Skill + `--setup-project` path already provides activation, Hooks, the Worker definition, and project-state loading.

The [`CLAUDE.md`](CLAUDE.md) file in this directory is an optional always-loaded instruction bridge for teams that deliberately want every Claude session to know the WishGraph role rules. Copying it does not activate a project or install runtime, Hooks, or mechanical gates.

## Troubleshooting

If `Start discussion` does not respond after reopening the session:

1. Say `Check WishGraph status` to run the fixed-path, read-only WishGraph Doctor.
2. Run `claude doctor` when Claude Code itself may be misconfigured.
3. If the global Skill is newer than the project runtime, say `Update this project's WishGraph`.
4. If only the Claude adapter is missing, say `Repair WishGraph hooks for this host`.

Updating the global Skill never silently overwrites an existing project's `.wishgraph/hooks/`. Unknown or locally modified runtime files stop for review.

## Boundaries

- Hooks never launch Agents. The Host Adapter acts only after exact Task authority already exists.
- Explore, Plan, `/fork`, and hidden subagents are Helpers by default and cannot receive a Worker Claim.
- Write/build gates cover Claude tools exposed to Hooks; they are not an operating-system sandbox.
- A Claude Code session is mechanically protected only when the Claude Adapter is installed and loaded; `mode: enforce` alone cannot intercept it.
- One Worker can bind only one Task or Revision at a time and must release the old Claim before reuse.
- Claims coordinate worktrees sharing one local Git common directory; they are not distributed locks across machines.

See the [state-machine specification](../../docs/orchestration-state-machine.md) and [External-Memory Hooks](../../docs/memory-sync-hooks.md) for protocol details.

Official references: [Claude Code Skills](https://code.claude.com/docs/en/skills) · [`CLAUDE.md` memory](https://code.claude.com/docs/en/memory)
