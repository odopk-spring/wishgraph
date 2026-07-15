# 任务修订

仅用于对已完成 Task 的明确、低风险、小范围修改。保存为 `tasks/revisions/<parent-task-id>-rN.md`，不要复制完整 Task Spec。

<!-- wishgraph:revision-state:start -->
```json
{
  "schema_version": 1,
  "kind": "revision",
  "revision_id": "012-r1",
  "parent_task_id": "012",
  "status": "pending",
  "user_request": "将阅读页主题色从亮蓝改为深蓝。",
  "allowed_scope": ["ui/ReaderTheme.swift"],
  "validation_plan": ["阅读页预览"],
  "run_report": "reports/runs/012-r1-attempt-1.md",
  "worker_creation_authorized": true
}
```
<!-- wishgraph:revision-state:end -->

## 背景

- 为什么它仍属于原 Task：
- 为什么它风险低且可以独立撤销：

## 升级边界

如果修改涉及公共 API、schema、持久化、迁移、依赖、权限、安全、隐私、多个无关模块或新的产品决定，停止执行并请求正式后续 Task。
