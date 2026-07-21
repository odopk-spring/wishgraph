# WishGraph v0.1.0 Public Beta

WishGraph turns natural-language project intent into bounded Tasks, inspectable
Worker execution, validation evidence, and current repository state for Codex and
Claude Code.

This release is a **prerelease public beta**. It is suitable for evaluation and
real project feedback, but does not yet carry a stable v1 compatibility promise.

## Highlights

- Opt-in, file-backed project governance with compact cross-session handoff.
- Exact Task authorization and independent, inspectable Worker routing.
- Advisory `warn` mode by default and explicit mechanical `enforce` mode.
- Claims, immutable Run Reports, validation, safe Integration, and Revisions.
- Codex, Claude Code CLI, and host-neutral manual fallback paths.
- Atomic project runtime upgrades that preserve modified or unknown copies for
  human review.

## Install

Use the tagged commands in the
[README](https://github.com/odopk-spring/wishgraph/tree/v0.1.0#install-in-60-seconds).
They install the immutable `v0.1.0` source rather than the moving `main` branch.

## Compatibility and boundaries

- Git and Python 3.9+ are required; no Python packages are installed.
- Hooks are host-tool gates, not an operating-system sandbox.
- Read interception depends on host capabilities.
- Claims coordinate only worktrees sharing one local Git common directory.
- WishGraph runs no daemon and does not automatically pop up another window when
  a Worker completes.

See [COMPATIBILITY.md](https://github.com/odopk-spring/wishgraph/blob/v0.1.0/COMPATIBILITY.md),
[PRIVACY.md](https://github.com/odopk-spring/wishgraph/blob/v0.1.0/PRIVACY.md), and
[SECURITY.md](https://github.com/odopk-spring/wishgraph/blob/v0.1.0/SECURITY.md).

## Verification

Release artifacts include `SHA256SUMS`. The tag workflow runs the full test suite,
tag-pinned installation smoke tests on Ubuntu, macOS, and Windows, plus three-round
cold-process performance benchmarks before producing those artifacts.

The ordinary PreToolUse target remains below 200 ms. The release gate uses 200 ms
on Ubuntu/macOS and 250 ms on GitHub-hosted Windows runners to account for observed
cold-process runner variance.

## Feedback

Use GitHub Issues for reproducible bugs and concrete feature requests. Report
suspected vulnerabilities privately according to `SECURITY.md`.
