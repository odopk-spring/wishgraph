# Project Status

This file is the current integrated project snapshot, not an append-only history. The Discussion-local Integration phase rewrites it after each integration. Detailed execution history remains in `reports/runs/*.md` and Git. Live Worker progress comes from `memory_sync.py status`; do not write heartbeat or transient progress here.

## Current Integration

- Date:
- Commit:

The JSON block below is the machine-readable source for this integration lifecycle. Keep the rest of this file as the compressed human review view.

<!-- wishgraph:integration-state:start -->
```json
{
  "schema_version": 1,
  "kind": "integration",
  "integration_id": "integration/YYYYMMDD-HHMM",
  "status": "completed",
  "integration_kind": "sequential",
  "authorization": "inherited_task_approval",
  "reports": [
    "reports/runs/NNN-short-slug.md"
  ]
}
```
<!-- wishgraph:integration-state:end -->

## Orchestration Snapshot

These values are a read-only review snapshot. Their live source is the Git-common-dir session runtime, Worker Claim, and Integration lease; do not add them to the Task Lifecycle JSON above.

- Session Role:
- Flow Phase:
- Expected transition:
- Active Worker Claim:
- Active Integration lease:

## Run Reports Absorbed This Integration

- `reports/runs/NNN-short-slug.md`

## Current Project Status

- Completed:
- User-visible result:
- Current important facts:

## Validation

- Build:
- Tests:
- Manual:

## Unresolved Items

- Risks:
- Conflicts:
- Pending user decisions:

## Worker Status

- Completed:
- Waiting:
- Blocked:
- Competitive candidates:
- Selected report(s):

## Next Step

- Recommended task:
- Reason:

## Discussion Handoff

- Current focus:
- Results to present:
- Detailed evidence: `reports/PROJECT_STATUS.md` and the run reports listed above

## Shared Memory Impact

Use exactly `Updated` or `N/A`. Every N/A needs a concrete reason, and every Updated row must correspond to the integration diff.

| File | Result | Reason |
|---|---|---|
| `PRD.md` | Updated / N/A | Product behavior, scope, roadmap, progress, or why no change was needed |
| `ARCHITECTURE.md` | Updated / N/A | Dependency, ownership, data-flow impact, or why none |
| `CODEMAP.md` | Updated / N/A | File, symbol, contract, status, probe impact, or why none |
| `CONVENTIONS.md` | Updated / N/A | Workflow-rule impact, or why none |
| `prompts/DISCUSSION_AI.md` | Updated | Refresh the concise discussion handoff after the status snapshot |
| `prompts/EXECUTION_AI.md` | Updated / N/A | Stable execution-rule impact, or why none |
| `prompts/INTEGRATION_AI.md` | Updated / N/A | Stable integration-rule impact, or why none |
