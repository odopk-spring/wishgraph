# 001 - 用 WishGraph 启动项目治理

Spec source: 第一个讨论窗口把用户初始想法转换为 `PRD.md`。
Dependencies: None.
Language mode: 使用用户选择的项目语言；如果要求双语，中文在前、英文在后。

Task state 只记录 Task Lifecycle。Session Role、Flow Phase 与 `expected_transition` 保存在 Git common dir 的正交运行时状态中。

<!-- wishgraph:task-state:start -->
```json
{
  "schema_version": 1,
  "kind": "task",
  "task_id": "001",
  "parent_task_id": null,
  "dependencies": [],
  "status": "draft",
  "work_type": "sequential",
  "batch_id": null,
  "attempt": 1,
  "execution_mode": "exclusive",
  "comparison_group": null,
  "run_report": "reports/runs/001-attempt-1.md",
  "worker_creation_authorized": false,
  "integration_route": "auto_in_discussion"
}
```
<!-- wishgraph:task-state:end -->

## Intent

在功能实现前创建第一版持久项目框架。这个 Task 要让后续 Discussion 和 Worker 窗口无需聊天历史也能理解仓库。

## Current State

- 用户从粗略想法开始。
- `PRD.md` 包含第一版已确认项目框架。
- 除非下面明确列出，不应在这个 bootstrap 任务中实现业务代码。

## Change Set

| Target | Anchor | Required Change |
|---|---|---|
| `PRD.md` | Product frame and roadmap | 记录目标用户、目标、非目标、当前决策、首个薄切片和验收标准。 |
| `ARCHITECTURE.md` | Initial architecture | 记录计划结构、依赖边界、数据流和风险备注。 |
| `CODEMAP.md` | Initial map | 记录计划或现有文件、功能区域、合约、probe 和调试入口。 |
| `CONVENTIONS.md` | Project engineering rules | 只记录项目特有的构建、测试、编码、权限和 Git 约定。 |
| `tasks/002-first-slice.md` | First implementation task | PRD 批准后写首个有边界的实现任务。 |
| `reports/runs/001-bootstrap-project.md` | Bootstrap run report | 记录创建文件、假设、验证和共享记忆建议。 |
| `reports/PROJECT_STATUS.md` | 初始项目状态概览 | 把 bootstrap 汇总为第一份当前集成快照。 |
| `.wishgraph/` 和宿主 hook 配置 | 可选收尾强制 | Owner 要求 hooks 时，以 `warn` 模式安装，且不替换现有 hook groups。 |

## Implementation Notes

- 使用仓库原生命名和框架约定。
- 首个实现任务必须小到能用一组有边界、线性的 commit 完成。
- 首个实现任务必须包含 "Do Not Do" 边界。
- 如果仓库为空，映射计划文件，不要假装文件已经存在。
- 要求 hooks 时使用 bundled installer。Codex CLI 用户可用 `/hooks` 审阅精确项目 Hook；Codex Desktop 用户应在同一项目打开 CLI，不要把 `/hooks` 输入聊天框。

## Do Not Do

- 除非用户明确批准直接实现，不要在这个 bootstrap 任务中实现产品功能。
- 不要为了治理骨架引入依赖。
- 不要隐藏未解决产品决策；把它们记录为开放问题。

## Validation

- [ ] 治理文件存在并且彼此一致。
- [ ] `PRD.md` 包含目标用户、目标、非目标、首个薄切片和验收标准。
- [ ] `tasks/002-first-slice.md` 可直接交接给用户可见且可检查的 Worker thread 或窗口。
- [ ] Task 解释其工作类型、为什么串行或并行，以及何时需要用户确认集成。
- [ ] `reports/runs/001-bootstrap-project.md` 记录创建内容和未知项。
- [ ] `reports/PROJECT_STATUS.md` 列出 bootstrap 单次执行报告并汇总初始集成状态。
- [ ] Task 或 Project Status 记录与交付有关的语言要求。
- [ ] 如果要求 hooks，`.wishgraph/config.json` 初始使用 `warn`，且直接 worktree 检查可以运行。
- [ ] 除非用户明确说不提交，否则创建一个或多个有边界、线性的 commit。

## Rollback Boundary

回滚本任务的这组 commit，即可移除初始 WishGraph 治理骨架。

## Execution Report Requirements

报告创建文件、假设、开放决策、下一个执行任务、验证结果和 commit hash。
