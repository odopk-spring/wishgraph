# 执行报告

每次 Worker 执行都从本模板创建一个新文件：`reports/runs/<work-unit-id>.md`。不要复用或覆盖已有执行报告。

## 工作单元

- Unit：Task ID 或 `ad-hoc/YYYYMMDD-HHMM-short-slug`
- 模式：Formal / Revision / Ad-hoc
- 日期：
- Agent：
- 分支 / worktree：

下面的 JSON 块是生命周期状态的机器可读真相源；叙述性证据继续写在后续章节中。串行任务的 `batch_id` 使用 `null`。

`change_class: micro` 只用于读取旧报告，不再创建新的 ad-hoc micro 工作。新的局部修正使用 Task Revision，新功能使用正式 Task。只有 Task 定义了完整客观评分表时，竞争候选才填写分数；涉及偏好或接近的取舍时设 `selection_requires_judgment: true`。

执行 Task Revision 时使用 `change_class: revision`，`task_id` 保持为原 Task，填写精确 `revision_id` 并列出全部 changed paths。所有显式风险字段必须为 false；否则停止并请求正式后续 Task。

<!-- wishgraph:run-state:start -->
```json
{
  "schema_version": 1,
  "kind": "run",
  "task_id": "001",
  "revision_id": null,
  "attempt": 1,
  "unit": "NNN-short-slug",
  "status": "completed",
  "work_type": "sequential",
  "execution_mode": "exclusive",
  "batch_id": null,
  "changed_paths": [],
  "public_api_change": false,
  "schema_change": false,
  "persistence_change": false,
  "security_impact": false,
  "privacy_impact": false,
  "permission_change": false,
  "billing_impact": false,
  "deletion_change": false,
  "migration_change": false,
  "dependency_change": false,
  "cross_module_contract_change": false,
  "change_class": "formal",
  "candidate_score": null,
  "selection_requires_judgment": false,
  "integration_authorization": "inherited_task_approval",
  "integration_readiness": "ready",
  "scope_check": "pass",
  "conflict_status": "none",
  "new_decision": false,
  "validation": {
    "build": "n/a",
    "tests": "pass",
    "manual": "n/a"
  }
}
```
<!-- wishgraph:run-state:end -->

## 摘要

简要说明修改内容和原因。

## 修改文件

| File | Reason |
|---|---|
| `path/to/file` | 修改摘要 |

## 验证

| 检查 | 命令 / 场景 | 结果 | 证据 |
|---|---|---|---|
| 构建 | `<command>` | Pass / Fail / N/A | 关键输出或具体 N/A 理由 |
| 测试 | `<command>` | Pass / Fail / N/A | 关键输出或具体 N/A 理由 |
| 手动 | `<scenario>` | Pass / Fail / N/A | 说明或具体 N/A 理由 |

## 风险

- 剩余风险：
- 未运行检查：
- 推荐后续：

## Shared Memory Impact Proposal

Worker 不直接修改共享项目记忆。需要 Discussion-local Integration 更新时使用 `Integrate`；无需更新时使用 `N/A` 并给出具体理由。

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
- Discussion-local Integration 必须保留的事实：
- 可以安全集成、阻塞或需要用户决定的理由：
