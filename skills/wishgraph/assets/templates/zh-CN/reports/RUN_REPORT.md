# 执行报告

每次 Worker 执行都从本模板创建一个新文件：`reports/runs/<work-unit-id>.md`。不要复用或覆盖已有执行报告。

## 工作单元

- Unit：Task ID 或 `ad-hoc/YYYYMMDD-HHMM-short-slug`
- 模式：Formal / Ad-hoc
- 日期：
- Agent：
- 分支 / worktree：
- 状态：Completed / Blocked / Incomplete

## 摘要

简要说明修改内容和原因。

## 修改文件

| File | Reason |
|---|---|
| `path/to/file` | 修改摘要 |

## 验证

| 检查 | 命令 / 场景 | 结果 | 证据 |
|---|---|---|---|
| 构建 | `<command>` | Pass / Fail / Not run | 关键输出或原因 |
| 测试 | `<command>` | Pass / Fail / Not run | 关键输出或原因 |
| 手动 | `<scenario>` | Pass / Fail / Not run | 说明 |

## 风险

- 剩余风险：
- 未运行检查：
- 推荐后续：

## Shared Memory Impact Proposal

Worker 不直接修改共享项目记忆。需要集成 Agent 更新时使用 `Integrate`；无需更新时使用 `N/A` 并给出具体理由。

| File | Result | Reason |
|---|---|---|
| `PRD.md` | Integrate / N/A | 产品行为、范围、路线图、进度影响，或无需更新的理由 |
| `ARCHITECTURE.md` | Integrate / N/A | 依赖、归属、数据流影响，或无需更新的理由 |
| `CODEMAP.md` | Integrate / N/A | 文件、符号、契约、状态、验证入口影响，或无需更新的理由 |
| `CONVENTIONS.md` | Integrate / N/A | 工作规则影响，或无需更新的理由 |
| `prompts/DISCUSSION_AI.md` | Integrate / N/A | 集成后应向讨论 AI 呈现的结果，或无需更新的理由 |
| `prompts/EXECUTION_AI.md` | Integrate / N/A | 稳定执行规则影响，或无需更新的理由 |
| `prompts/INTEGRATION_AI.md` | Integrate / N/A | 稳定集成规则影响，或无需更新的理由 |

## 集成说明

- 合并依赖：
- 冲突提醒：
- 集成 Agent 必须保留的事实：
