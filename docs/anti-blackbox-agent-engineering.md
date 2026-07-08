# Anti-Black-Box Agent Engineering

AI coding becomes dangerous when it is opaque: the agent changes files, the app seems different, and nobody can explain why or how to recover.

WishGraph treats auditability as a first-class engineering requirement.

## The Agent Must Explain

Before execution:

- What intent it inferred.
- What it believes is in scope.
- What it will not touch.
- What risks exist.
- How it will validate.

After execution:

- What files changed.
- What behavior changed.
- What checks passed.
- What checks failed or were skipped.
- What state future agents should read.

## The Project Must Remember

Use durable files:

- `CODEMAP.md` for navigation.
- `CONVENTIONS.md` for collaboration rules.
- `ARCHITECTURE.md` for boundaries.
- `.tasks/build/*.md` for executable specs.
- `reports/DEV_REPORT.md` for evidence.

## The Human Must Review The Right Layer

Humans should not need to inspect every code path every time. They should see a compressed review window that lets them judge direction, risk, and result.

## Red Flags

- The agent says "fixed" without validation.
- The task has no "do not do" section.
- The agent changes unrelated files.
- The project map is stale.
- A bug fix does not identify the polluted state.
- The agent relies on "as discussed above" instead of a file-backed spec.

## Core Claim

The future of AI engineering is not merely stronger models. It is stronger project structure around the models.
