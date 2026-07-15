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

Hooks enforce mechanical authority and external-memory closeout. They do not write semantic project memory, choose product meaning, select parallelism, launch Workers, merge branches, or replace human review.

The stable entrypoint is `.wishgraph/hooks/memory_sync.py`. Its implementation remains split into four boundaries:

```text
workflow_state.py   typed state and parsing
policy.py           pure transition and gate decisions
host_adapter.py     host events, CLI, and output mapping
git_state.py        Git facts, Claims, sessions, and Integration leases
```

## Hook Events

### UserPromptSubmit

Only after `.wishgraph/config.json` enables the project, route explicit entry commands. Low-risk Discussion entry and status refresh may normalize case, whitespace, terminal punctuation, and a bounded allowlist of polite wrappers before exact alias lookup. Task execution, stop, retry, takeover, and exact IDs remain strict and never receive that normalization. Missing config and `mode: off` are silent no-op states; `开始讨论` never installs or enables WishGraph. A neutral execution window receives the exact Task route and must acquire its Claim before business work. A Discussion window routes a visible Worker; Claude Code and failed automatic routing expose only the exact one-line command. Short approvals are accepted only through one persisted `expected_transition`.

When the Hook cannot resolve the whole prompt to one allowed command, it emits no route and does not mutate session state. The original prompt continues to the Agent. The Agent may ask whether the user wants Discussion or refresh, but an ambiguous execution request must be answered with a request for the exact command, such as `执行 012 任务`; Agent interpretation cannot manufacture authorization.

### SessionStart

Create or load a neutral session and run the worktree external-memory safety check. Default `safety_only` mode reports pending or invalid state without activating Discussion or injecting its full prompt.

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

Inspect closeout before an agent stops. In `enforce`, continue or block when required Task/Revision state, Run Report, validation, or shared-memory impact is missing. In `warn`, report the problem without hard blocking.

Claude Code may also expose `TaskCompleted`; keep it as a host adapter event rather than portable workflow meaning.

## Installed Files

```text
.wishgraph/config.json
.wishgraph/hooks/memory_sync.py
.wishgraph/hooks/git_state.py
.wishgraph/hooks/workflow_state.py
.wishgraph/hooks/policy.py
.wishgraph/hooks/host_adapter.py
.wishgraph/hooks/runtime-manifest.json
.codex/hooks.json        # Codex
.claude/settings.json    # Claude Code
```

The runtime manifest records one generated runtime version and SHA-256 fingerprints for all five runtime files. Doctor compares only those fixed paths. The installer merges host JSON, removes obsolete WishGraph handlers, preserves unrelated hook groups, and refuses to overwrite a locally modified generated runtime unless `--force-assets` is explicit. Codex users must trust the repository and review `/hooks`.

Updating the global Codex or Claude Skill refreshes the bundled runtime for future installs, but does not rewrite an existing project's `.wishgraph/hooks/` copy. The safe upgrade command repairs missing metadata for current bundled files or replaces a bundled-known generated version, and rolls back all runtime/config writes on failure. Unknown, incomplete, newer, or locally modified copies stop for review; `--force-assets` remains a deliberate human override.

The two host files are thin adapters over the same `.wishgraph/hooks/` runtime. A Worker Claim records both the machine hostname and `agent_platform`; an idle thread is reusable only by the same agent platform. Switching between Codex and Claude keeps repository truth, Tasks, reports, Claims, and status portable, but never sends a Codex route to a Claude thread ID or vice versa.

Use `warn` for first adoption. Use `enforce` only after a clean successful closeout. Add the Git pre-commit fallback for strict enforcement outside host lifecycle hooks. Follow `installation.md` for commands and prerequisites.

## Configuration

Key settings include:

- `mode`: `off`, `warn`, or `enforce`.
- `paths`: canonical governance, Task, Revision, report, and prompt locations.
- `required_impact_rows`: shared-memory files that require `Integrate` or concrete `N/A` evidence.
- `session_start_context_mode`: default `safety_only`; compatibility mode may provide a compact summary.
- Project Status and Discussion dynamic-block size limits.
- `orchestration_gate_enabled` and host-dependent read-gate mode.

New projects use `tasks/build/*.md`, `tasks/revisions/*.md`, and `reports/PROJECT_STATUS.md`. Legacy `.tasks/build/*.md` and a sole `reports/DEV_REPORT.md` remain readable for migration. If both standard status files exist, strict checks block until one authoritative source remains.

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
```

Use `flow-plan` to evaluate one pure state/event transition. Apply only its returned state patch through `session apply`; do not hand-edit a different semantic result.

Use `status` as read-only evidence. Its default active view reads current Task/Revision candidates, changed local reports, Claims, and exact report paths across refs. `--task` filters one exact Task; only `--full` enumerates historical report trees. No status view authorizes a merge.

## Mechanical Gate Boundary

Require:

```text
write/build gate: required
read gate: host capability dependent
```

Business writes and implementation validation require a Claim bound to the current work unit, branch, absolute worktree, and session. Merge resolution, combined validation, shared-state writes, and integration commit require a bound Discussion-local Integration lease.

Native write tools, recognized shell build/write commands, and MCP tools whose names expose write/edit/create/delete/update intent are gated. A shell script or opaque MCP tool can hide side effects from name-based interception, so this is a host-tool gate rather than an operating-system sandbox. Do not describe prompt instructions or opaque tools as hard enforcement. When a host cannot intercept every source-read tool, report that limitation honestly.

Ordinary non-commit PreToolUse must remain bounded and avoid full source-tree enumeration. SessionStart performs a broader worktree check and has a separate latency budget.

## Performance Baseline

Use these regression budgets:

```text
SKILL.md                          < 15-20 KB
PreToolUse p95                   < 200 ms
SessionStart p95                 < 500 ms
non-commit PreToolUse bulk delta <= 25 ms
```

Run cold Python subprocesses and nearest-rank p95 with the bundled script:

```bash
python3 scripts/benchmark_hooks.py \
  --warmup 10 \
  --iterations 100 \
  --rounds 3 \
  --bulk-files 20000 \
  --enforce \
  --json-out /tmp/wishgraph-hook-latency.json
```

The temporary fixture covers passthrough, neutral-write denial, Worker-write allowance, staged commit, and existing/fresh SessionStart. It then adds a large untracked source tree and reruns ordinary non-commit gates.

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
- Recognized older runtime: use the atomic safe upgrade; a failed write restores the previous runtime, manifest, and config.
- Modified generated runtime: compare before using `--force-assets`; preserve intentional local changes.
- Incorrect repository rule: switch to `warn` while repairing configuration rather than fabricating reports.
- Missing or malformed structured block: repair the durable record; do not silently fall back when a block is present but invalid.
- Stale Claim or lease: preserve it as evidence and use the explicit recovery action.
- Performance regression: run the bundled benchmark and I/O-contract tests before changing thresholds or Hook behavior.
