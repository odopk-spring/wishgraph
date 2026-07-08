# Templates / 模板

This folder provides manually copyable WishGraph project-memory templates.

本目录提供可手动复制的 WishGraph 项目外置记忆模板。

## English

Use the root templates directly:

```text
PRD.md
ARCHITECTURE.md
CODEMAP.md
CONVENTIONS.md
prompts/DISCUSSION_AI.md
prompts/EXECUTION_AI.md
.tasks/build/*.md
reports/DEV_REPORT.md
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
.tasks/build/*.md
reports/DEV_REPORT.md
```

## Bilingual Projects / 双语项目

For bilingual projects, copy the language version that should be easiest for the team to maintain, then set `Bilingual output: Yes` in `prompts/DISCUSSION_AI.md`.

双语项目建议先选择团队最容易长期维护的模板语言，再在 `prompts/DISCUSSION_AI.md` 中设置 `Bilingual output: Yes`。文件路径、命令、代码符号、包名和环境变量不要翻译。
