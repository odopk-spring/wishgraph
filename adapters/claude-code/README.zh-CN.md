# Claude Code 适配器

Claude Code 可以把 WishGraph 作为原生 skill 使用。Claude Code skill 放在 skill 目录中，目录名会成为 slash command。因为本仓库安装目录名是 `wishgraph`，所以命令是：

```text
/wishgraph
```

Claude Code 的项目记忆也可以使用 `CLAUDE.md`。本目录中的模板是一个轻量 bridge，适合希望每个 Claude Code session 都知道 WishGraph 工作流的团队。

官方参考：

- Claude Code skills: https://code.claude.com/docs/en/skills
- Claude Code memory and `CLAUDE.md`: https://code.claude.com/docs/en/memory

## 安装为用户 skill

如果希望所有 Claude Code 项目都能使用 `/wishgraph`：

```bash
curl -fsSL https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.sh | bash -s -- claude-user
```

必要时重启 Claude Code，然后运行：

```text
/wishgraph 请为当前项目主动推荐合适的安装方式，让我用自然语言选择，然后持续配置到验证完成
```

Windows PowerShell 可以使用原生安装器：

```powershell
& ([scriptblock]::Create((irm 'https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.ps1'))) claude-user -SetupProject
```

如果要中英双语交接，追加：

```text
Use bilingual Chinese and English for user-facing prompts and summaries. Keep file paths, commands, and code identifiers unchanged.
```

## 安装到单个项目

如果团队希望把 skill 放进单个仓库：

```bash
curl -fsSL https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.sh | bash -s -- claude-project
```

这会创建：

```text
.claude/skills/wishgraph/
```

信任工作区前，请先审阅 skill。

## 添加项目记忆

把本适配器的 `CLAUDE.zh-CN.md` 复制到目标项目根目录，或合并进现有 `CLAUDE.md`：

```bash
cp adapters/claude-code/CLAUDE.zh-CN.md /path/to/project/CLAUDE.md
```

`CLAUDE.md` 用于 always-loaded 项目规则。较大的任务过程应留在 `/wishgraph` skill 和 WishGraph 项目文件中，例如 `PRD.md`、`CODEMAP.md`、`tasks/build/*.md`、`reports/runs/*.md` 和 `reports/PROJECT_STATUS.md`。

## 安装项目记忆同步 Hooks

学习成本最低的方式是直接说：

```text
/wishgraph 为这个项目推荐合适的 Hooks 配置，让我用自然语言选择，然后继续配置到验证完成
```

如果需要手动安装警告模式 Hooks：

```bash
python3 ~/.claude/skills/wishgraph/scripts/install_project_hooks.py \
  --target /path/to/project \
  --host claude \
  --mode warn
```

安装器会把 `SessionStart`、`PreToolUse`、`Stop` 和 `TaskCompleted` 安全合并进 `.claude/settings.json`。完成一次正确收尾后，再把 `.wishgraph/config.json` 切换为 `enforce`。详见 [`docs/memory-sync-hooks.zh-CN.md`](../../docs/memory-sync-hooks.zh-CN.md)。

## 推荐 Claude Code 流程

1. 开始讨论 session：

   ```text
   /wishgraph start this project. If there is no PRD, run the WishGraph intake prompt and grill one decision at a time.
   ```

   如果需要双语输出，追加：`Use bilingual Chinese and English for user-facing prompts and summaries.`

2. 让 WishGraph 创建或更新：

   ```text
   PRD.md
   ARCHITECTURE.md
   CODEMAP.md
   CONVENTIONS.md
   prompts/DISCUSSION_AI.md
   prompts/EXECUTION_AI.md
   prompts/INTEGRATION_AI.md
   tasks/build/*.md
   reports/RUN_REPORT.md
   reports/PROJECT_STATUS.md
   ```

3. 先让讨论 AI 解释任务应串行还是并行，并询问是否创建执行 session。只有人类明确命令后，宿主支持时才由讨论 Agent 为每个已授权规格创建并配置用户可见 Worker，自动交接执行提示词、已批准任务文件，并使用 `<task-id> · <short title> · WG Worker` 命名。不得静默创建或使用隐藏 subagent；不能创建可见 session 时才降级为手动复制。

   明确批准的极小 ad-hoc 修改可以省略 task 文件，但仍要创建唯一不可变执行报告。安全串行批准包含正常临时集成；并行或高风险集成需要明确确认。平台不支持后台任务时，Agent 必须如实切换角色或给出一次性启动指令。

4. 如果讨论 session 需要迁移，提问：

   ```text
   迁移讨论窗口，把当前讨论提示词完整显示出来供我复制。
   ```
