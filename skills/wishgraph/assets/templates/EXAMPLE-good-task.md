# 012 - Move token refresh out of dashboard render path

Spec source: `PRD.md` "Now" roadmap says dashboard first paint must not wait on auth refresh.
Dependencies: None.

<!-- wishgraph:task-state:start -->
```json
{
  "schema_version": 1,
  "kind": "task",
  "task_id": "012",
  "parent_task_id": null,
  "dependencies": [],
  "status": "draft",
  "work_type": "sequential",
  "batch_id": null,
  "attempt": 1,
  "execution_mode": "exclusive",
  "comparison_group": null,
  "run_report": "reports/runs/012-attempt-1.md",
  "worker_creation_authorized": false,
  "integration_policy": "inherited_task_approval"
}
```
<!-- wishgraph:task-state:end -->

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
- [ ] PRD, CODEMAP, and discussion-state impact recorded as Integrate or N/A; shared files not edited by the worker.
- [ ] WishGraph worktree memory check passes when hooks are installed.
- [ ] One atomic commit created unless user explicitly says not to commit.

## Rollback Boundary

Revert this task's single commit to restore previous dashboard refresh timing.

## Execution Report Requirements

Report changed files, tests run, manual check result, run report path, integration proposals, commit hash, and remaining risk.
