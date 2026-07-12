# Run Report

Create one new file from this template for each worker execution. Use `reports/runs/<work-unit-id>.md`. Never reuse or overwrite an earlier run report.

## Work Unit

- Unit: Task ID or `ad-hoc/YYYYMMDD-HHMM-short-slug`
- Mode: Formal / Ad-hoc
- Date:
- Agent:
- Branch / worktree:
- Status: Completed / Blocked / Incomplete
- Work type: sequential / parallel_batch / high_risk
- Batch ID: N/A for sequential; stable batch ID for parallel work
- Integration authorization: Inherited task approval / Requires explicit user confirmation
- Integration readiness: Ready / Blocked / Needs decision
- Scope check: Pass / Fail
- Conflict status: None / Present
- New product / architecture / data decision: No / Yes

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
