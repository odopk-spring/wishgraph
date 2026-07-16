# WishGraph

[English](README.md) | [简体中文](README.zh-CN.md)

[![CI](https://github.com/odopk-spring/wishgraph/actions/workflows/ci.yml/badge.svg)](https://github.com/odopk-spring/wishgraph/actions/workflows/ci.yml)
![状态](https://img.shields.io/badge/status-v0.1%20public%20beta-625DF1)
![Python](https://img.shields.io/badge/Python-3.9%2B-2D72E8)
![Codex](https://img.shields.io/badge/agent-Codex-172033)
![Claude Code](https://img.shields.io/badge/agent-Claude%20Code-172033)
![许可证](https://img.shields.io/badge/license-PolyForm%20Noncommercial-14A878)

**为 AI 编程 Agent 提供持久的项目记忆和执行边界。**

WishGraph 把产品意图、架构、任务范围、执行证据和最新项目状态保存在仓库中。Codex 与 Claude Code 可以从精简、共享的项目事实继续工作，不必把聊天记录或每次遍历完整源码树当作项目记忆。

![讨论、可见 Worker、集成、再讨论](docs/assets/wishgraph-simple-loop-zh.svg)

[60 秒开始](#60-秒开始) · [理解工作流程](#一个项目三类职责) · [浏览文档](docs/README.md) · [English](README.md)

> WishGraph 按项目选择启用。全局安装 Skill 只表示它随时可用；用户没有明确启用的项目仍按普通 Agent 项目运行。

所有支持的宿主都使用同一套首次流程：

```text
1. 在项目里启用 WishGraph
2. 重新打开当前 Agent 会话
3. 输入：开始讨论
```

## 实际使用是什么样

项目启用 WishGraph 后，日常入口只有几条简短的自然语言命令：

```text
开始讨论。
执行 012 号任务。
刷新项目状态。
```

- **开始讨论**：读取精简的当前状态入口，进入规划和讨论。
- **执行 012 号任务**：授权并路由准确匹配的 Task，再由 Host Adapter 尝试当前宿主真实可用的 Formal Worker 容器。
- **刷新项目状态**：读取当前快照和相关终态报告，默认不遍历完整源码树。

“把这个按钮换成暖灰色”这类目标明确、风险较低的小改动会成为原 Task 的轻量 Revision。Worker 窗口释放旧 Task 并获取新 Claim 后也可以继续执行下一个任务。小修订保持轻量，同时仍保留验证和记录。

授权后的实际行为取决于宿主，但降级不会伪装成已启动：

| 宿主 | 优先 Formal Worker | 何时接受原生容器 |
| --- | --- | --- |
| Codex App / CLI / IDE | 项目级 `wishgraph-worker` 自定义 Agent thread | 宿主返回真实 thread ID，WishGraph 注册成功 |
| Claude Code CLI | 在隔离 worktree 中运行 `claude --bg --agent wishgraph-worker "执行 <task-id> 任务"` | 稳定 Claude session ID 已保存 |
| 不支持或原生路由不可用 | 用户根据一行命令打开可检查的执行会话 | 新会话通过 Task preflight 并取得 Claim |

Hook 只准备和记录路由，不会创建 Codex Agent。Claude 后台启动也只有在受管 Agent、`agents --json`、worktree runtime、已授权 Task 与当前 `HEAD` 均兼容时，才由 Host Adapter 执行。任何原生路由失败都只输出 `执行 <task-id> 任务`，不会让 Discussion 接管实现。

无论哪个宿主，只有 Worker 通过准确 preflight 并取得 Claim 后，才开始业务实现。

## 60 秒开始

### Codex

先让 Codex 安装 Skill：

```text
Use $skill-installer to install https://github.com/odopk-spring/wishgraph/tree/main/skills/wishgraph
```

然后打开目标项目并启用 WishGraph：

```text
在当前项目使用 WishGraph。
```

重新打开 Codex 会话，再输入“开始讨论”。

也可以在终端一次安装 Skill 和安全模式的项目 Hooks：

```bash
curl -fsSL https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.sh | bash -s -- codex --setup-project
```

### Claude Code

在目标项目中执行下面的命令，重新打开 Claude Code CLI 会话，再输入“开始讨论”：

```bash
curl -fsSL https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.sh | bash -s -- claude-user --setup-project
```

### Windows PowerShell

```powershell
& ([scriptblock]::Create((irm 'https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.ps1'))) codex -SetupProject
```

安全配置默认使用 `warn` 模式，不会阻止提交。完整跑通一次工作循环后，可以在 Bash 使用 `--strict`，或在 PowerShell 使用 `-Strict` 开启严格检查。其他安装目标和恢复步骤见 [Getting Started](GETTING_STARTED.md)。

如果重新打开会话后输入“开始讨论”仍没有响应，再运行 WishGraph Doctor。Claude Code CLI 用户可以额外运行 `claude doctor`。这些属于排障步骤，不是正常安装流程。

## 一个项目，三类职责

| 职责 | 运行位置 | 负责内容 |
| --- | --- | --- |
| **Discussion** | 用户长期使用的讨论窗口 | 澄清意图、创建有边界的 Task Spec、路由 Worker、集成结果并呈现决定；不在这里实现业务代码。 |
| **Worker** | 独立、用户可见的执行窗口 | 认领一个 Task 或 Revision，只修改允许的范围，完成验证并写入不可变 Run Report。 |
| **Integration** | Discussion 内部的临时阶段 | 评估终态报告、运行组合验证、更新共享项目状态；只有遇到实质产品决定或风险时才询问用户。 |

Integration 是流程阶段，不是隐藏 Agent，也不会创建第四个窗口。如果 Worker 完成时 Discussion 没有运行，Claim release 会在共享 Git runtime 中写入一条 pending notification。绑定的 Discussion 在下一次激活时消费并标记已读；切换宿主后，明确“开始讨论”或刷新项目状态可以接管。这里没有 daemon、终端轮询、IPC 或自动弹窗。

Codex 优先使用项目 `wishgraph-worker` 的可见、可检查 Agent thread；Claude Code CLI 优先使用受管原生后台 session。Explorer、Reviewer、Plan、`/fork` 和隐藏 Agent 只能作为 Helper，不能因为是子代理就获得 Worker Claim。

## 人与 Agent 共享的文件

| 入口 | 用途 |
| --- | --- |
| `PRD.md` | 当前目标、范围、路线图和产品决定 |
| `ARCHITECTURE.md` + `CODEMAP.md` | 系统边界，以及功能到源文件的映射 |
| `CONVENTIONS.md` | 协作、验证和 Git 规则 |
| `tasks/build/*.md` | 有明确边界的正式 Task |
| `tasks/revisions/*.md` | 与原 Task 关联的小修订，例如 `012-r1` |
| `reports/runs/*.md` | Worker 的不可变执行证据 |
| `reports/PROJECT_STATUS.md` | 最新集成快照，也是人类最快的项目入口 |

便于人阅读的项目语义保存在 Markdown 中。小型、带版本的 JSON 块只记录授权、Claim、验证和集成状态等机械事实。最新状态文件始终重写为当前快照；执行历史保留在不可变报告中，不会不断堆进状态首页。

## 内置维护能力

项目启用后，Skill 会把下面的请求路由到边界明确的维护动作：

| 请求 | 结果 |
| --- | --- |
| `检查 WishGraph 状态` | 只读检查安装文件和最近观测到的宿主执行 |
| `更新这个项目的 WishGraph` | 通过文件指纹确认来源，安全升级并支持失败回滚 |
| `修复当前宿主的 WishGraph Hooks` | 只修复当前宿主，保留其他工具的 Hooks |

Doctor 会区分“配置正确”和“宿主最近确实调用过”。如果实际触发仍未确认，Codex 用户可通过 `/hooks` 复核；Claude Code CLI 用户可以运行 `claude doctor`。

## 安全边界与当前限制

- Worker 需要用户明确授权，并持有绑定 Task、session、branch、worktree、scope 和验证计划的有效 Claim。
- 写入和构建门禁覆盖宿主支持的原生工具与可识别命令。源码读取能否拦截取决于宿主能力；Hooks 也不是操作系统沙箱。
- Claim 在共享同一本地 Git common directory 的 worktree 之间原子生效，但不是跨机器的分布式锁。
- 正常退出的 Worker 必须释放 Claim 并持久化提醒；宿主进程被强制结束时可能绕过 terminal Hook，下一次 Discussion 只能根据 stale Claim 或结构化宿主状态恢复，不能承诺实时推送。
- 安全结果可以直接进入集成，不再询问“是否开始集成”。冲突、公共 API 变化、新产品决定、证据缺失等实质风险会回到 Discussion，询问具体选择。
- Hooks 负责暴露和约束流程状态，不会自行启动 Worker、合并代码或决定产品含义。

WishGraph 当前是 **v0.1 public beta**。Skill 已通过校验，安装和运行时生命周期已有自动化测试，Codex 与 Claude Code 路径也有明确文档。进入稳定 v1 之前，仍需要更多真实项目和宿主版本验证。

## 浏览仓库

| 目标 | 从这里开始 |
| --- | --- |
| 跟随引导完成配置 | [Getting Started](GETTING_STARTED.md) |
| 理解方法和核心概念 | [WishGraph 方法论](docs/wishgraph-method.md) |
| 查看状态机与角色边界 | [编排状态机](docs/orchestration-state-machine.md) |
| 查看 Hooks 协议和宿主限制 | [外置记忆 Hooks](docs/memory-sync-hooks.zh-CN.md) |
| 适配 Claude Code | [Claude Code 中文适配器](adapters/claude-code/README.zh-CN.md) |
| 手动浏览模板 | [Templates](templates/README.md) |

```text
skills/wishgraph/   可安装 Skill 与内置运行时
templates/          英文和中文项目记忆模板
adapters/           Claude Code 与通用 Agent 适配说明
docs/               方法、协议与工作流程文档
scripts/            Bash 和 PowerShell 安装器
tests/              运行时与安装器回归测试
```

WishGraph 支持英文、简体中文和双语项目记忆。命令、路径、标识符和结构化状态保持语言无关。

## 许可证

WishGraph 使用 [PolyForm Noncommercial License 1.0.0](LICENSE)。你可以为非商业目的下载、学习、修改与再分发；商业使用需要获得著作权人的单独书面许可。它是 source-available 非商业许可证，不是 OSI 开源许可证。
