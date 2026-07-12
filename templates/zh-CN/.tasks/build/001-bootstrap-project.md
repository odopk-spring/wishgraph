# 001 - 用 WishGraph 启动项目治理

Status: Draft
Spec source: 第一个讨论窗口把用户初始想法转换为 `PRD.md`。
Dependencies: None.
Language mode: 使用用户选择的项目语言；如果要求双语，中文在前、英文在后。
Run report: `reports/runs/001-bootstrap-project.md`
Work type: sequential
Batch ID: N/A
Integration authorization: 随任务批准授权

## Intent

在功能实现前创建第一版持久项目框架。这个任务要让未来讨论和执行 agent 不依赖聊天历史也能理解仓库。

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
| `CONVENTIONS.md` | Collaboration rules | 记录讨论 / 执行角色、验证顺序、外置记忆更新规则和 git 规则。 |
| `prompts/DISCUSSION_AI.md` | Current handoff | 保存当前讨论状态、开放决策和下一个可能任务。 |
| `prompts/EXECUTION_AI.md` | Execution handoff | 保存执行窗口稳定提示词。 |
| `prompts/INTEGRATION_AI.md` | Temporary integration handoff | 保存授权单写者集成和真实后台降级的稳定提示词。 |
| `.tasks/build/002-first-slice.md` | First implementation task | PRD 批准后写首个有边界的实现任务。 |
| `reports/runs/001-bootstrap-project.md` | Bootstrap run report | 记录创建文件、假设、验证和共享记忆建议。 |
| `reports/DEV_REPORT.md` | Initial project overview | 把 bootstrap 汇总为第一份集成快照。 |
| `.wishgraph/` 和宿主 hook 配置 | 可选收尾强制 | Owner 要求 hooks 时，以 `warn` 模式安装，且不替换现有 hook groups。 |

## Implementation Notes

- 使用仓库原生命名和框架约定。
- 首个实现任务必须小到能用一个原子 commit 完成。
- 首个实现任务必须包含 "Do Not Do" 边界。
- 如果仓库为空，映射计划文件，不要假装文件已经存在。
- 要求 hooks 时使用 bundled installer，并提醒 Codex 用户通过 `/hooks` 审阅项目 hooks。

## Do Not Do

- 除非用户明确批准直接实现，不要在这个 bootstrap 任务中实现产品功能。
- 不要为了治理骨架引入依赖。
- 不要隐藏未解决产品决策；把它们记录为开放问题。

## Validation

- [ ] 治理文件存在并且彼此一致。
- [ ] `PRD.md` 包含目标用户、目标、非目标、首个薄切片和验收标准。
- [ ] `prompts/DISCUSSION_AI.md` 可复制到新讨论窗口。
- [ ] `prompts/EXECUTION_AI.md` 加 `.tasks/build/002-first-slice.md` 可复制到新执行窗口。
- [ ] 讨论提示词解释首个任务的工作类型、为什么串行或并行、准确 Worker 启动步骤，以及何时需要用户确认集成。
- [ ] `reports/runs/001-bootstrap-project.md` 记录创建内容和未知项。
- [ ] `reports/DEV_REPORT.md` 列出 bootstrap 执行报告并汇总初始集成状态。
- [ ] `prompts/DISCUSSION_AI.md` 记录项目语言模式。
- [ ] 如果要求 hooks，`.wishgraph/config.json` 初始使用 `warn`，且直接 worktree 检查可以运行。
- [ ] 除非用户明确说不提交，否则创建一个原子 commit。

## Rollback Boundary

回滚本任务的单个 commit，即可移除初始 WishGraph 治理骨架。

## Execution Report Requirements

报告创建文件、假设、开放决策、下一个执行任务、验证结果和 commit hash。
