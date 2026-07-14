# Run Report

Create one new file from this template for each worker execution. Use `reports/runs/<work-unit-id>.md`. Never reuse or overwrite an earlier run report.

## Work Unit

- Unit: Task ID or `ad-hoc/YYYYMMDD-HHMM-short-slug`
- Mode: Formal / Ad-hoc
- Date:
- Agent:
- Branch / worktree:

The JSON block below is the machine-readable source for lifecycle state. Keep narrative evidence in the sections that follow. Use `null` for a sequential Batch ID.

Use `change_class: micro` only for an independent ad-hoc unit with no API, schema, persistence, security, permission, billing, deletion, migration, dependency, or cross-module-contract impact. List every changed path. Competitive candidates record their objective score only when the Task defines a complete scorecard; set `selection_requires_judgment: true` for preferences or close tradeoffs.

<!-- wishgraph:run-state:start -->
```json
{
  "schema_version": 1,
  "kind": "run",
  "task_id": "001",
  "attempt": 1,
  "unit": "NNN-short-slug",
  "status": "completed",
  "work_type": "sequential",
  "execution_mode": "exclusive",
  "batch_id": null,
  "changed_paths": [],
  "public_api_change": false,
  "schema_change": false,
  "persistence_change": false,
  "security_impact": false,
  "permission_change": false,
  "billing_impact": false,
  "deletion_change": false,
  "migration_change": false,
  "dependency_change": false,
  "cross_module_contract_change": false,
  "change_class": "formal",
  "candidate_score": null,
  "selection_requires_judgment": false,
  "integration_authorization": "inherited_task_approval",
  "integration_readiness": "ready",
  "scope_check": "pass",
  "conflict_status": "none",
  "new_decision": false,
  "validation": {
    "build": "n/a",
    "tests": "pass",
    "manual": "n/a"
  }
}
```
<!-- wishgraph:run-state:end -->

## Summary

Briefly describe what changed and why.

## Files Changed

| File | Reason |
|---|---|
| `path/to/file` | Change summary |

## Validation

| Check | Command / Scenario | Result | Evidence |
|---|---|---|---|
| Build | `<command>` | Pass / Fail / N/A | Key output or concrete N/A reason |
| Tests | `<command>` | Pass / Fail / N/A | Key output or concrete N/A reason |
| Manual | `<scenario>` | Pass / Fail / N/A | Notes or concrete N/A reason |

## Risk Notes

- Residual risk:
- Unrun checks:
- Follow-up recommended:

## Shared Memory Impact Proposal

Worker agents do not edit shared project memory. Use exactly `Integrate` when the integration agent should update the file, or `N/A` with a concrete reason.

| File | Result | Reason |
|---|---|---|
| `PRD.md` | Integrate / N/A | Product behavior, scope, roadmap, progress, or why no change is needed |
| `ARCHITECTURE.md` | Integrate / N/A | Dependency, ownership, data-flow impact, or why none |
| `CODEMAP.md` | Integrate / N/A | File, symbol, contract, status, probe impact, or why none |
| `CONVENTIONS.md` | Integrate / N/A | Workflow-rule impact, or why none |
| `prompts/DISCUSSION_AI.md` | Integrate / N/A | Result the integration agent should expose to discussion AI, or why none |
| `prompts/EXECUTION_AI.md` | Integrate / N/A | Stable execution-rule impact, or why none |
| `prompts/INTEGRATION_AI.md` | Integrate / N/A | Stable integration-rule impact, or why none |

## Integration Notes

- Merge dependency:
- Conflict warning:
- Facts the integration agent must preserve:
- Reason integration is safe, blocked, or needs a user decision:
