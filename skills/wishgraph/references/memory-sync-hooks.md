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

Hooks provide advisory checks in `warn` and enforce mechanical authority and closeout only in `enforce`. They do not write semantic project memory, choose product meaning, select parallelism, launch Workers, merge branches, replace human review, or persist ordinary diagnostics.

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

Only after `.wishgraph/config.json` enables the project, route explicit entry commands. Low-risk Discussion entry and status refresh may normalize case, whitespace, terminal punctuation, and bounded polite wrappers; Task authority remains strict and exact. In Discussion, an exact Task command asks the current host to route an independent Formal Worker. In an ordinary neutral window, it binds the current window as Worker without spawning another Worker. `enforce` requires the authorized Run and Claim first; `warn` may continue from the exact approved Task when that automation is unavailable. Hooks never create Agents themselves. Short approvals are accepted only through one persisted `expected_transition`.

When the Hook cannot resolve the whole prompt to one allowed command, it emits no route and does not mutate session state. The original prompt continues to the Agent. The Agent may ask whether the user wants Discussion or refresh, but an ambiguous execution request must be answered with a request for the exact command, such as `执行 012 任务`; Agent interpretation cannot manufacture authorization.

The default Discussion entry reads only the current Project Status sections, session runtime, and pending notifications. It does not build the active integration index or maintain a second dynamic prompt snapshot. Exact Task execution narrows candidates by canonical filename before reading bodies, then reads only the exact Task and its declared dependencies. Exact Revision routing reads only that parent's Revision family. Full active/history scans remain explicit status or recovery operations.

### SessionStart

Create or load a neutral session and run the worktree external-memory safety check. Stay silent on a normal start. Report only pending recovery, integration, failure recovery, or a decision that needs the user; never activate Discussion or inject its full prompt.

Use explicit `开始讨论` / `Start discussion` or project refresh to load Discussion context. A continuously open Discussion receives new state only through a supported resume event or refresh.

### PreToolUse

In `enforce`, gate:

- Business writes.
- Implementation build/test commands.
- Dependency installation.
- Task, Revision, and shared-state writes.
- Merge and commit operations.

In `warn`, classify the same operations only for diagnostics and never deny the tool. In `enforce`, ordinary non-commit operations use the current Session Role, live Worker Claim, or Integration lease. Commit operations also check staged closeout and deny implicit-staging flags such as `git commit -a`.

### Stop And TaskCompleted

Inspect closeout before an agent stops. In `enforce`, block when required Task/Revision state, Run Report, validation, or shared-memory impact is missing. In `warn`, every closeout and authority finding stays non-blocking and silent.

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

The runtime manifest records one generated runtime version and SHA-256 fingerprints for the four public boundary files, stable entrypoint, and any private Host Adapter provider. Doctor compares only those fixed paths. The installer merges host JSON, removes obsolete WishGraph handlers, preserves unrelated hook groups, and refuses to overwrite a locally modified generated runtime unless `--force-assets` is explicit. Codex project Hooks require the project layer and exact Hook definition to be trusted. `/hooks` is a Codex CLI command; Desktop users must open the CLI in the same project for that review instead of typing it into the Desktop chat.

Updating the global Codex or Claude Skill refreshes the bundled runtime for future installs, but does not rewrite an existing project's `.wishgraph/hooks/` copy. The safe upgrade command repairs missing metadata for current bundled files or replaces a bundled-known generated version, and rolls back all runtime/config writes on failure. Unknown, incomplete, newer, or locally modified copies stop for review; `--force-assets` remains a deliberate human override.

The two host files are thin adapters over the same `.wishgraph/hooks/` runtime. Claude setup defaults an unset Worktree `baseRef` to `head` and adds `.wishgraph` to `worktree.symlinkDirectories`, preserving existing entries and an explicit existing baseRef. Native background launch is available only with `baseRef: head` and an authorized Task record already matching current `HEAD`; otherwise it uses the manual command. This lets an isolated Worker run the same local runtime while its Claim binds the actual Worker branch/worktree. A Worker Claim records both the machine hostname and `agent_platform`; an idle thread is reusable only by the same agent platform. Switching between Codex and Claude keeps repository truth, Tasks, reports, Claims, and status portable, but never sends a Codex route to a Claude thread ID or vice versa.

`required_hosts` in project config is the selected automation scope; `current_host` is only the Agent invoking this Hook. In `enforce`, Worker creation and Claim acquisition require the selected host, current Adapter and Worker definition, and a recent matching receipt. In `warn`, these facts remain visible in Doctor but never block distribution, Claim attempts, writes, or builds.

The canonical execution record lives at `.git/wishgraph/runs/<work-unit>-attempt-N.json`. It alone owns authorization, Worker binding, Claim ID, terminal commit/report evidence, risk outcome, and Integration result. Session runtime, host observation, Project Status, and notifications are bounded projections. Worker reminders still use one inbox; Claim release writes the Run first and then one idempotent notification. Hooks never launch a daemon, poll another terminal, open a popup, or parse prose as terminal evidence.

In `enforce`, a normal terminal Hook blocks while the Worker still holds an active Claim. In `warn`, it stays silent. Forced termination leaves a stale Claim as recovery evidence; stale evidence is preserved but does not lock future distribution.

`SessionStart` and `UserPromptSubmit` record bounded host-liveness evidence outside the worktree:

```text
.git/wishgraph/host-observations/<host>/session-start.json
.git/wishgraph/host-observations/<host>/user-prompt-submit.json
```

Each receipt contains only host, event, runtime version, and observation time. Before writing it, the adapter requires a valid stable session identity and an event payload consistent with the invoked lifecycle event; a bare manual CLI call is not a receipt. Doctor reports `unverified`, `stale`, `observed`, or `confirmed_recently` by comparing these receipts with the installed runtime and current host adapter. This proves only that the host recently invoked WishGraph; it is not a permanent trust guarantee. Do not write a receipt from `PreToolUse`, enumerate logs, or add files to the worktree.

Use `warn` for first adoption and distribution-first operation, including hosts that do not run Hooks. Use `enforce` only when the user explicitly wants mechanical blocking. Add the Git pre-commit fallback only for strict enforcement outside host lifecycle hooks.

## Configuration

Key settings include:

- `mode`: `off`, `warn`, or `enforce`.
- `required_hosts`: non-empty subset of `codex` and `claude`; use `mode: off` instead of an empty list.
- `paths`: canonical governance, Task, Revision, report, and prompt locations.
- `paths.prd`, `paths.architecture`, `paths.codemap`, and `paths.conventions`: the four configured stable-memory paths; Run Report impact rows are derived from these paths rather than maintained in a second list.
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

Codex `prepare` returns the bounded native-Agent payload but does not create an Agent. The active host creates the thread and calls `register` with the real stable ID when runtime automation is available. In `enforce`, Integration requires the durable Task terminal state, Run Report, canonical result commit, and released Claim. In `warn`, a failed prepare/register/observe path falls back to the visible Worker report and result commit without a retry loop.

The current Discussion runs the Claude Host Adapter command directly when available; it must not delegate implementation to an ordinary helper. The adapter invokes the equivalent of `claude --bg --agent wishgraph-worker --worktree <unique> --settings <ephemeral-worktree-json> "执行 012 任务"` only after the Discussion runtime and the exact Task record in HEAD both prove authorization. In `enforce`, the managed Worker stays `starting` / `awaiting_claim` until its Claim matches the real full Claude session ID, originating Discussion ID, actual branch, and absolute worktree; Claim failure stops execution and records a recoverable failure. In `warn`, missing launch or Claim automation falls back to the same exact Task in a visible Worker without retry loops. The extra mechanics stay hidden from users and never rewrite their settings. Capability or launch failure prints one usable handoff. Refresh queries `claude agents --json --all --cwd <project>` and never parses conversation prose as terminal evidence. Current Claude Code exposes interactive inspection and control through `claude agents --cwd <project>` and conversation recovery through `claude --resume <full-session-id>`; do not advertise nonexistent `claude logs`, `claude attach`, or `claude stop` subcommands.

Use `flow-plan` for read-only reducer inspection. Public `session set` cannot establish roles or phases, and public `session apply` accepts diagnostic metadata only. Use `session transition SESSION_ID EVENT --data-json ...` for a semantic Discussion transition; it reads current state, invokes the reducer, persists only its patch, and creates a one-time Integration grant only after durable evidence passes. Internal host code may call the atomic patch primitive after it already owns an accepted reducer plan.

PreToolUse classifies bounded WishGraph control commands before ordinary write/build checks. In `enforce`, Workers may control only their own Claim, Discussion only its own transition and lease, and Helpers neither. In `warn`, the same findings are advisory and produce no denial.

Use `status` as read-only evidence. Its default active view reads current Task/Revision candidates, changed local reports, Claims, and exact report paths across refs. `--task` filters one exact Task; only `--full` enumerates historical report trees. No status view authorizes a merge.

## Mechanical Gate Boundary

In `enforce`, require:

```text
write/build gate: required
read gate: host capability dependent
```

In `warn`, an exact approved Task, bounded scope, validation plan, immutable Run Report, and visible Worker are sufficient; Claim and lease automation is best-effort. In `enforce`, business writes and validation require the bound Claim, while Integration actions require the bound lease.

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

Dispatch latency means exact user command to durable Run authorization plus a copy-ready Host Adapter route. Native host thread creation and model startup happen after this boundary. Strict mode reports `starting` until a real thread/session ID and Claim exist; warn mode may continue without that automation.

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
- Current adapter with no recent host receipt: in `warn`, continue distribution and show the fact only in Doctor; in `enforce`, reopen once and use the reported CLI fallback if still unconfirmed.
- Recognized older runtime: use the atomic safe upgrade; a failed write restores the previous runtime, manifest, and config.
- Modified generated runtime: compare before using `--force-assets`; preserve intentional local changes.
- Incorrect repository rule: switch to `warn` while repairing configuration rather than fabricating reports.
- Missing or malformed structured block: repair the durable record; do not silently fall back when a block is present but invalid.
- Stale Claim: preserve it as evidence but allow a new Claim. A stale Integration lease still requires explicit recovery before strict Integration.
- Performance regression: run the bundled benchmark and I/O-contract tests before changing thresholds or Hook behavior.
