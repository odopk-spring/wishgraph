# Project Report Overview

This is the current integrated project snapshot. Only the integration agent updates this file. Worker agents write immutable task-scoped reports under `reports/runs/`.

## Latest Integration

- Integration ID: `integration/YYYYMMDD-HHMM`
- Date:
- Agent:
- Status: Completed / Blocked / Incomplete
- Target branch:

## Integrated Run Reports

List every run report absorbed by this integration. Integrate worker branches with `--no-commit` so the hook can verify these files in the same diff.

- `reports/runs/NNN-short-slug.md`

## Latest Integrated Results

- Completed result:
- User-visible effect:
- Important implementation fact:
- Deferred or rejected result:

## Validation Summary

| Check | Result | Evidence |
|---|---|---|
| Build | Pass / Fail / Not run | Key output or reason |
| Tests | Pass / Fail / Not run | Key output or reason |
| Manual | Pass / Fail / Not run | Scenario and notes |

## Current Risks and Follow-up

- Residual risk:
- Unresolved conflict:
- Next recommended task:

## Discussion Handoff

State what the discussion agent should present to the user next. The integration agent must also update the dynamic state block in `prompts/DISCUSSION_AI.md`.

## External Memory Impact

Use exactly `Updated` or `N/A`. Every N/A needs a concrete reason. `Updated` must correspond to a file in the integration diff.

| File | Result | Reason |
|---|---|---|
| `PRD.md` | Updated / N/A | Product behavior, scope, roadmap, progress, or why no change was needed |
| `ARCHITECTURE.md` | Updated / N/A | Dependency, ownership, data-flow impact, or why none |
| `CODEMAP.md` | Updated / N/A | File, symbol, contract, status, probe impact, or why none |
| `CONVENTIONS.md` | Updated / N/A | Workflow-rule impact, or why none |
| `prompts/DISCUSSION_AI.md` | Updated | Record merged results and the next discussion state |
| `prompts/EXECUTION_AI.md` | Updated / N/A | Stable execution-rule impact, or why none |
| `prompts/INTEGRATION_AI.md` | Updated / N/A | Stable integration-rule impact, or why none |

## Integration Commit

- Commit hash or pending commit note:
