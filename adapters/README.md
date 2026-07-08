# Adapters / 适配器

Adapters are lightweight instruction files for agent tools that do not use Codex skills directly, or for teams that want always-loaded project rules.

适配器是给不直接支持 Codex skill 的 agent 工具使用的轻量 instruction 文件，也适合需要常驻项目规则的团队。

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
