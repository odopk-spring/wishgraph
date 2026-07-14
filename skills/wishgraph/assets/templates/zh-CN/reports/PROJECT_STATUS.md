# 项目状态概览

本文件只保存最近一次正式集成后的当前项目快照，不连续追加历史。集成 AI 每次集成都重写本文件；详细执行历史保存在 `reports/runs/*.md` 和 Git 中。

## 当前集成

- 日期：
- 提交：

下面的 JSON 块是本次集成生命周期的机器可读真相源；本文件其余部分继续作为压缩后的人类评审视图。

<!-- wishgraph:integration-state:start -->
```json
{
  "schema_version": 1,
  "kind": "integration",
  "integration_id": "integration/YYYYMMDD-HHMM",
  "status": "completed",
  "integration_kind": "sequential",
  "authorization": "inherited_task_approval",
  "reports": [
    "reports/runs/NNN-short-slug.md"
  ]
}
```
<!-- wishgraph:integration-state:end -->

## 本次吸收的执行报告

- `reports/runs/NNN-short-slug.md`

## 当前项目状态

- 已完成：
- 用户可见结果：
- 当前重要事实：

## 验证

- 构建：
- 测试：
- 手动验证：

## 未解决事项

- 风险：
- 冲突：
- 待用户决定：

## Worker 状态

- 已完成：
- 等待中：
- 阻塞中：
- 竞争候选：
- 选中的报告：

## 下一步

- 推荐任务：
- 推荐原因：

## 讨论交接

- 当前焦点：
- 需要呈现：
- 详细证据：`reports/PROJECT_STATUS.md` 和上面列出的单次执行报告

## 共享记忆影响

Result 只能使用 `Updated` 或 `N/A`。每个 N/A 必须有具体理由；每个 Updated 必须对应集成 diff 中的文件。

| File | Result | Reason |
|---|---|---|
| `PRD.md` | Updated / N/A | 产品行为、范围、路线图、进度影响，或无需更新的理由 |
| `ARCHITECTURE.md` | Updated / N/A | 依赖、归属、数据流影响，或无需更新的理由 |
| `CODEMAP.md` | Updated / N/A | 文件、符号、契约、状态、验证入口影响，或无需更新的理由 |
| `CONVENTIONS.md` | Updated / N/A | 工作规则影响，或无需更新的理由 |
| `prompts/DISCUSSION_AI.md` | Updated | 状态快照完成后刷新精简讨论交接 |
| `prompts/EXECUTION_AI.md` | Updated / N/A | 稳定执行规则影响，或无需更新的理由 |
| `prompts/INTEGRATION_AI.md` | Updated / N/A | 稳定集成规则影响，或无需更新的理由 |
