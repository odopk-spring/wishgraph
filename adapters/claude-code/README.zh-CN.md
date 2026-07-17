# Claude Code CLI 适配器

[English](README.md) | [简体中文](README.zh-CN.md)

WishGraph 在 Claude Code 中使用原生 Skill、项目 Hooks 和受管 `wishgraph-worker` Agent。正常使用不需要复制完整提示词，也不需要手工“迁移讨论窗口”。项目状态保存在仓库里，新会话打开同一项目后输入“开始讨论”即可继续。

## 60 秒安装

在目标 Git 项目中运行：

```bash
curl -fsSL https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.sh | bash -s -- claude-user --setup-project
```

Windows PowerShell：

```powershell
& ([scriptblock]::Create((irm 'https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.ps1'))) claude-user -SetupProject
```

安装完成后：

```text
1. 重新打开 Claude Code 会话
2. 输入：开始讨论
```

脚本会：

- 把 Skill 安装到 `~/.claude/skills/wishgraph/`，因此可以使用 `/wishgraph`。
- 在当前项目安装 `.wishgraph/` runtime。
- 默认写入 `required_hosts: [codex, claude]` 并原子安装两端项目适配器；只有明确只用 Claude 时才添加 `--project-hosts claude`。
- 安装一个用户级 Adapter；未明确启用 WishGraph 的项目中它保持静默，项目级 Hooks 继续作为兼容路径。
- 安装受管 `.claude/agents/wishgraph-worker.md`。
- 每次启动临时传入最小 Worktree 配置，不改写用户或项目现有设置，并让隔离 worktree 可以访问 `.wishgraph` runtime。

全局 Adapter 与受管 Agent 可以服务所有通过 `.wishgraph/config.json` 明确加入的项目；项目无需重复创建 `.claude/settings.json`。

默认 `warn` 模式只提醒，不阻止结束或提交。完整跑通一次后，可在安装命令后追加 `--strict`；PowerShell 使用 `-Strict`。

## 日常使用

```text
开始讨论
执行 012 任务
刷新项目状态
```

- Discussion 只读取精简交接、当前 Project Status 和 active state；其他文档按需打开。
- Worker 只读取准确 Task 或 Revision、`prompts/EXECUTION_AI.md`、必要状态和 scope 内源码。
- Integration 只读取本次报告和确实受到影响的共享文件。

在另一个 Claude Code 窗口继续时，不需要输出或复制 `prompts/DISCUSSION_AI.md`。打开同一项目后输入“开始讨论”。从 Codex 切换过来时，先确认 Claude 已列入 `required_hosts`，必要时安装或修复 Adapter，重开会话后再使用同一入口。

## Worker 怎样启动

Discussion 收到准确授权后，Host Adapter 检测当前 Claude CLI 的实际能力，并按下面顺序选择：

| 能力档 | 行为 |
| --- | --- |
| `background_session` | 运行等价于 `claude --bg --agent wishgraph-worker --worktree <unique> --settings <ephemeral-json> "执行 <task-id> 任务"` 的命令，查询 `claude agents --json --all --cwd <project>`，保存稳定 session ID 和实际 worktree。 |
| `forked_subagent` | 只用于短时、低风险、默认只读的辅助检查；不能成为正式业务 Worker。 |
| `manual_command_only` | 只输出 `执行 <task-id> 任务`，Discussion 随即停止执行动作。 |

进入 `background_session` 需要同时满足：

- 当前 CLI 支持 `--bg`、`agents --json`、`--worktree` 和 `--settings`。
- 受管 `wishgraph-worker` Agent 定义存在。
- 每次启动传入的 Worktree 配置能让隔离 Worker 使用同一 runtime。
- Task 已得到明确授权，并且记录与当前 `HEAD` 一致。

`claude --bg` 返回不代表 Task 已经 `running`。WishGraph 还必须保存真实 session ID；Worker 进入实际 worktree 后必须取得绑定 Task、session、branch、绝对 worktree、scope 和 validation plan 的 Claim。

任何检测或启动失败都严格降级为：

```text
执行 <task-id> 任务
```

Discussion 不会因为 Claude 后台能力不可用而直接修改业务代码。

## 查看和控制后台 Worker

```bash
claude agents --json --all --cwd /path/to/project
claude agents --cwd /path/to/project
claude --resume <full-session-id>
```

- `claude agents --json` 为 WishGraph 刷新提供结构化 session 状态。
- `claude agents --cwd` 打开 Claude 原生交互视图，用于查看和控制。
- 适合恢复时，`claude --resume` 使用完整稳定 session ID 继续指定会话。
- 当前 Claude Code 不提供 `claude logs`、`claude attach` 或 `claude stop` 子命令。WishGraph 不调用也不宣传它们；已创建但验证失败的 session 会明确记录为 `manual_intervention_required`。
- `/tasks` 只查看当前 Claude session 关联的后台工作，不创建 WishGraph Task，也不授予 Claim。

WishGraph 只有在 Task 终态、不可变 Run Report、验证结果和已释放 Claim 相互一致时，才进入 Integration。

## Worker 完成后

正常 Claim release 会在共享 Git runtime 中写入一条 pending notification。Discussion 在下一次 SessionStart、输入或明确刷新时消费并标记已读。

这是“下次激活时读取”，不是实时推送。WishGraph 不运行 daemon、终端轮询、跨终端 IPC 或自动弹窗。安全结果自动进入 Discussion-local Integration；冲突、风险和产品决定只询问具体问题。

## `CLAUDE.md` 是否必须

不是。正常的 Skill + `--setup-project` 路径已经可以完成启用、Hooks、Worker 定义和项目状态读取。

本目录的 [`CLAUDE.zh-CN.md`](CLAUDE.zh-CN.md) 只是可选的 always-loaded instruction bridge，适合团队明确希望每个 Claude 会话都预先知道 WishGraph 角色规则时使用。复制它不会自动启用项目，也不会安装 runtime、Hooks 或机械门禁。

## 排障

重新打开会话后，如果“开始讨论”没有响应：

1. 输入 `检查 WishGraph 状态`，让 WishGraph Doctor 做固定路径只读检查。
2. 必要时运行 `claude doctor`，检查 Claude Code 自身配置。
3. 如果 Skill 已更新而项目 runtime 仍旧，输入 `更新这个项目的 WishGraph`。
4. 如果只缺当前 Claude 适配器，输入 `修复当前宿主的 WishGraph Hooks`。

更新全局 Skill 不会静默覆盖项目中的 `.wishgraph/hooks/`。未知或本地修改过的 runtime 会停止并交给用户检查。

## 边界

- Hook 不会启动 Agent；Host Adapter 只在已有明确 Task 授权后执行宿主动作。
- Explore、Plan、`/fork` 和隐藏子代理默认都是 Helper，不能获得 Worker Claim。
- 写入和构建门禁覆盖 Claude 暴露给 Hooks 的工具路径，不是操作系统沙箱。
- 只有 Claude Adapter 已安装并加载时，Claude Code 会话才受到机械门禁；单独设置 `mode: enforce` 无法拦截。
- 一个 Worker 同一时间只能绑定一个 Task 或 Revision；复用前必须释放旧 Claim。
- Claim 只协调共享同一个本地 Git common directory 的 worktree，不是跨机器分布式锁。

协议细节见[状态机规格](../../docs/orchestration-state-machine.md)和[外置记忆 Hooks](../../docs/memory-sync-hooks.zh-CN.md)。

官方参考：[Claude Code Skills](https://code.claude.com/docs/en/skills) · [`CLAUDE.md` memory](https://code.claude.com/docs/en/memory)
