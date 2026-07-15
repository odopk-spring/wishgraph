# Review Window Format

Use this format for human-facing summaries in Discussion. “Review Window” names a presentation format in the `presenting_result` phase; it is not a separate role, window, or fourth Agent.

## Before Execution

```markdown
## Understanding
- User intent:
- Success criteria:
- Out of scope:

## Plan
- Step 1:
- Step 2:
- Step 3:

## Risk
- Main risk:
- Validation:
- Human decision needed:

## Execution Shape
- Work type: discussion / sequential / parallel_batch / high_risk
- Why:
- Worker creation offer:
- Explicit creation authority: Required / Received / N/A
- Visible Worker tasks created:
- Manual fallback required:
- Integration authority:
```

## After Execution

```markdown
## Result
- Changed:
- Not changed:
- Behavior:

## Evidence
- Build:
- Tests:
- Manual check:

## Risk
- Residual risk:
- Follow-up:

## External Memory
- Run report:
- Integrate proposals:
- N/A with reasons:
- Hook check:

## Worker and Integration Status
- Completed workers:
- Waiting workers:
- Blocked workers:
- Integration: Waiting / Running / Blocked / Completed
- Integration authorization: Inherited / Explicitly confirmed / Required
- Human result review: Pending / Accepted / Changes requested
```

After integration, replace the run-report proposal lines with integrated report paths, shared files Updated or N/A, and whether the discussion handoff was refreshed.

## Rules

- Keep the summary short enough for review.
- Link to task files for detail.
- Do not hide failed checks.
- Say when the agent made an assumption.
- Avoid dumping raw logs unless the log line is the evidence.
- Keep integration authorization separate from the user's review of the integrated result.
- Keep Worker creation authorization separate from task approval and integration authorization. Never report a Worker as created unless a user-visible task actually exists.
- Do not present hooks as semantic reviewers or background executors.
