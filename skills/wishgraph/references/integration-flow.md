# Discussion-Local Integration

Use this reference after Worker closeout, while evaluating integration readiness, merging results, updating shared project memory, or asking a material decision.

## Contents

- Trigger and evaluation
- Integration lease
- Merge and validation
- Shared-memory writeback
- Completion and review
- Blocked and decision paths
- Human-facing review format

## Trigger

Every Worker terminal event enters:

```text
completed|blocked|incomplete
-> integration_pending
-> integration evaluation
```

Do not ask whether to begin evaluation or integration.

Route evaluation outcomes:

- Safe and complete: enter automatic, Discussion-local, safe-when-silent Integration.
- Material risk, conflict, or new product/architecture/data decision: enter `decision_required` and ask only the concrete choice.
- Missing report, failed prescribed validation, or invalid closeout: enter `blocked` or Worker repair.
- Competitive or mechanically ambiguous result: return a comparison or exact decision to Discussion.

If Discussion is inactive, persist `integration_pending`. Resume evaluation on the next explicit Discussion entry or refresh. Do not describe this as real-time push.

## Safe Integration Gates

Require all applicable evidence:

- Formal Task or Revision is terminal and integration-eligible.
- Expected immutable Run Report exists and parses correctly.
- Prescribed validation passed or an approved `N/A` is explicit.
- Changed scope is bounded and matches the durable record.
- No unresolved merge conflict or dependency ordering problem remains.
- No new public API, schema, persistence, migration, dependency, permission, security, privacy, product, or architecture decision is hidden in the patch.
- Rollback remains safe.
- For `parallel_independent`, every expected Worker is terminal and overlap, interface, dependency, and combined-validation gates pass.

Task approval carries authority for later safe sequential integration. Do not ask twice. Parallel, competitive, high-risk, or ambiguous results follow their explicit policy.

## Integration Lease

Before entering `integrating`, atomically acquire one lease bound to:

```text
discussion session
integration_id
base branch
absolute worktree
selected Task IDs
selected Run Reports
optional Revision ID
lease status and heartbeat
```

Use the lease as the single-writer authority for merge resolution, combined validation, shared-state writes, and the integration commit. Do not use it to implement new product work.

Only one active lease may exist for the repository's Git common directory. Release it after durable completion; revoke only through explicit recovery authority.

## Merge And Combined Validation

1. Start from the intended clean integration worktree and branch.
2. Merge or cherry-pick Worker commits with `--no-commit` or an equivalent no-commit operation.
3. Keep new Run Reports visible in the integration diff.
4. Resolve only bounded merge conflicts that do not require a new product or architecture choice.
5. Run combined validation across the selected results.
6. Stop at `decision_required` or `blocked` when evidence no longer satisfies the safe gates.

Do not silently blend competitive candidates or unrelated Worker changes.

## Shared-Memory Writeback

Read every selected Run Report and apply its `Integrate` proposals. If any selected report marks a managed file `Integrate`, the Project Status row must be `Updated` and that file must appear in the integration diff; `N/A` cannot silently drop the proposal. For other managed files, record `Updated` or concrete `N/A`; do not force meaningless edits.

Update as needed:

- `PRD.md` for product truth and roadmap.
- `ARCHITECTURE.md` for ownership or dependency changes.
- `CODEMAP.md` for feature-to-code facts.
- `CONVENTIONS.md` for durable collaboration or validation rules.
- Stable prompts only when their reusable contract changed.
- `reports/PROJECT_STATUS.md` as the complete current snapshot.

Rewrite Project Status rather than appending history. Preserve current facts, unresolved risk, conflicts, pending decisions, next action, and only the report paths absorbed by this integration. Keep historical detail in immutable reports and Git.

After Project Status is complete, update only the concise dynamic state block in `prompts/DISCUSSION_AI.md`: latest integration ID, current focus, result to present, pending decisions, next action, and Project Status pointer.

## Completion

Fill the `wishgraph:integration-state` block with the integration ID, status, kind, authority, and exactly the absorbed reports. Create the integration commit while the lease is active.

- Move absorbed formal Tasks from `completed` to `integrated`.
- Move absorbed Revisions from `completed` to `integrated` without regressing their parent lifecycle.
- Release the Integration lease.
- Enter `presenting_result` and show the compressed result and evidence.
- After human acceptance, move only the relevant formal Task from `integrated` to `reviewed`.

Review acceptance is not new integration authority.

## Material Decisions

Ask the smallest real question, for example:

```text
012 changes the public API. Option A preserves compatibility with a wrapper;
Option B makes the breaking contract explicit. I recommend A. Adopt A?
```

Do not ask `是否开始集成？`. Do not disguise failed validation or a new product choice as safe integration.

## Failure And Recovery

- Missing or malformed report: return to Worker repair.
- Failed validation: mark blocked/incomplete with evidence.
- Unsafe conflict: preserve the merge state only when recoverable; otherwise abort the no-commit merge without deleting Worker history.
- Incorrect rule: switch project hooks to `warn` while repairing configuration; never fabricate state to bypass enforcement.

## Human-Facing Review Format

“Review” is the `presenting_result` state in Discussion, not a separate role or window.

Before execution, present only what the user must verify:

```markdown
## Understanding
- Intent and success:
- Out of scope:

## Execution Shape
- Work type and reason:
- Worker authority and visible tasks:
- Validation and main risk:
- Material decision needed:
```

After execution and integration, present:

```markdown
## Result
- Changed / not changed:
- User-visible behavior:

## Evidence
- Build / tests / manual check:

## Risk
- Residual risk and follow-up:

## External Memory
- Integrated Run Reports:
- Shared files Updated or N/A:
- Hook check and Discussion handoff:

## Status
- Completed / waiting / blocked Workers:
- Integration state and authority:
- Human review: Pending / Accepted / Changes requested
```

Keep raw logs in Run Reports. State failed checks and assumptions. Keep Worker creation authority, integration authority, and human result acceptance separate. Never report a Worker or background action that did not actually exist.
