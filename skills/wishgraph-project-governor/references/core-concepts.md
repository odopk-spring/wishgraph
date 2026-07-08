# WishGraph Core Concepts

## Wish

A low-bandwidth human expression of direction, dissatisfaction, taste, or goal. It can be vague: "make this smoother", "this feels wrong", "do not make it too complex".

## Intent Compiler

The process that translates a wish into operational artifacts:

```text
Wish -> Requirements -> Spec -> Task -> Patch -> Probe -> Report
```

The compiler must preserve uncertainty. If the wish is ambiguous, the agent should ask targeted questions or encode assumptions explicitly.

## Spec Graph

The durable description of what the project should be. It may live in PRDs, architecture docs, issue specs, task files, schemas, tests, or design notes.

## Task Graph

The ordered set of small execution units. Each task should have a clear dependency, validation surface, and rollback boundary.

## Dependency Map

The map from features to files, modules, contracts, symbols, tests, and runtime probes. `CODEMAP.md` is the lightweight default.

## Causal Log

The record of why the project changed: decisions, task specs, commits, validation reports, bug reports, failed attempts, and repair notes.

## Probe

Any check that can reveal whether the system still satisfies the spec: tests, builds, linters, screenshots, performance traces, health checks, logs, or manual scripts.

## Review Window

The compressed interface for the human reviewer. It should show what the AI understood, what it plans to do, what changed, how it was verified, what failed, and where human judgment is needed.

## Anti-Black-Box Rule

An agent should be able to answer:

- What intent did it infer?
- What spec did it compile?
- What files and symbols did it touch?
- Why were these changes minimal?
- How was behavior verified?
- What risk remains?
