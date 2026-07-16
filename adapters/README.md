# Adapters / 适配器

Adapters are lightweight instruction files for agent tools that do not use Codex skills directly, or for teams that want always-loaded project rules.

适配器是给不直接支持 Codex skill 的 agent 工具使用的轻量 instruction 文件，也适合需要常驻项目规则的团队。

An adapter is not the WishGraph runtime. It can explain roles and file conventions, but native Worker creation, lifecycle Hooks, write/build gates, and completion notifications exist only when the current host and project runtime actually support them.

适配器不等于 WishGraph runtime。它可以解释角色与文件约定；只有当前宿主和项目 runtime 确实支持时，才具备原生 Worker 创建、生命周期 Hooks、写入／构建门禁和完成提醒。

| Route | Native Worker support | Mechanical gates |
| --- | --- | --- |
| Codex Skill + project runtime | Host-mediated inspectable Agent thread, with one-line fallback | Codex project Hooks |
| Claude Code Skill + project runtime | Managed background session when capability checks pass, with one-line fallback | Claude Code project Hooks |
| Generic instruction adapter | Manual inspectable session only unless that host supplies an equivalent integration | Policy guidance; direct checker commands only |

Installing any global Skill means “available,” not “active in every project.” Project activation must still be explicit.

## Claude Code

- English: [`claude-code/CLAUDE.md`](claude-code/CLAUDE.md)
- 中文：[`claude-code/CLAUDE.zh-CN.md`](claude-code/CLAUDE.zh-CN.md)
- Guide: [`claude-code/README.md`](claude-code/README.md)
- 中文指南：[`claude-code/README.zh-CN.md`](claude-code/README.zh-CN.md)

## Generic Agents

- English: [`generic/AGENTS.md`](generic/AGENTS.md)
- 中文：[`generic/AGENTS.zh-CN.md`](generic/AGENTS.zh-CN.md)
- Guide: [`generic/README.md`](generic/README.md)
- 中文指南：[`generic/README.zh-CN.md`](generic/README.zh-CN.md)

## Bilingual Use / 双语使用

Use the English or Chinese adapter as the base project instruction, then tell the agent:

```text
Use bilingual Chinese and English for user-facing prompts and summaries. Keep file paths, commands, and code identifiers unchanged.
```

选择英文或中文适配器作为项目基础 instruction 后，再告诉 agent：

```text
面向用户的提示、摘要和任务解释使用中英双语，中文在前、英文在后。文件路径、命令和代码符号保持原文。
```
