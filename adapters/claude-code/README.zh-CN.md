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
/wishgraph start this project from my rough idea
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

`CLAUDE.md` 用于 always-loaded 项目规则。较大的任务过程应留在 `/wishgraph` skill 和 WishGraph 项目文件中，例如 `PRD.md`、`CODEMAP.md`、`.tasks/build/*.md` 和 `reports/DEV_REPORT.md`。

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
   .tasks/build/*.md
   reports/DEV_REPORT.md
   ```

3. 开启新的执行 session，粘贴执行提示词和已批准任务文件；也可以再次调用 `/wishgraph`，要求它严格按指定任务执行。

4. 如果讨论 session 需要迁移，提问：

   ```text
   迁移讨论窗口，把当前讨论提示词完整显示出来供我复制。
   ```
