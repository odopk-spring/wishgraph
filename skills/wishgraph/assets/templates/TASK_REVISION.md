# Task Revision

Use this lightweight record for a clear, low-risk change to a completed Task. Save it as `tasks/revisions/<parent-task-id>-rN.md`. Do not copy the full Task Spec.

<!-- wishgraph:revision-state:start -->
```json
{
  "schema_version": 1,
  "kind": "revision",
  "revision_id": "012-r1",
  "parent_task_id": "012",
  "status": "pending",
  "user_request": "Change the reading-page theme from bright blue to dark blue.",
  "allowed_scope": ["ui/ReaderTheme.swift"],
  "validation_plan": ["Reader preview"],
  "run_report": "reports/runs/012-r1-attempt-1.md",
  "worker_creation_authorized": true
}
```
<!-- wishgraph:revision-state:end -->

## Context

- Why this remains part of the parent Task:
- Why it is low risk and independently reversible:

## Escalation Boundary

Stop and request a formal follow-up Task if the change affects a public API, schema, persistence, migration, dependencies, permissions, security, privacy, multiple unrelated modules, or a new product decision.
