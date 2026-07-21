# Compatibility and support matrix

WishGraph v0.1.0 requires Git and Python 3.9 or newer. It installs no Python
packages and does not require the governed project itself to use Python.

## Automated coverage

| Platform | Python | Coverage |
|---|---:|---|
| Ubuntu latest | 3.9, 3.13 | Full unit suite, hook compilation, Bash syntax |
| macOS latest | 3.9, 3.13 | Full unit suite, hook compilation, Bash syntax |
| Windows latest | 3.13 | Full unit suite, native PowerShell installation smoke test |

## Host surfaces

| Host | Beta support | Notes |
|---|---|---|
| Codex | Supported | Native inspectable Agent creation depends on the active Codex surface; otherwise WishGraph emits a manual handoff. |
| Claude Code CLI | Supported | Managed background execution requires compatible `claude agents`, `--bg`, Agent, and Worktree capabilities. |
| Other hosts | Portable manual path | Requires a genuinely inspectable independent Worker window or thread. |

## Release acceptance still requiring human evidence

Before publishing v0.1.0, record at least one complete install → Discussion →
Worker → validation → Integration → reopen flow for:

- Windows with Codex;
- macOS or Linux with Codex;
- macOS or Linux with Claude Code;
- one safe upgrade from an older generated runtime;
- one explicit strict-mode flow.

Record exact host versions and limitations in the release checklist. Automated
simulation is not a substitute for those real-host observations.
