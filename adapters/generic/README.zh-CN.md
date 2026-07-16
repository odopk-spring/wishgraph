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

项目明确启用后，用户侧仍保持简单：重新打开会话，输入“开始讨论”，执行某个准确 Task 时输入“执行 012 任务”。通用适配器本身不会创建原生 Worker；除非当前宿主另有等价、可检查的 thread 集成，否则只降级为一行执行命令。

如果需要中英双语交接，追加：

```text
Use bilingual Chinese and English for user-facing prompts and summaries. Keep file paths, commands, and code identifiers unchanged.
```

## 避免项目文件膨胀

已有产品、架构、代码地图、规范、Task 和测试文件能够承担同一事实时继续复用。只补齐缺少的入口状态，Task、Revision 和 Run Report 目录在首次需要时再创建。下面是默认路径，不是要求已有项目复制一套文档：

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

同一项目的新窗口通过“开始讨论”继续；已经处于 Discussion 时使用“刷新项目状态”。正常交接不复制完整提示词或旧聊天记录。

## 工具无关规则

持久项目事实不依赖某个聊天产品。任何能读写这些文件的 Agent 都可以参与协议，但不同宿主的安全性和自动化程度并不相同。仅复制本适配器不会获得原生 Worker 创建、生命周期 Hook 注册、写入／构建拦截或完成提醒。

安装 WishGraph hook runtime 后，通用 Agent 可以直接运行确定性检查：

```bash
python3 .wishgraph/hooks/memory_sync.py check --scope worktree
python3 .wishgraph/hooks/memory_sync.py check --scope staged
```

这些命令检查收尾状态，不能替代宿主的 `PreToolUse` 集成，也不能描述成写入／构建硬门禁。

安装方式和可选 Git pre-commit 强制策略见 [`docs/memory-sync-hooks.zh-CN.md`](../../docs/memory-sync-hooks.zh-CN.md)。
