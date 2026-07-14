# Good Execution Spec

Use this reference when writing or reviewing `tasks/build/*.md`. Existing projects that already use `.tasks/build/*.md` may keep that legacy path.

## What "Good" Means

A good execution spec gives an implementation agent enough context to produce correct code while avoiding context bloat.

It should answer:

- What user-visible outcome must change?
- What repo facts matter?
- Which files, symbols, APIs, routes, tests, or commands are in scope?
- What must not be changed?
- How will the result be verified?
- Which shared-memory files should the integration agent update?
- What is the rollback boundary?
- Which language mode should human-facing explanations and reports use?
- Is the work sequential, parallel, or high-risk, and what integration authority applies?

## Context Budget Rule

Include only context that changes implementation decisions.

Prefer:

- Anchors over pasted code.
- File paths and symbol names over broad folder descriptions.
- Acceptance criteria over long product essays.
- Links or section names over copied docs.
- Explicit "Do Not Do" bullets over vague caution.

Avoid:

- Full chat transcripts.
- Long PRD copies.
- Unrelated future roadmap.
- Multiple alternative designs after a decision is already made.
- "As discussed above" references.

## Quality Checklist

Before handing a task to execution AI, confirm:

- The task can be executed without chat history.
- The implementation surface is small enough for one atomic commit.
- The exact behavior change is observable.
- The "Current State" section is based on repo facts, not guesses.
- The "Change Set" anchors stable files or symbols.
- The "Do Not Do" section prevents likely scope drift.
- The validation commands are concrete.
- The unique immutable run-report path and commit requirements are explicit.
- The worker report must record Integrate or N/A with a reason for every managed shared-memory file.
- The WishGraph worktree memory check is explicit when project hooks are installed.
- The language mode is explicit when the project uses bilingual handoff.
- Work type, batch ID, integration authorization, and the unique report path are explicit.

## Compact Example

```markdown
# 012 - Move token refresh out of dashboard render path

Status: Pending
Spec source: `PRD.md` "Now" roadmap says dashboard first paint must not wait on auth refresh.
Dependencies: None.
Language mode: English.
Run report: `reports/runs/012-dashboard-token-refresh.md`
Work type: sequential
Batch ID: N/A
Integration authorization: Inherited task approval

## Intent

Dashboard should render cached account data immediately. Token refresh should run in the background and update the session only after the first paint.

## Current State

- `CODEMAP.md` maps dashboard startup to `src/dashboard/DashboardPage.tsx` and auth state to `src/auth/sessionStore.ts`.
- `DashboardPage` currently calls `refreshToken()` during render initialization.
- `npm test -- dashboard` covers dashboard loading states.
- No schema or API contract change is intended.

## Change Set

| Target | Anchor | Required Change |
|---|---|---|
| `src/dashboard/DashboardPage.tsx` | `DashboardPage` startup effect | Render from cached session first; move refresh trigger into a post-render effect. |
| `src/auth/sessionStore.ts` | `refreshToken` caller contract | Preserve existing return type; ensure failed refresh keeps existing cached session and exposes current error path. |
| `tests/dashboard-loading.test.tsx` | loading behavior tests | Add or update a test proving cached dashboard content appears before refresh resolves. |

## Implementation Notes

- Use the existing session store and test helpers.
- Keep the public `refreshToken()` API unchanged.
- If current helpers cannot await refresh resolution deterministically, add a small test-only mock at the existing test boundary.

## Do Not Do

- Do not redesign auth.
- Do not change token storage.
- Do not add a new state library.
- Do not alter dashboard layout or copy.
- Do not touch billing, profile, or settings routes.

## Validation

- [ ] `npm test -- dashboard`
- [ ] `npm test -- auth`
- [ ] Manual check: dashboard shows cached account data while simulated refresh is pending.
- [ ] `reports/runs/012-dashboard-token-refresh.md` created with test evidence.
- [ ] Shared-memory impact records Integrate or N/A with reasons; worker does not edit shared memory.
- [ ] `python3 .wishgraph/hooks/memory_sync.py check --scope worktree` passes when hooks are installed.
- [ ] One atomic commit created unless user explicitly says not to commit.

## Rollback Boundary

Revert this task's single commit to restore previous dashboard refresh timing.

## Execution Report Requirements

Report changed files, tests run, manual check result, run report path, integration proposals, commit hash, and remaining risk.
```

## Why This Example Works

- It is short, but it names exact anchors.
- It separates intent from implementation notes.
- It includes the existing state and test surface.
- It blocks obvious scope drift.
- It makes validation and integration proposals mandatory without creating shared-file races.
- It makes memory-impact decisions mechanically checkable without forcing meaningless file edits.
- It can become one atomic commit.
