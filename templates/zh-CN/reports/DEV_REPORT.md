# 项目报告概览

这是当前已集成项目事实的快照。只有集成 Agent 更新本文件；执行 Worker 把不可变的任务报告写入 `reports/runs/`。

## 最新集成

- 集成 ID：`integration/YYYYMMDD-HHMM`
- 日期：
- Agent：
- 状态：Completed / Blocked / Incomplete
- 目标分支：

## 已集成执行报告

列出本次集成吸收的全部报告。使用 `--no-commit` 合并 Worker 分支，使 Hook 能在同一 diff 中验证这些文件。

- `reports/runs/NNN-short-slug.md`

## 最新集成结果

- 已完成结果：
- 用户可见影响：
- 重要实现事实：
- 延后或拒绝的结果：

## 验证摘要

| 检查 | 结果 | 证据 |
|---|---|---|
| 构建 | Pass / Fail / Not run | 关键输出或原因 |
| 测试 | Pass / Fail / Not run | 关键输出或原因 |
| 手动 | Pass / Fail / Not run | 场景和说明 |

## 当前风险与后续

- 剩余风险：
- 未解决冲突：
- 推荐下一任务：

## 讨论交接

写明讨论 Agent 下一步应该向用户呈现什么。集成 Agent 还必须更新 `prompts/DISCUSSION_AI.md` 的动态状态区。

## External Memory Impact

Result 只能使用 `Updated` 或 `N/A`。每个 N/A 必须有具体理由；Updated 对应的文件必须出现在集成 diff 中。

| File | Result | Reason |
|---|---|---|
| `PRD.md` | Updated / N/A | 产品行为、范围、路线图、进度影响，或无需更新的理由 |
| `ARCHITECTURE.md` | Updated / N/A | 依赖、归属、数据流影响，或无需更新的理由 |
| `CODEMAP.md` | Updated / N/A | 文件、符号、契约、状态、验证入口影响，或无需更新的理由 |
| `CONVENTIONS.md` | Updated / N/A | 工作规则影响，或无需更新的理由 |
| `prompts/DISCUSSION_AI.md` | Updated | 记录合并结果和下一步讨论状态 |
| `prompts/EXECUTION_AI.md` | Updated / N/A | 稳定执行规则影响，或无需更新的理由 |
| `prompts/INTEGRATION_AI.md` | Updated / N/A | 稳定集成规则影响，或无需更新的理由 |

## 集成提交

- commit hash 或待提交说明：
