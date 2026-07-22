# Changelog

All notable WishGraph changes are recorded here. Product releases use semantic
version tags; the project-local runtime keeps its own independent integer version
for safe upgrades.

## [0.1.1] - 2026-07-22

### Fixed

- Allowed `warn` integrations to absorb the immutable Run Report from the
  preceding Worker closeout commit when the same change moves its Task from
  `completed` to `integrated`.
- Kept existing-report validation strict for report format, Task ID, attempt,
  safety fields, readiness, and duplicate integration references.

### Compatibility

- Kept `enforce` Claim, canonical Run, Integration lease, and new-report gates
  unchanged.

## [0.1.0] - 2026-07-21

First public beta release candidate.

### Added

- File-backed PRD, architecture, code map, conventions, Tasks, Revisions, Run
  Reports, and current Project Status.
- Explicit Discussion, inspectable Worker, and Discussion-local Integration flow.
- Codex and Claude Code adapters with advisory `warn` and opt-in `enforce` modes.
- Bound Claims, canonical execution Runs, Integration leases, notifications, and
  exact Task/Revision identity checks.
- Safe project activation, Doctor diagnostics, atomic runtime upgrades, and
  current-host adapter repair.
- Cross-platform installers for macOS, Linux, and Windows with Python 3.9+.

### Performance

- Added a cold-process benchmark for ordinary tool gates, commit gates,
  SessionStart, Discussion dispatch, and source-tree scaling.
- Added direct Git metadata reads and a lightweight PreToolUse entry path to keep
  ordinary gates independent of repository size and below their latency budget.

### Known limitations

- This is a public beta, not a stable v1 compatibility promise.
- Host Hooks are tool-level gates, not an operating-system sandbox. Read
  interception remains host-capability dependent.
- Claims coordinate worktrees sharing one local Git common directory; they are
  not distributed locks across machines.
- Background completion is consumed on the next Discussion activation or refresh;
  WishGraph intentionally runs no daemon or cross-window popup service.
- Broader real-project and host-version acceptance evidence is still required
  before v1.

[0.1.1]: https://github.com/odopk-spring/wishgraph/releases/tag/v0.1.1
[0.1.0]: https://github.com/odopk-spring/wishgraph/releases/tag/v0.1.0
