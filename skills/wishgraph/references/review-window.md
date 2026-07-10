# Review Window Format

Use this format for human-facing summaries.

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
```

After integration, replace the run-report proposal lines with integrated report paths, shared files Updated or N/A, and whether the discussion handoff was refreshed.

## Rules

- Keep the summary short enough for review.
- Link to task files for detail.
- Do not hide failed checks.
- Say when the agent made an assumption.
- Avoid dumping raw logs unless the log line is the evidence.
