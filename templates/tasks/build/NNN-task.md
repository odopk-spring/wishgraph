# NNN - Task Title

Spec source: Link or summarize the approved requirement.
Dependencies: List required prior tasks, migrations, or decisions.
Language mode: Follow the current project language unless this task explicitly overrides it.

The JSON block is the machine-readable task lifecycle source. Keep `worker_creation_authorized` false until the user explicitly authorizes this user-visible and inspectable Worker thread or window. `worker_execution_profiles` stores only grounded, per-Task Codex or Claude recommendations; leave a host absent to use its current default. `integration_route` describes future Discussion routing only: safe work uses `auto_in_discussion`; high-risk work uses `decision_required`. It never grants the Worker Integration authority.

Task state records only Task Lifecycle. Session Role, Flow Phase, and `expected_transition` remain orthogonal Git-common-dir runtime state.

<!-- wishgraph:task-state:start -->
```json
{
  "schema_version": 1,
  "kind": "task",
  "task_id": "001",
  "parent_task_id": null,
  "dependencies": [],
  "status": "draft",
  "work_type": "sequential",
  "batch_id": null,
  "attempt": 1,
  "execution_mode": "exclusive",
  "comparison_group": null,
  "run_report": "reports/runs/001-attempt-1.md",
  "worker_execution_profiles": {},
  "worker_creation_authorized": false,
  "integration_route": "auto_in_discussion"
}
```
<!-- wishgraph:task-state:end -->

## Intent

State the user-visible goal in one short paragraph. This section must be understandable without reading chat history.

## Current State

Summarize the relevant repo facts discovered from files, tests, logs, or docs.

## Readiness Notes

- Verified code/module/interface anchors:
- Available validation commands:
- Permission and risk boundaries:
- Unknowns or source conflicts carried into this Task:

## Change Set

| Target | Anchor | Required Change |
|---|---|---|
| `path/to/file` | `SymbolOrRouteName` | Describe the exact behavior change |

## Implementation Notes

- Keep the patch minimal.
- Use existing project patterns and helpers.
- Preserve compatibility unless this task explicitly authorizes a breaking change.

## Do Not Do

- Do not refactor unrelated files.
- Do not introduce new dependencies unless explicitly approved.
- Do not change public APIs, data schema, security, billing, or deletion behavior unless listed in Change Set.

## Validation

- [ ] Build: `<command>`
- [ ] Tests: `<command or test names>`
- [ ] Manual check: `<scenario>`
- [ ] Exactly one new immutable run report created at the path above.
- [ ] Run report records Integrate or N/A with a reason for every shared-memory file.
- [ ] Worker did not modify shared project memory or `reports/PROJECT_STATUS.md`.
- [ ] Run report records work type, batch ID, integration readiness, scope check, conflict status, and new-decision status.
- [ ] `python3 .wishgraph/hooks/memory_sync.py check --scope worktree` passes when hooks are installed.
- [ ] One atomic commit created for this task, unless the user explicitly requested no commit.
- [ ] No unrelated diffs staged.

## Rollback Boundary

Describe the smallest revertable unit. Name any generated files, migration effects, or external side effects.

## Execution Report Requirements

The final report must include:

- Files changed.
- Behavior changed.
- Validation commands and results.
- Risks or checks not run.
- Run report path, Integrate proposals, and N/A reasons.
- Any follow-up task candidates.
- Whether integration is ready, blocked, or requires a user decision.
