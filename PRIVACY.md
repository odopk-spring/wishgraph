# Privacy and local data

WishGraph does not implement analytics, telemetry, advertising identifiers, or a
background network service.

Project truth is stored in repository files. Transient execution state, Claims,
session identifiers, host observations, and notifications are stored under the
repository's Git common directory. Records may include local absolute worktree
paths, branch names, commit IDs, host type, machine hostname, and Agent
thread/session identifiers.

WishGraph installers contact GitHub to download the selected release. Managed
Claude Code execution invokes the user's installed Claude CLI; Codex and Claude
may have their own data handling and telemetry policies outside WishGraph's
control.

Before publishing a repository, review committed Tasks and Run Reports for
private source paths, prompts, logs, personal data, credentials, or proprietary
context. Never place secrets in WishGraph records.
