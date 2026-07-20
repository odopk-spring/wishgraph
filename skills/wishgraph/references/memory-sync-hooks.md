# External-Memory Sync Hooks

Use this reference when configuring, inspecting, debugging, or benchmarking the project-local WishGraph runtime. Read `installation.md` for prerequisite and setup decisions.

## Contents

- Runtime boundary and events
- Installed files and configuration
- Checker and status commands
- Mechanical enforcement limits
- Performance targets and benchmark
- Failure and recovery

## Runtime Boundary

Hooks enforce mechanical authority and external-memory closeout. They do not write semantic project memory, choose product meaning, select parallelism, launch Workers, merge branches, replace human review, or persist ordinary diagnostics.

The stable entrypoint is `.wishgraph/hooks/memory_sync.py`. Its implementation keeps four public boundaries. Native Worker and tool-gate providers remain private behind the Host Adapter:

```text
workflow_state.py   typed state and parsing
policy.py           pure transition and gate decisions
host_adapter.py           only public host boundary
codex_worker_provider.py  private Codex native-thread implementation
claude_worker_provider.py private Claude background-session implementation
tool_gate_provider.py     private PreToolUse classification and authority gate
git_state.py              Git facts, canonical Runs, Claims, sessions, and Integration leases
```

## Hook Events

### UserPromptSubmit

Only after `.wishgraph/config.json` enables the project, route explicit entry commands. Low-risk Discussion entry and status refresh may normalize case, whitespace, terminal punctuation, and bounded polite wrappers; Task authority remains strict and exact. In Discussion, an exact Task command creates an authorized Run and asks the current host to route an independent Formal Worker. In an ordinary neutral window, it creates the same Run and binds the current window as Worker after Claim acquisition, without spawning another Worker. Hooks never create Agents themselves. Short approvals are accepted only through one persisted `expected_transition`.

When the Hook cannot resolve the whole prompt to one allowed command, it emits no route and does not mutate session state. The original prompt continues to the Agent. The Agent may ask whether the user wants Discussion or refresh, but an ambiguous execution request must be answered with a request for the exact command, such as `执行 012 任务`; Agent interpretation cannot manufacture authorization.

The default Discussion entry reads only the current Project Status sections, session runtime, and pending notifications. It does not build the active integration index or maintain a second dynamic prompt snapshot. Exact Task execution narrows candidates by canonical filename before reading bodies, then reads only the exact Task and its declared dependencies. Exact Revision routing reads only that parent's Revision family. Full active/history scans remain explicit status or recovery operations.

### SessionStart

Create or load a neutral session and run the worktree external-memory safety check. Stay silent on a normal start. Report only pending recovery, integration, failure recovery, or a decision that needs the user; never activate Discussion or inject its full prompt.

Use explicit `开始讨论` / `Start discussion` or project refresh to load Discussion context. A continuously open Discussion receives new state only through a supported resume event or refresh.

### PreToolUse

Gate:

- Business writes.
- Implementation build/test commands.
- Dependency installation.
- Task, Revision, and shared-state writes.
- Merge and commit operations.

Ordinary non-commit operations use the current Session Role, live Worker Claim, or Integration lease. Commit operations also check staged closeout. Deny implicit-staging commit flags such as `git commit -a` because they bypass bounded staging review.

### Stop And TaskCompleted

Inspect closeout before an agent stops. In `enforce`, block when required Task/Revision state, Run Report, validation, or shared-memory impact is missing. In `warn`, ordinary closeout incompleteness stays non-blocking and silent. Authority and state-integrity boundaries still fail closed in every active mode.

Claude Code may also expose `TaskCompleted`; keep it as a host adapter event rather than portable workflow meaning.

### Output Ownership

- `PreToolUse` stays silent unless the operation is actually denied.
- `SessionStart` reports only recovery, pending integration, failure recovery, or a user decision.
- `Stop` / `TaskCompleted` emit at most one closeout result through the channel required by that host event.
- `status`, `doctor`, and `check` are explicit CLI diagnostics and may show detailed paths and internal state.

`mode` decides whether an ordinary mechanical finding blocks; event ownership decides whether and where it is shown. A Hook invocation uses one output channel only. Normal Hook messages state impact and next action, while raw Claim IDs, commits, worktrees, runtime phases, and checker errors stay in explicit diagnostics.

## Installed Files

```text
.wishgraph/config.json
.wishgraph/hooks/memory_sync.py
.wishgraph/hooks/git_state.py
.wishgraph/hooks/workflow_state.py
.wishgraph/hooks/policy.py
.wishgraph/hooks/host_adapter.py
.wishgraph/hooks/codex_worker_provider.py
.wishgraph/hooks/claude_worker_provider.py
.wishgraph/hooks/tool_gate_provider.py
.wishgraph/hooks/runtime-manifest.json
.codex/hooks.json        # Codex
.codex/agents/wishgraph-worker.toml  # managed Codex Formal Worker
.claude/settings.json    # Claude Code
.claude/agents/wishgraph-worker.md  # managed Claude background Worker
```

The runtime manifest records one generated runtime version and SHA-256 fingerprints for the four public boundary files, stable entrypoint, and any private Host Adapter provider. Doctor compares only those fixed paths. The installer merges host JSON, removes obsolete WishGraph handlers, preserves unrelated hook groups, and refuses to overwrite a locally modified generated runtime unless `--force-assets` is explicit. Codex users must trust the repository and review `/hooks`.

Updating the global Codex or Claude Skill refreshes the bundled runtime for future installs, but does not rewrite an existing project's `.wishgraph/hooks/` copy. The safe upgrade command repairs missing metadata for current bundled files or replaces a bundled-known generated version, and rolls back all runtime/config writes on failure. Unknown, incomplete, newer, or locally modified copies stop for review; `--force-assets` remains a deliberate human override.

The two host files are thin adapters over the same `.wishgraph/hooks/` runtime. Claude setup defaults an unset Worktree `baseRef` to `head` and adds `.wishgraph` to `worktree.symlinkDirectories`, preserving existing entries and an explicit existing baseRef. Native background launch is available only with `baseRef: head` and an authorized Task record already matching current `HEAD`; otherwise it uses the manual command. This lets an isolated Worker run the same local runtime while its Claim binds the actual Worker branch/worktree. A Worker Claim records both the machine hostname and `agent_platform`; an idle thread is reusable only by the same agent platform. Switching between Codex and Claude keeps repository truth, Tasks, reports, Claims, and status portable, but never sends a Codex route to a Claude thread ID or vice versa.

`required_hosts` in project config is the selected protection scope; `current_host` is only the Agent invoking this Hook. Before a Formal Worker is created or acquires/rebinds a Claim, the current host must be selected, its Adapter and managed Worker definition must be present, and a recent `SessionStart` or `UserPromptSubmit` receipt must match the current runtime version and postdate Adapter installation. A Worker write/build request is denied when that check fails. Helper agents never gain authority from this check.

The canonical execution record lives at `.git/wishgraph/runs/<work-unit>-attempt-N.json`. It alone owns authorization, Worker binding, Claim ID, terminal commit/report evidence, risk outcome, and Integration result. Session runtime, host observation, Project Status, and notifications are bounded projections. Worker reminders still use one inbox; Claim release writes the Run first and then one idempotent notification. Hooks never launch a daemon, poll another terminal, open a popup, or parse prose as terminal evidence.

A normal terminal Hook blocks while the Worker still holds an active Claim. Forced process termination can bypass every Hook; with daemon and polling explicitly excluded, the remaining recoverable signal is the stale Claim or structured host-session state discovered at the next Discussion inspection.

`SessionStart` and `UserPromptSubmit` record bounded host-liveness evidence outside the worktree:

```text
.git/wishgraph/host-observations/<host>/session-start.json
.git/wishgraph/host-observations/<host>/user-prompt-submit.json
```

Each receipt contains only host, event, runtime version, and observation time. Doctor reports `unverified`, `stale`, `observed`, or `confirmed_recently` by comparing these receipts with the installed runtime and current host adapter. This proves only that the host recently invoked WishGraph; it is not a permanent trust guarantee. Do not write a receipt from `PreToolUse`, enumerate logs, or add files to the worktree.

Use `warn` for first adoption. Use `enforce` only after a clean successful closeout. Add the Git pre-commit fallback for strict enforcement outside host lifecycle hooks. Follow `installation.md` for commands and prerequisites.

## Configuration

Key settings include:

- `mode`: `off`, `warn`, or `enforce`.
- `required_hosts`: non-empty subset of `codex` and `claude`; use `mode: off` instead of an empty list.
- `paths`: canonical governance, Task, Revision, report, and prompt locations.
- `required_impact_rows`: shared-memory files that require `Integrate` or concrete `N/A` evidence.
- Project Status size limits and the explicit Discussion context size limit.
- `orchestration_gate_enabled` and host-dependent read-gate mode.

WishGraph reads `tasks/*.md`, `tasks/revisions/*.md`, and `reports/PROJECT_STATUS.md`. Task, Revision, Run Report, and Project Status records require their structured state blocks. `paths.run_report_template` allocates one portable repository-relative report path when a work unit is authorized; `paths.run_report_glob` validates it. The defaults remain `reports/runs/{work_unit_id}-attempt-{attempt}.md` and `reports/runs/*.md`. Pre-release hidden Task paths, `reports/DEV_REPORT.md`, old field aliases, and configuration without `required_hosts` are intentionally not inferred. Reactivate the project or regenerate the affected record instead of maintaining two truth formats.

## Commands

Run from the project root:

```bash
python3 PATH_TO_SKILL/scripts/install_project_hooks.py --target . --host codex --doctor --json
python3 PATH_TO_SKILL/scripts/install_project_hooks.py --target . --upgrade --json
python3 PATH_TO_SKILL/scripts/install_project_hooks.py --target . --host codex --repair-host-adapter --json
python3 .wishgraph/hooks/memory_sync.py check --scope worktree
python3 .wishgraph/hooks/memory_sync.py check --scope staged
python3 .wishgraph/hooks/memory_sync.py status
python3 .wishgraph/hooks/memory_sync.py status --task 012
python3 .wishgraph/hooks/memory_sync.py status --full
python3 .wishgraph/hooks/memory_sync.py claim inspect
python3 .wishgraph/hooks/memory_sync.py integration-lease inspect
python3 .wishgraph/hooks/memory_sync.py codex-worker prepare 012 --discussion-session-id <discussion-session-id>
python3 .wishgraph/hooks/memory_sync.py codex-worker register 012 --discussion-session-id <discussion-session-id> --thread-id <real-id> --inspectable --controllable --independent-context
python3 .wishgraph/hooks/memory_sync.py codex-worker observe --discussion-session-id <discussion-session-id> --thread-id <real-id> --state completed
python3 .wishgraph/hooks/memory_sync.py claude-worker capability
python3 .wishgraph/hooks/memory_sync.py claude-worker launch 012 --discussion-session-id <discussion-session-id>
python3 .wishgraph/hooks/memory_sync.py claude-worker refresh --discussion-session-id <discussion-session-id>
```

Codex `prepare` returns the bounded native-Agent payload but does not create an Agent. The active host creates the thread and calls `register` only with the real stable ID and control attestations; only then does Discussion enter `waiting_for_worker`. `observe` accepts a structured host state, but Integration still requires the durable Task terminal state, Run Report, and released Claim. Spawn failure uses `codex-worker fail` and prints the compact cross-host manual handoff.

The current Discussion runs the Claude Host Adapter command directly; it must not delegate that command to `Task`, `Agent`, `/fork`, or an ordinary background subagent. The adapter invokes the equivalent of `claude --bg --agent wishgraph-worker --worktree <unique> --settings <ephemeral-worktree-json> "执行 012 任务"` only after the Discussion runtime and the exact Task record in HEAD both prove authorization. The managed Worker stays `starting` / `awaiting_claim` until its Claim matches the real full Claude session ID, originating Discussion ID, actual branch, and absolute worktree. Claim failure stops execution and records a recoverable failure state. The extra mechanics stay hidden from users and never rewrite their settings. Capability or launch failure prints the project directory, copy-ready Codex and Claude Code startup commands with resolved profiles, and the final Task phrase. Refresh queries `claude agents --json --all --cwd <project>` and never parses conversation prose as terminal evidence. Current Claude Code exposes interactive inspection and control through `claude agents --cwd <project>` and conversation recovery through `claude --resume <full-session-id>`; do not advertise nonexistent `claude logs`, `claude attach`, or `claude stop` subcommands.

Use `flow-plan` for read-only reducer inspection. Public `session set` cannot establish roles or phases, and public `session apply` accepts diagnostic metadata only. Use `session transition SESSION_ID EVENT --data-json ...` for a semantic Discussion transition; it reads current state, invokes the reducer, persists only its patch, and creates a one-time Integration grant only after durable evidence passes. Internal host code may call the atomic patch primitive after it already owns an accepted reducer plan.

PreToolUse classifies bounded WishGraph control commands before ordinary write/build checks. Workers may control only their own Claim; Discussion may control only its own semantic transition and Integration lease; Helpers cannot acquire either. Direct role promotion, another session's runtime, mixed control actions, and Worker lease control are denied even in `warn` mode.

Use `status` as read-only evidence. Its default active view reads current Task/Revision candidates, changed local reports, Claims, and exact report paths across refs. `--task` filters one exact Task; only `--full` enumerates historical report trees. No status view authorizes a merge.

## Mechanical Gate Boundary

Require:

```text
write/build gate: required
read gate: host capability dependent
```

Business writes and implementation validation require a Claim bound to the current work unit, branch, absolute worktree, and session. Merge resolution, combined validation, shared-state writes, and integration commit require a bound Discussion-local Integration lease.

Native write tools, recognized shell build/write commands, and MCP tools whose names expose write/edit/create/delete/update intent are gated. A shell script or opaque MCP tool can hide side effects from name-based interception, so this is a host-tool gate rather than an operating-system sandbox. An uninstalled Adapter cannot intercept anything in that host, even when project config says `mode: enforce`. Do not describe prompt instructions or opaque tools as hard enforcement. When a host cannot intercept every source-read tool, report that limitation honestly.

Ordinary non-commit PreToolUse must remain bounded and avoid full source-tree enumeration. SessionStart performs a broader worktree check and has a separate latency budget.

## Performance Baseline

Use these regression budgets:

```text
SKILL.md                          < 15-20 KB
PreToolUse p95                   < 200 ms
SessionStart p95                 < 500 ms
Discussion dispatch p95         < 3,000 ms
non-commit PreToolUse bulk delta <= 25 ms
```

Dispatch latency means exact user command to durable Run authorization plus a copy-ready Host Adapter route. Native host thread creation and model startup happen after this boundary and are reported as `starting` until a real thread/session ID and Claim exist.

Run cold Python subprocesses and nearest-rank p95 with the bundled script:

```bash
python3 skills/wishgraph/scripts/benchmark_hooks.py \
  --warmup 10 \
  --iterations 100 \
  --rounds 3 \
  --bulk-files 20000 \
  --enforce \
  --json-out /tmp/wishgraph-hook-latency.json
```

The temporary fixture covers passthrough, neutral-write denial, Worker-write allowance, staged commit, existing/fresh SessionStart, and repeated Discussion dispatch. It then adds a large untracked source tree and reruns ordinary non-commit gates.

Keep the boundary exact:

- Ordinary non-commit PreToolUse must not enumerate tracked or untracked source trees. It may inspect the requested operation, session runtime, bounded Claims, branch/worktree binding, and configured gate files.
- Commit PreToolUse may inspect staged state but not unrelated untracked source files.
- SessionStart uses the worktree external-memory check and Git's untracked query; measure it separately rather than claiming it never inspects worktree state.
- Default status may scan configured Task/Revision records but resolves only active candidate report paths across refs. `status --full` may enumerate historical report locations. Neither recursively parses business source.

Keep non-timing I/O-contract tests in the normal suite. Fail ordinary PreToolUse if it invokes Git `status`, `diff`, `ls-files`, `ls-tree`, or `for-each-ref`, or uses `os.walk`, `Path.rglob`, or recursive `**` glob. Allow bounded Claim `*.json` scans.

Do not put wall-clock assertions in ordinary unit tests. If absolute p95 fails but the I/O contract passes, repeat three rounds and record environment variance. Treat a bulk delta failure as source-tree coupling. Repair the hot path before raising thresholds. Do not commit machine-specific JSON as a universal result.

## Failure And Recovery

- Invalid configuration: report the specific field and stop semantic claims.
- Missing or outdated current-host adapter: repair only that host after Doctor confirms a current runtime.
- Current adapter with no recent host receipt: reopen the Agent session. If it still does not respond, use `/hooks` in Codex or `claude doctor` in Claude Code CLI.
- Recognized older runtime: use the atomic safe upgrade; a failed write restores the previous runtime, manifest, and config.
- Modified generated runtime: compare before using `--force-assets`; preserve intentional local changes.
- Incorrect repository rule: switch to `warn` while repairing configuration rather than fabricating reports.
- Missing or malformed structured block: repair the durable record; do not silently fall back when a block is present but invalid.
- Stale Claim or lease: preserve it as evidence and use the explicit recovery action.
- Performance regression: run the bundled benchmark and I/O-contract tests before changing thresholds or Hook behavior.
