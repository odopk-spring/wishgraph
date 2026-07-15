# Templates / 模板

This folder provides manually copyable WishGraph project-memory templates.

本目录提供可手动复制的 WishGraph 项目外置记忆模板。

Project-level memory-sync hooks are bundled with the installable skill rather than duplicated here. Use `skills/wishgraph/scripts/install_project_hooks.py` to merge them safely into a target project. Hooks 项目级记忆同步配置由可安装 skill 提供，请使用安装器安全合并，不要手工覆盖已有配置。

Discussion AI classifies work as `discussion`, `sequential`, `parallel_batch`, or `high_risk`. After an explicit human command, Codex creates a user-visible Worker; Claude Code and unsupported or failed creation output only `执行 <task-id> 任务`. Safe sequential and mechanically proven `parallel_independent` results enter Discussion-local Integration automatically; high-risk, conflicting, blocked, competitive, or ambiguous results ask only the concrete decision. Integration never creates a separate window.

Task templates start with a versioned `wishgraph:task-state` block. The checked lifecycle is `draft -> approved -> running -> completed|blocked|incomplete -> integrated -> reviewed`; only an explicit human command changes Worker authorization to true.

Worker windows can be rebound after terminal closeout. Low-risk corrections use `tasks/revisions/<task-id>-rN.md` and a `wishgraph:revision-state` block instead of a full Task Spec.

Discussion 先判断工作类型；人类明确命令后，Codex 创建用户可见 Worker；Claude Code、宿主不支持或创建失败时只输出 `执行 <task-id> 任务`。安全串行和机械检查证明独立的 `parallel_independent` 结果自动进入 Discussion-local Integration；高风险、冲突、阻塞、竞争或歧义只询问具体决定。Integration 不创建独立窗口。

任务模板使用版本化 `wishgraph:task-state` 状态块，受检生命周期为 `draft -> approved -> running -> completed|blocked|incomplete -> integrated -> reviewed`；只有人类明确命令才能把 Worker 创建授权改为 true。

Worker 窗口在终态收尾后可以重新绑定；低风险修正使用 `tasks/revisions/<task-id>-rN.md` 和 `wishgraph:revision-state`，不创建完整 Task Spec。

## English

Use the root templates directly:

```text
PRD.md
ARCHITECTURE.md
CODEMAP.md
CONVENTIONS.md
prompts/DISCUSSION_AI.md
prompts/EXECUTION_AI.md
prompts/INTEGRATION_AI.md
tasks/build/*.md
tasks/revisions/*.md
reports/PROJECT_STATUS.md
reports/RUN_REPORT.md
reports/runs/<work-unit-id>.md
```

## 中文

中文模板在：

```text
templates/zh-CN/
```

复制到目标项目时，通常仍然使用同样的目标路径：

```text
PRD.md
ARCHITECTURE.md
CODEMAP.md
CONVENTIONS.md
prompts/DISCUSSION_AI.md
prompts/EXECUTION_AI.md
prompts/INTEGRATION_AI.md
tasks/build/*.md
tasks/revisions/*.md
reports/PROJECT_STATUS.md
reports/RUN_REPORT.md
reports/runs/<work-unit-id>.md
```

## Bilingual Projects / 双语项目

For bilingual projects, copy the language version that should be easiest for the team to maintain, then set `Bilingual output: Yes` in `prompts/DISCUSSION_AI.md`.

双语项目建议先选择团队最容易长期维护的模板语言，再在 `prompts/DISCUSSION_AI.md` 中设置 `Bilingual output: Yes`。文件路径、命令、代码符号、包名和环境变量不要翻译。
