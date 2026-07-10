# NNN - 任务标题

Status: Pending
Spec source: 链接或概述已批准需求。
Dependencies: 列出依赖的前置任务、migration 或决策。
Language mode: 默认遵循 `prompts/DISCUSSION_AI.md`，除非本任务明确覆盖。
Run report: `reports/runs/NNN-short-slug.md`

## Intent

用一小段话说明用户可见目标。本节必须不依赖聊天历史也能理解。

## Current State

概述从文件、测试、日志或文档中确认的相关仓库事实。

## Change Set

| Target | Anchor | Required Change |
|---|---|---|
| `path/to/file` | `SymbolOrRouteName` | 描述准确行为变化 |

## Implementation Notes

- 保持 patch 最小。
- 使用项目已有模式和 helper。
- 除非任务明确授权破坏性变更，否则保持兼容。

## Do Not Do

- 不要重构无关文件。
- 除非明确批准，不要引入新依赖。
- 除非列在 Change Set 中，不要修改 public APIs、data schema、security、billing 或 deletion behavior。

## Validation

- [ ] Build: `<command>`
- [ ] Tests: `<command or test names>`
- [ ] Manual check: `<scenario>`
- [ ] 在上面指定路径创建唯一的新不可变执行报告。
- [ ] 执行报告对每个共享记忆文件填写 Integrate 或 N/A 加理由。
- [ ] Worker 没有修改共享项目记忆或 `reports/DEV_REPORT.md`。
- [ ] 已安装 hooks 时，`python3 .wishgraph/hooks/memory_sync.py check --scope worktree` 通过。
- [ ] 除非用户明确要求不提交，否则为本任务创建一个原子 commit。
- [ ] 未 stage 无关 diff。

## Rollback Boundary

描述最小可回滚单元。说明任何 generated files、migration effects 或 external side effects。

## Execution Report Requirements

最终报告必须包含：

- 修改文件。
- 行为变化。
- 验证命令和结果。
- 风险或未运行检查。
- 执行报告路径、Integrate 建议和 N/A 理由。
- 后续任务候选。
