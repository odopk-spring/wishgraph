# 012 - 把 token refresh 移出 dashboard 渲染路径

Status: Example
Spec source: `PRD.md` "Now" roadmap 要求 dashboard first paint 不能等待 auth refresh。
Dependencies: None.
Run report: `reports/runs/012-dashboard-token-refresh.md`

## Intent

Dashboard 应该立即渲染缓存账户数据。Token refresh 应在后台运行，并且只在 first paint 之后更新 session。

## Current State

- `CODEMAP.md` 将 dashboard startup 映射到 `src/dashboard/DashboardPage.tsx`，将 auth state 映射到 `src/auth/sessionStore.ts`。
- `DashboardPage` 当前在 render initialization 期间调用 `refreshToken()`。
- `npm test -- dashboard` 覆盖 dashboard loading states。
- 本任务不改变 schema 或 API contract。

## Change Set

| Target | Anchor | Required Change |
|---|---|---|
| `src/dashboard/DashboardPage.tsx` | `DashboardPage` startup effect | 先从 cached session 渲染；把 refresh trigger 移到 post-render effect。 |
| `src/auth/sessionStore.ts` | `refreshToken` caller contract | 保持现有 return type；refresh 失败时保留 existing cached session，并暴露当前 error path。 |
| `tests/dashboard-loading.test.tsx` | loading behavior tests | 新增或更新测试，证明 cached dashboard content 在 refresh resolve 前出现。 |

## Implementation Notes

- 使用已有 session store 和 test helpers。
- 保持 public `refreshToken()` API 不变。
- 如果现有 helper 无法确定性等待 refresh resolution，在已有测试边界添加小型 test-only mock。

## Do Not Do

- 不要重新设计 auth。
- 不要改变 token storage。
- 不要添加新 state library。
- 不要修改 dashboard layout 或 copy。
- 不要触碰 billing、profile 或 settings routes。

## Validation

- [ ] `npm test -- dashboard`
- [ ] `npm test -- auth`
- [ ] Manual check: dashboard 在模拟 refresh pending 时显示 cached account data。
- [ ] 创建 `reports/runs/012-dashboard-token-refresh.md` 并记录测试证据。
- [ ] 对 PRD、CODEMAP 和讨论状态填写 Integrate 或 N/A；Worker 不直接修改共享文件。
- [ ] 已安装 hooks 时，WishGraph worktree memory check 通过。
- [ ] 除非用户明确说不提交，否则创建一个原子 commit。

## Rollback Boundary

回滚本任务的单个 commit，恢复之前的 dashboard refresh timing。

## Execution Report Requirements

报告修改文件、运行测试、手动检查结果、执行报告路径、集成建议、commit hash 和剩余风险。
