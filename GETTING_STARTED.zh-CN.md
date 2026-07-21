# WishGraph 上手指南

[English](GETTING_STARTED.md) | [简体中文](GETTING_STARTED.zh-CN.md)

这份指南从安装讲到第一次完整的 Discussion → Worker → Integration 流程。如果只想先了解 WishGraph，请从[中文首页](README.zh-CN.md)开始。

## 安装前需要什么

- 一个 Git 仓库。
- Python 3.9 或更高版本。
- Codex 或 Claude Code，用于当前支持的原生宿主路径。

WishGraph 不安装任何 Python 第三方包。安装器会在写入前检查依赖和目标 Git 仓库。

三个概念要分开：

- **全局已安装：**Agent 可以使用 WishGraph。
- **当前项目已启用：**项目根目录存在 `.wishgraph/config.json`，且模式是 `warn` 或 `enforce`。
- **Discussion 已开始：**已启用项目收到明确的“开始讨论”命令。

全局安装不会让所有文件夹自动进入 WishGraph。

## 在当前项目安装

进入需要启用 WishGraph 的 Git 项目，运行一条命令。

### Codex · macOS / Linux

```bash
curl -fsSL https://raw.githubusercontent.com/odopk-spring/wishgraph/v0.1.0/scripts/install-wishgraph.sh | bash -s -- codex --setup-project
```

### Claude Code CLI · macOS / Linux

```bash
curl -fsSL https://raw.githubusercontent.com/odopk-spring/wishgraph/v0.1.0/scripts/install-wishgraph.sh | bash -s -- claude-user --setup-project
```

### Windows PowerShell

Codex：

```powershell
& ([scriptblock]::Create((irm 'https://raw.githubusercontent.com/odopk-spring/wishgraph/v0.1.0/scripts/install-wishgraph.ps1'))) codex -SetupProject
```

Claude Code：

```powershell
& ([scriptblock]::Create((irm 'https://raw.githubusercontent.com/odopk-spring/wishgraph/v0.1.0/scripts/install-wishgraph.ps1'))) claude-user -SetupProject
```

安装器会先检查 Git、Python 和仓库根目录，并把执行安装的 Agent（`current_host`）与项目要支持的宿主（`required_hosts`）分开。默认原子安装 Codex 与 Claude Code 两端适配器，同时保留无关 Hooks。默认 `warn` 是完全非阻断的建议模式：宿主没有执行 Hook 或流程证据不完整时，仍可正常分发任务和使用普通工具。

明确只用单端时，可添加 `--project-hosts codex` 或 `--project-hosts claude`（PowerShell：`-ProjectHosts codex|claude`）。另一端不算缺失，但普通会话也不受保护。Agent 引导安装时会询问同样的三种选择，不会根据当前 Agent 静默决定。

如果 Skill 已经安装，也可以直接告诉 Agent：

```text
在当前项目使用 WishGraph。
```

这句话明确授权推荐的安全配置。“开始讨论”本身不会在未配置项目里自动安装 WishGraph。

## 开始第一次会话

安装成功后：

```text
1. 重新打开当前 Agent 会话
2. 输入：开始讨论
```

新窗口默认保持 neutral。收到命令后，它只读取当前 Project Status、待处理通知和下一步真正需要的 active state。

对于已有项目，WishGraph 会先复用仓库中已经可信的文档。它不应该为了证明安装成功而重命名目录、复制出一套平行文档、创建虚假的 bootstrap Task，或者修改业务代码。

对于空白或还很模糊的项目，Discussion 从一个简短的首问开始：

```text
先不用写完整 PRD。请用几句话告诉我：
1. 你想做一个什么项目？
2. 最先服务谁？
3. 他们第一次打开时最应该完成什么动作？
4. 你会用什么结果判断 v0 做对了？
如果还不确定，可以只回答第 1 点，我会继续一问一问补齐。
```

Discussion 一次只追问一个会改变结果的决定，并提供推荐默认值。项目框架足够清楚后才进入实现。

## 执行第一个 Task

需求明确后，Discussion 会生成一份自包含 Task，至少写清楚：

- 目标和当前状态。
- 允许修改的范围。
- 明确不做什么。
- 依赖和所有权。
- 验证命令或手动检查。
- 对共享项目状态的影响。
- 回滚边界和 Run Report 路径。

然后它请求执行授权。使用准确命令：

```text
执行 012 任务
```

在 Discussion 中，这条命令派发独立 Worker。如果你在同一已启用项目的普通 neutral 新窗口中直接输入它，当前可检查窗口会直接成为 Worker，不再额外创建第二个 Worker；`enforce` 要求先取得 Claim，`warn` 则把 Claim 作为尽力执行的自动化。

授权并不会让 Discussion 自己实现 Task。它会请求当前宿主提供最合适的合法 Worker 路径。

| 宿主路径 | 实际行为 |
| --- | --- |
| 支持可检查 Agent thread 的 Codex 界面 | 宿主创建项目 `wishgraph-worker`；只有返回真实稳定 thread ID 后才记录成功。 |
| 能力检查通过的 Claude Code CLI | Host Adapter 在独立 Worktree 中启动受管后台 Agent，只临时注入本次 Worktree 设置，并保存稳定 session ID。 |
| 原生创建不可用或失败 | Discussion 给出项目目录、Codex/Claude 启动命令、各自配置和 `执行 012`；任选一套复制即可。 |

请求创建进程或 thread 不代表 Task 已经 `running`。Worker 必须通过准确 Task preflight；`enforce` 还要求取得绑定 session、branch、绝对 worktree、scope 和 validation plan 的 Claim。

派发性能目标只覆盖“命令解析 → 规范 Run 授权 → 宿主路由就绪”，目标 p95 小于 3 秒。宿主创建原生 thread/session 和模型启动不在这个时间内。严格模式在真实 ID 和 Claim 就绪前保持 `starting` 或 `awaiting_claim`；建议模式在自动化缺失时可直接按准确批准的 Task 继续。

全局 Claude Adapter 和 Worker Agent 可以服务所有已明确启用的项目。项目级 `.claude/settings.json` 不是必需条件；每次启动注入的设置不会覆盖全局或项目配置。

## Worker 会读取什么

普通 Worker 从下面三类内容开始：

1. 自己的准确 Task 或 Revision。
2. 最小必要的 Project Status 小节。
3. 允许范围真正需要的源码。

稳定角色规则来自已安装的 Skill 和 Host Adapter，因此 WishGraph 不会添加项目级 Prompt 文件。

它默认不读取无关 Task、历史 Run Report 或完整源码树。如果实现需要 Task 没有授权的公共 API、schema、持久化、依赖、权限、安全、隐私或新产品决定，Worker 会停止并把问题交回 Discussion。

收尾时，Worker 运行规定验证，生成一个不可变 Run Report，记录项目状态影响，把工作推进到真实终态，按规则创建一组有边界、线性的 commit，然后释放已经取得的 Claim。

## Integration 和完成提醒

有运行时自动化时，每个 Worker 终态都先进入 `integration_pending`。`warn` 缺少这类自动化时，Worker 直接把报告路径和结果 commit 交回 Discussion。

安全结果会由 Discussion-local Integration 先以不提交方式合并，检查报告和受影响文件，运行组合验证，更新共享项目状态，重写 `reports/PROJECT_STATUS.md`，最后创建集成提交。`enforce` 要求这些动作持有 lease；`warn` 保持 Discussion 本地单写，不因 lease 自动化缺失而阻塞。

系统不会重复询问“是否开始集成”。只有出现具体冲突、风险、兼容性选择或产品决定时，才需要用户判断。

如果 Worker 完成时 Discussion 没有运行，已经取得的 Claim 可以在 Git common runtime 中写入 pending notification。`warn` 没有这类自动化时，可见 Worker 的返回结果就是交接。WishGraph 不使用 daemon、终端轮询、跨窗口 IPC 或自动弹窗。

## 换窗口或换宿主继续

不需要迁移提示词。

在同一项目的新窗口输入：

```text
开始讨论
```

已经处于 Discussion 时可以输入：

```text
刷新项目状态
```

从 Codex 切换到 Claude Code，或反向切换时，严格模式要求该宿主在 `required_hosts` 中并已安装 Adapter。`warn` 下缺少宿主自动化只作提示，可直接把准确 Task 交给可见 Worker，不进入重开循环。持久项目事实可以共享，宿主自己的 thread/session ID 不跨平台复用。

## Revision 和 Worker 复用

属于原 Task 的明确低风险小修订使用 `tasks/revisions/<task-id>-rN.md`。它只记录 parent Task、准确请求、允许范围、针对性验证、状态和报告路径。

旧工作进入终态且旧 scope 清除后，原 Worker thread 可以复用。已经取得的旧 Claim 必须释放；严格模式还要为新 Task 或 Revision 取得新 Claim。同一时间一个 Worker 只能持有一个 active work unit。

任何涉及 API、schema、持久化、迁移、依赖、权限、安全、隐私或新产品决定的修改，都升级为正式后续 Task。

## 已有项目怎样避免文件膨胀

WishGraph 默认使用 native-lite：

- 已经有产品说明时，先核验当前 Task 涉及的关键路径、符号、命令和明显冲突，再决定复用，不创建竞争性的 `PRD.md`。
- 已有架构、代码地图、规范、Issue、Task 或测试事实源能支持当前 Task 时继续复用，并把未知内容写入该 Task。
- 只有缺少合适的当前状态源时，才补充精简 `reports/PROJECT_STATUS.md`。
- `tasks/`、`tasks/revisions/` 和 `reports/runs/` 在首次需要对应工作单元时创建；只有真实运行才生成报告。
- 当前状态保持为重写后的快照，历史留在不可变报告和 Git 中。

标准文件名是默认方案，不是要求已有项目复制一套文档。native-lite 不创建项目级 Prompt、空白 Run Report、文档注册表或持久信任评分，也不限制用户自己的根目录文件和项目原生目录。

## 维护与排障

普通用户可以直接使用自然语言：

| 请求 | 作用 |
| --- | --- |
| `检查 WishGraph 状态` | 固定路径、只读的 Doctor 检查，不扫描业务源码。 |
| `更新这个项目的 WishGraph` | 根据文件指纹安全升级，失败时原子回滚。 |
| `修复当前宿主的 WishGraph Hooks` | 只修复当前宿主，保留无关 Hooks。 |

在 `warn` 下，即使 Hook 没有响应，也不影响讨论和 Worker 分发；只有需要诊断时才运行 Doctor。`enforce` 下可完整重开一次，仍无回执时再使用对应 CLI 的 Hook 审查入口。

Doctor 默认检查配置中的全部 `required_hosts`，并分别报告安装和 Hook 执行状态。`warn` 的顶层 `healthy` 只取决于核心 runtime，即使没有回执也保持可用；`enforce` 才同时要求 Adapter 当前且存在近期回执。

更新全局 Skill 不会静默覆盖已有项目的 `.wishgraph/hooks/`。项目 runtime 应走安全升级路径；未知或本地修改过的生成文件会停止并交给用户检查。

## 严格模式

先使用 `warn`。完整跑通一次后，如果希望阻塞不合规的收尾和提交，再开启严格模式：

```bash
curl -fsSL https://raw.githubusercontent.com/odopk-spring/wishgraph/v0.1.0/scripts/install-wishgraph.sh | bash -s -- codex --setup-project --strict
```

Claude Code 把 `codex` 换成 `claude-user`；PowerShell 使用 `-Strict`。

严格配置会启用 `enforce` 并请求 Git pre-commit 兜底。安装器不会覆盖已有 Git hook，只会给出串联方式。

`enforce` 只通过已安装且已加载的宿主 Adapter 工作，不是操作系统沙箱。没有 Claude Adapter 时，WishGraph 无法在普通 Claude Code 会话内机械检测或阻止写入；Git 兜底也只检查提交阶段。

## 首次验证清单

WishGraph 正常工作时应该满足：

- “开始讨论”只在已启用项目中进入 Discussion。
- 新 Discussion 不扫描完整源码树也能理解当前状态。
- 准确执行命令创建或路由独立、可检查的 Worker。
- `enforce` 下 Worker 取得 Claim 前不能写业务代码或运行实现构建；`warn` 只要求准确批准的 Task、scope 和验证边界，不因 Claim 自动化缺失而阻塞。
- 一个不可变 Run Report 记录真实验证结果。
- 安全 Integration 更新受影响的项目事实，并重写当前状态。
- 新窗口只需“开始讨论”，不需要复制聊天记录或完整提示词。

实现细节见[外置记忆 Hooks](docs/memory-sync-hooks.zh-CN.md)、[状态机规格](docs/orchestration-state-machine.md)和 [Claude Code 适配器](adapters/claude-code/README.zh-CN.md)。
