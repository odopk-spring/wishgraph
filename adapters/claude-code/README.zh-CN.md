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

安装器会把 `SessionStart`、`PreToolUse`、`Stop` 和 `TaskCompleted` 安全合并进 `.claude/settings.json`，在未设置时把 Worktree `baseRef` 设为 `head`，保留已有 Worktree 配置并把 `.wishgraph` 加入 `worktree.symlinkDirectories`，同时安装受管 `.claude/agents/wishgraph-worker.md`。完成一次正确收尾后，再把 `.wishgraph/config.json` 切换为 `enforce`。详见 [`docs/memory-sync-hooks.zh-CN.md`](../../docs/memory-sync-hooks.zh-CN.md)。

## 推荐 Claude Code 流程

1. 在目标项目明确启用 WishGraph：

   ```text
   /wishgraph 在当前项目使用 WishGraph。
   ```

   安全配置完成后当前 session 仍保持 neutral。重新打开 Claude Code，再输入“开始讨论”。只安装全局 Skill，或在未配置项目里单独说“开始讨论”，都不会启用该项目。

2. 每个角色只读所需内容：

   - Discussion 从精简交接、当前 Project Status 和 active state 开始，只有当前问题需要时才打开产品或架构文件。
   - Worker 只读准确 Task/Revision、`prompts/EXECUTION_AI.md`、必要状态，以及 scope 内的源码。
   - Integration 只读选中的报告和报告实际影响的共享文件。

   现有项目优先复用已有同类文件，Task、Revision 和报告目录在首次需要时再创建。

3. 先让 Discussion 解释任务应串行还是并行，并询问 Worker 授权。Claude Code 使用三档能力：

   - `background_session`：只有受管 Agent、`agents --json`、worktree runtime、已授权 Task 和当前 `HEAD` 均兼容时，才运行 `claude --bg --agent wishgraph-worker "执行 <task-id> 任务"`，并用 `claude agents --json --all --cwd <project>` 保存和刷新稳定 session ID。
   - `forked_subagent`：只用于短时、低风险辅助检查，不能成为正式业务 Worker。
   - `manual_command_only`：只输出 `执行 <task-id> 任务`，随后停止 Discussion 的执行动作。

   `claude --bg` 返回并不代表 Task 已进入 `running`；还需要稳定 session ID，真正实现前仍需 Worker Claim。任何降级都不能让 Discussion 修改业务代码。

   `claude agents` 查看后台 session，`claude logs <id>` 查看近期输出，`claude attach <id>` 恢复交互控制，`claude stop <id>` 停止 session。`/tasks` 只查看当前 Claude session 关联的后台工作，不创建 WishGraph Task，也不授予 Claim。

   Claim release 向共享 Git runtime 写入一条幂等 pending notification。绑定的 Discussion 在下一次激活时消费；切换宿主后，明确开始讨论或刷新状态可接管。这是“下次激活时拉取”，不是实时弹窗。安全串行和机械检查证明独立的并行结果由持有 lease 的 Discussion-local Integration 自动集成；风险或冲突只询问具体决定，Integration 不创建额外窗口，也不使用 daemon、轮询、IPC 或弹窗。

4. 如果讨论 session 需要迁移，提问：

   ```text
   迁移讨论窗口，把当前讨论提示词完整显示出来供我复制。
   ```
