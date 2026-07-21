# Run Report

Create one new file from this template for each worker execution. Use the configured `paths.run_report_template` (default: `reports/runs/<work-unit-id>-attempt-N.md`). Never reuse or overwrite an earlier run report.

## Work Unit

- Unit: Task ID or `ad-hoc/YYYYMMDD-HHMM-short-slug`
- Mode: Formal / Revision / Ad-hoc
- Date:
- Agent:
- Branch / worktree:

The JSON block below is the machine-readable source for lifecycle state. Keep narrative evidence in the sections that follow. Use `null` for a sequential Batch ID.

`integration_recommendation` is evidence for Discussion routing, never Worker authorization. `enforce` additionally requires a reducer-issued transition grant and Discussion-local Integration lease. In `warn`, Discussion may integrate after verifying the approved Task, this report, the result commit, validation, and risk.

Use `change_class: revision` only for a bounded Task Revision; otherwise use `formal`. Competitive candidates record their objective score only when the Task defines a complete scorecard; set `selection_requires_judgment: true` for preferences or close tradeoffs.

For a Task Revision, set `change_class: revision`, keep `task_id` as the parent Task, set the exact `revision_id`, and list every changed path. All explicit risk flags must remain false; otherwise stop and request a formal follow-up Task.

<!-- wishgraph:run-state:start -->
```json
{
  "schema_version": 1,
  "kind": "run",
  "task_id": "001",
  "revision_id": null,
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
  "privacy_impact": false,
  "permission_change": false,
  "billing_impact": false,
  "deletion_change": false,
  "migration_change": false,
  "dependency_change": false,
  "cross_module_contract_change": false,
  "change_class": "formal",
  "candidate_score": null,
  "selection_requires_judgment": false,
  "integration_recommendation": "safe_for_discussion_integration",
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

Workers do not edit shared project memory. Use one row for each configured stable-memory path (`paths.prd`, `paths.architecture`, `paths.codemap`, and `paths.conventions`). The rows below are the default layout; replace their paths when a native-lite project reuses other files. Use exactly `Integrate` when the Discussion-local Integration phase should update the file, or `N/A` with a concrete reason.

| File | Result | Reason |
|---|---|---|
| `PRD.md` | Integrate / N/A | Stable product behavior, scope, goals, or why no change is needed |
| `ARCHITECTURE.md` | Integrate / N/A | Dependency, ownership, data-flow impact, or why none |
| `CODEMAP.md` | Integrate / N/A | File, symbol, contract, status, probe impact, or why none |
| `CONVENTIONS.md` | Integrate / N/A | Project-specific engineering-rule impact, or why none |

## Integration Notes

- Merge dependency:
- Conflict warning:
- Facts the Discussion-local Integration phase must preserve:
- Reason integration is safe, blocked, or needs a user decision:
