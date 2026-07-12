# Templates / 模板

This folder provides manually copyable WishGraph project-memory templates.

本目录提供可手动复制的 WishGraph 项目外置记忆模板。

Project-level memory-sync hooks are bundled with the installable skill rather than duplicated here. Use `skills/wishgraph/scripts/install_project_hooks.py` to merge them safely into a target project. Hooks 项目级记忆同步配置由可安装 skill 提供，请使用安装器安全合并，不要手工覆盖已有配置。

Discussion AI classifies work as `discussion`, `sequential`, `parallel_batch`, or `high_risk`. After an explicit human command, it creates and configures user-visible Worker tasks when the host supports that capability; manual copying is the fallback. Safe sequential task approval includes normal integration authority; parallel and high-risk integration require explicit user confirmation. Integration is temporary and must use a truthful fallback when background tasks are unavailable.

讨论 AI 先判断工作类型；人类明确命令后，宿主支持时由讨论 Agent 创建并配置用户可见 Worker，手动复制仅作降级。安全串行任务的批准包含正常集成授权；并行和高风险集成需要用户明确确认。集成 Agent 是临时角色，平台不支持后台任务时必须如实降级。

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
.tasks/build/*.md
reports/DEV_REPORT.md
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
.tasks/build/*.md
reports/DEV_REPORT.md
reports/RUN_REPORT.md
reports/runs/<work-unit-id>.md
```

## Bilingual Projects / 双语项目

For bilingual projects, copy the language version that should be easiest for the team to maintain, then set `Bilingual output: Yes` in `prompts/DISCUSSION_AI.md`.

双语项目建议先选择团队最容易长期维护的模板语言，再在 `prompts/DISCUSSION_AI.md` 中设置 `Bilingual output: Yes`。文件路径、命令、代码符号、包名和环境变量不要翻译。
