# NNN - Task Title

Spec source: Link or summarize the approved requirement.
Dependencies: List required prior tasks, migrations, or decisions.
Language mode: Follow `prompts/DISCUSSION_AI.md` unless this task explicitly overrides it.

The JSON block is the machine-readable task lifecycle source. Keep `worker_creation_authorized` false until the user explicitly authorizes this visible Worker. For `parallel_batch` or `high_risk`, use `requires_explicit_user_confirmation` as the integration policy.

<!-- wishgraph:task-state:start -->
```json
{
  "schema_version": 1,
  "kind": "task",
  "task_id": "NNN-short-slug",
  "status": "draft",
  "work_type": "sequential",
  "batch_id": null,
  "run_report": "reports/runs/NNN-short-slug.md",
  "worker_creation_authorized": false,
  "integration_policy": "inherited_task_approval"
}
```
<!-- wishgraph:task-state:end -->

## Intent

State the user-visible goal in one short paragraph. This section must be understandable without reading chat history.

## Current State

Summarize the relevant repo facts discovered from files, tests, logs, or docs.

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
