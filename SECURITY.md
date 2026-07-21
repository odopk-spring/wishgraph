# Security policy

## Supported versions

During the public beta, only the latest `0.1.x` release receives security fixes.
The `main` branch is a development snapshot and is not a supported release.

| Version | Supported |
|---|---|
| Latest `0.1.x` | Yes |
| Older beta snapshots | No |

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Email
`zuelfma@foxmail.com` with:

- the affected WishGraph version or commit;
- the host, operating system, Python version, and `warn`/`enforce` mode;
- reproduction steps and expected impact;
- whether the issue can cross an authorized Task, worktree, repository, or host
  boundary;
- any suggested mitigation.

Remove credentials, private repository content, prompts, and personal data from
the report. You should receive an acknowledgement within seven days. A fix or
coordinated disclosure date depends on severity and reproducibility.

## Security boundary

WishGraph gates operations exposed through installed host adapters. It does not
replace operating-system permissions, containers, network policy, repository
access control, or human code review. An uninstalled adapter and an opaque tool
that hides its side effects cannot be mechanically intercepted.

Install a tagged release rather than `main`. Review remote installer content
before piping it to a shell, and compare release checksums when release assets are
available.
