# 通用 Agent 适配器

这个适配器用于不直接支持 Codex 或 Claude Code skill 的工具。

核心思路很简单：把 WishGraph 工作流放进你的 agent 已经会读取的 instruction 文件里，然后让 agent 创建同样的项目外置记忆文件。

## 安装到项目

把 `AGENTS.zh-CN.md` 复制到目标项目根目录：

```bash
cp adapters/generic/AGENTS.zh-CN.md /path/to/project/AGENTS.md
```

如果你的工具使用其他 always-loaded instruction 文件，也可以把同样内容复制过去。

常见例子：

- `AGENTS.md`
- `CLAUDE.md`
- 编辑器或 agent 工具支持的 project rules file
- agent workspace 里的 pinned system/developer prompt

然后用下面提示启动 agent：

```text
Follow AGENTS.md. Start WishGraph for this project. If there is no PRD, run the WishGraph intake prompt and grill it into a PRD before writing code.
```

如果需要中英双语交接，追加：

```text
Use bilingual Chinese and English for user-facing prompts and summaries. Keep file paths, commands, and code identifiers unchanged.
```

## 预期输出

Agent 应创建或更新：

```text
PRD.md
ARCHITECTURE.md
CODEMAP.md
CONVENTIONS.md
prompts/DISCUSSION_AI.md
prompts/EXECUTION_AI.md
tasks/build/*.md
reports/PROJECT_STATUS.md
reports/RUN_REPORT.md
reports/runs/<work-unit-id>.md
```

## 工具无关规则

不要依赖某个聊天产品。稳定协议是上面的文件集。任何能读写文件的 agent，只要遵守规划 / 执行分工，就可以参与。

安装 WishGraph hook runtime 后，通用 Agent 可以直接运行确定性检查：

```bash
python3 .wishgraph/hooks/memory_sync.py check --scope worktree
python3 .wishgraph/hooks/memory_sync.py check --scope staged
```

安装方式和可选 Git pre-commit 强制策略见 [`docs/memory-sync-hooks.zh-CN.md`](../../docs/memory-sync-hooks.zh-CN.md)。
