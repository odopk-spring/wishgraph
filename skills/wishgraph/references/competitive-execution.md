# Competitive Execution

Use this reference when the user explicitly wants multiple Workers to solve the same goal, compare alternatives, run an experiment race, or choose one winner.

## When To Use

Use `competitive` only when:

- The candidates pursue the same approved goal.
- Each can run in an isolated branch/worktree.
- Each has independent validation and an immutable report.
- A scorecard or explicit human preference can choose a winner.
- Only one candidate will be integrated.

Do not confuse competitive execution with `parallel_independent`. Independent tasks may all integrate; competitive candidates are alternatives and exactly one wins.

## Candidate Graph

Create follow-up candidates such as:

```text
012a
012b
```

Set:

```json
{
  "parent_task_id": "012",
  "execution_mode": "competitive",
  "comparison_group": "012"
}
```

Give every candidate a distinct Task Spec, attempt, Run Report path, branch/worktree, and competitive Claim. Keep the same product goal while allowing the intended implementation difference.

## Authorization

Show the candidate set, reason for competition, expected cost, scorecard, and stop condition before launch. Require explicit human authority for the exact user-visible and inspectable Worker threads or windows. Do not infer competitive authority from ordinary Task approval or a vague request for parallelism. Every concurrent writer must use a distinct worktree.

## Scorecard

Prefer measurable dimensions already approved in the parent goal:

- Correctness and acceptance tests.
- Performance or resource use.
- Complexity and maintainability.
- Compatibility and migration risk.
- Rollback quality.
- User-visible quality when a human judgment is required.

Record weights and measurement methods before results exist. Do not change the scorecard to favor a completed candidate.

An objective scorecard may select a unique winner automatically when all required evidence is complete and no product, architecture, API, data, security, or compatibility decision remains. A tie, incomplete evidence, or subjective preference returns a compact comparison and recommendation to Discussion.

## Execution And Isolation

- Acquire one competitive Claim per candidate in a distinct worktree.
- Prevent shared-memory edits from every candidate.
- Run the same required baseline and evaluation surface where comparison fairness needs it.
- Preserve failures and negative results in each immutable report.
- Do not allow one candidate to consume another candidate's unapproved changes.

## Selection And Closeout

Integrate exactly one winner.

1. Verify every expected candidate is terminal or explicitly abandoned.
2. Validate the scorecard evidence and unresolved decisions.
3. Select the unique winner automatically only when the policy allows it; otherwise ask the user.
4. Mark the winner ready for Integration.
5. Mark losing candidates `rejected` or `superseded`.
6. Release all candidate Claims.
7. Preserve every Task Spec, report, commit, and comparison result.

Do not merge parts of multiple candidates unless Discussion first creates and authorizes a new fusion Task with its own validation and rollback boundary.

## Review Output

Present:

- Candidate and approach.
- Validation status.
- Score by predeclared dimension.
- Material tradeoff.
- Recommended winner and why.
- Required human decision, if any.
- Loser closeout state.

Keep raw logs in Run Reports; keep the Discussion comparison short enough for a real choice.
