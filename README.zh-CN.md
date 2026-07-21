<p align="center">
  <img src="docs/assets/brand/wishgraph-mark.svg" width="88" alt="WishGraph 标志">
</p>

<h1 align="center">WishGraph</h1>

<p align="center"><strong>让 AI 在明确边界内执行，让项目事实可以持续交接。</strong></p>

<p align="center">面向 Codex 与 Claude Code 的按项目协同层：分离规划、执行、证据和集成，同时避免用流程文件填满仓库。</p>

<p align="center">
  <a href="#60-秒安装"><strong>60 秒安装</strong></a> ·
  <a href="#一分钟看懂一次完整流程"><strong>看一次完整流程</strong></a> ·
  <a href="#常见问题">常见问题</a> ·
  <a href="#安全边界">安全边界</a>
</p>

<p align="center">
  <a href="https://github.com/odopk-spring/wishgraph/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/odopk-spring/wishgraph/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="状态：v0.1 public beta" src="https://img.shields.io/badge/status-v0.1%20public%20beta-625DF1">
  <img alt="许可证：PolyForm Noncommercial" src="https://img.shields.io/badge/license-PolyForm%20Noncommercial-14A878">
</p>

<p align="center"><a href="README.md">English</a> · <strong>简体中文</strong></p>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/hero/wishgraph-hero-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/hero/wishgraph-hero-light.svg">
  <img alt="WishGraph 把讨论、Worker 执行、验证证据和最新项目状态连接成可追踪工作循环" src="docs/assets/hero/wishgraph-hero-light.svg">
</picture>

WishGraph 把开放式需求整理成有边界的 Task，把明确授权的工作交给可检查 Worker，并通过真实验证证据和重写后的当前状态完成闭环。

```text
愿望 → 规格 → Task → Worker → 验证 → Run Report → 集成 → 最新项目状态
```

稳定的产品和工程事实优先留在项目已有文档中。WishGraph 只补充可靠交接真正需要的 Task、当前状态和执行证据，因此换窗口、换模型或换宿主时无需重放聊天历史。

## 整体框架

WishGraph 解决的不是“让 Agent 多读一些文档”，而是让不同阶段只读取真正需要的内容。

| 部分 | 作用 |
| --- | --- |
| **项目记忆** | 用 PRD、架构、代码地图和最新状态保存项目规则，而不是保存整段聊天记录。 |
| **Discussion** | 和用户讨论需求、明确边界、生成 Task；不修改业务代码。 |
| **Worker** | 执行一个已授权 Task，并留下验证证据。可由 Discussion 派发到独立 thread，也可在 neutral 窗口直接绑定当前窗口。 |
| **Integration** | 在 Discussion 内部检查结果、更新共享状态；安全时自动完成，遇到实质决定才询问用户。 |

默认读取范围也很小：

- Discussion 从 `reports/PROJECT_STATUS.md`、待处理通知和下一步真正需要的 active runtime 事实开始。
- Worker 只读自己的 Task 或 Revision、执行规则、必要状态和允许范围内的源码。
- Integration 只读本次报告以及确实受到影响的共享文件。

历史报告继续保留，但不会不断堆进最新状态，也不会在每次启动时全部重读。

> WishGraph 按项目启用。全局安装 Skill 只表示“可以使用”；没有明确启用的文件夹仍按普通 Agent 项目运行。

## 一分钟看懂一次完整流程

假设你想给阅读页面增加夜间模式。

### 1. 开始讨论

在已经启用 WishGraph 的项目里输入：

```text
开始讨论
```

你仍然可以像平时一样说：“我想给阅读页面增加夜间模式。”Discussion 会结合当前项目状态确认真正影响范围的问题，例如只改阅读页还是整个 App、跟随系统还是手动切换、怎样验证完成。

讨论明确后，它会生成一份自包含 Task，例如 `012b`，写清楚这次做什么、不做什么、允许修改哪里以及怎样验收。

### 2. 授权执行

你只需输入：

```text
执行 012b 任务
```

WishGraph 会让当前宿主选择最合适的可检查 Worker：

- 支持原生 Agent thread 或后台 session 时，创建独立 Worker 并保存真实 thread/session ID。
- 当前宿主不支持或启动失败时，输出一份精简的跨宿主交接：当前项目目录、Codex 与 Claude Code 各自可复制的启动命令和配置，以及最后一行 `执行 012b`。

Worker 通过 Task 检查并取得 Claim 后才会修改代码。它不会读取无关 Task、全部历史报告或完整源码树。

这里的“3 秒派发”指的是：精确命令被解析、授权写入规范 Run，并产生可执行的宿主路由。原生 thread/session 创建和模型启动可能更慢，取得真实 ID 和 Claim 前只显示 `starting` / `awaiting_claim`，不会假称正在执行。

### 3. 验证并更新项目

Worker 完成后写入不可变 Run Report，记录改了什么、运行了哪些验证、还有什么风险。Discussion 下次激活时收到提醒，并进入本地 Integration：

- 证据完整、没有冲突：自动集成并更新最新项目状态。
- 缺少报告或验证失败：标记阻塞，不假装完成。
- 出现公共 API、产品决定或冲突：只询问那一个具体问题。

下次换窗口、换模型，甚至在 Codex 和 Claude Code 之间切换时，不需要复制完整提示词。打开同一个 Git 项目并输入“开始讨论”，新的 Agent 会从项目文件继续。

### 4. 小修改保持小

如果你看完结果后说“这个蓝色不喜欢，换成暖灰色”，WishGraph 会把它作为原 Task 的轻量 Revision，而不是重新写一份长 Task。只有修改扩展到公共 API、数据结构、依赖、安全或新的产品决定时，才升级为正式后续 Task。

## 60 秒安装

需要 Git 和 Python 3.9+，不需要额外 Python 包。下面的命令会安装 Skill，并在**当前 Git 项目**中启用安全模式 Hooks。项目配置默认同时安装 Codex 与 Claude Code 适配器；这是推荐默认值，不代表必须同时使用两端。

### Codex · macOS / Linux

在目标项目目录运行：

```bash
curl -fsSL https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.sh | bash -s -- codex --setup-project
```

### Claude Code CLI · macOS / Linux

在目标项目目录运行：

```bash
curl -fsSL https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.sh | bash -s -- claude-user --setup-project
```

### Windows PowerShell

Codex：

```powershell
& ([scriptblock]::Create((irm 'https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.ps1'))) codex -SetupProject
```

Claude Code：

```powershell
& ([scriptblock]::Create((irm 'https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.ps1'))) claude-user -SetupProject
```

安装完成后只做两件事：

```text
1. 重新打开当前 Agent 会话
2. 输入：开始讨论
```

如果只想保护一个宿主，添加 `--project-hosts codex` 或 `--project-hosts claude`（PowerShell：`-ProjectHosts codex|claude`）。选择会保存为 `required_hosts`；未选择的宿主既不算安装失败，也不受 WishGraph 保护。

默认 `warn` 是安静的建议模式：普通文档和闭环问题静默且不阻止，权限和状态完整性底线仍然阻止。跑通一次完整流程后，再按需使用 `--strict`（PowerShell 为 `-Strict`）开启严格门禁。

如果你希望由 Agent 引导安装，也可以在 Codex 中先用 `$skill-installer` 安装本仓库的 `skills/wishgraph`，或在 Claude Code 安装后运行 `/wishgraph`，然后说：

```text
在当前项目使用 WishGraph。
```

更完整的安装方式、已有项目接入和故障恢复见 [中文上手指南](GETTING_STARTED.zh-CN.md)。

`warn` 和 `enforce` 只对已经安装并实际加载 WishGraph Adapter 的宿主生效，不是操作系统沙箱。每个选中的 Agent 在第一次执行受管 Task 前都要重新打开一次会话，让 WishGraph 确认本会话 Hook 回执。

用户级安装会合并一个全局 Adapter；它在未明确启用 WishGraph 的项目中保持静默。Claude 后台 Worker 的 Worktree 设置由每次启动临时注入，已启用项目无需重复创建 `.claude/settings.json`，也不会覆盖用户已有设置。

## 宿主适配

你不需要选择“新窗口、后台会话还是子代理”。WishGraph 先判断当前宿主实际提供的能力，再选择最合适的 Worker 容器；原生创建不可用时，严格退回一行人工执行命令。

| 宿主 | 首选 Worker | 无法原生创建时 | 不变的边界 |
| --- | --- | --- | --- |
| **Codex** | 当前界面支持时，使用可查看、可追踪、可控制的 Agent thread。 | 给出项目目录、Codex/Claude 启动命令和 Task 口令。 | 精确授权、Claim、scope、验证、Run Report 和 Integration。 |
| **Claude Code CLI** | 能力与 Agent 定义通过检查时，在独立 Worktree 中使用受管 `claude --bg --agent wishgraph-worker` 后台 session。 | 给出同一份跨宿主交接。 | 同上；`/tasks` 只用于查看后台工作，不创建 WishGraph Task。 |
| **其他宿主** | 使用宿主真正可检查的独立 thread 或窗口。 | 使用通用的跨宿主启动交接。 | 宿主能力不足不会扩大 Discussion 的执行权限。 |

Python 3.9+ 是 WishGraph runtime 的要求，不代表你的业务项目必须使用 Python。

## 常见问题

### 安装后，每个项目都会自动进入 WishGraph 吗？

不会。Skill 可以全局安装，但每个项目都必须明确启用。未启用项目中的“开始讨论”只是普通文本，不会创建 WishGraph 文件或启动流程。

### 换窗口或换 Agent 时，需要复制迁移提示词吗？

不需要。WishGraph 的交接状态保存在项目文件和 Git common runtime 中，不在聊天记录里。新的窗口打开同一个项目后输入“开始讨论”；切换宿主时，先确认它在 `required_hosts` 中，否则需要明确启用、安装对应 Adapter 并重开会话。完整提示词复制不是正常流程，也不是 Claude Code 的迁移要求。

### `开始讨论`、`执行 012 任务` 和 `刷新项目状态` 分别做什么？

- `开始讨论`：让当前中立窗口进入 Discussion，并读取精简的最新状态。
- `执行 012 任务`：在 Discussion 中派发独立 Worker；在普通 neutral 窗口中直接把当前窗口绑定为 Worker，不再绕行创建第二个窗口。两种入口都准确匹配 `012`，不会碰到 `012b` 或 `012ba`。
- `刷新项目状态`：刷新 active state 和相关终态证据，默认不遍历完整源码树和历史报告。

### Codex 和 Claude Code 的体验一样吗？

用户命令、Task、Claim、验证和项目状态相同，Worker 容器由宿主能力决定。具体差异见上方[宿主适配](#宿主适配)；任何原生启动失败都不会让 Discussion 接管业务代码。

### Worker 在后台完成后会主动弹窗吗？

不会。WishGraph 不运行 daemon、终端轮询或跨窗口 IPC。Worker 正常结束时写入 pending notification；Discussion 在下一次 SessionStart、输入或明确刷新时读取并标记已读。

### 项目会不会生成大量文件？

已有项目默认采用 native-lite：只核验当前 Task 需要的路径、符号、命令和明显冲突，复用可信的 README、产品文档、架构、规范和测试，并只补充缺失的 Project Status。WishGraph 不创建项目级 Prompt、文档注册表、信任状态或空白 Run Report；Task、Revision 和报告目录仅在首次需要时出现，`PROJECT_STATUS.md` 始终是唯一面向用户的动态快照。

### 小改动也必须走完整 Task 吗？

不需要。明确、低风险、属于原 Task 的局部反馈走轻量 Revision。修改一旦涉及公共 API、schema、持久化、依赖、权限、安全、隐私或新产品决定，就回到 Discussion 创建正式 Task。

### 可以在 Codex 和 Claude Code 之间切换吗？

可以。PRD、Task、报告和项目状态都在同一个 Git 项目中。宿主自己的 thread/session ID 不跨平台复用，但新的 Agent 可以读取同一 Task、取得新的合法 Claim 并继续流程。

### WishGraph 是沙箱吗？

不是。Hooks 可以拦截宿主暴露的写入、构建、提交和生命周期事件，但不能替代操作系统权限或容器隔离。源码读取门禁也取决于宿主是否暴露完整 Hook 能力。

## 安全边界

- **明确授权：**正式 Worker 必须对应准确 Task 或 Revision，不能从模糊聊天中自行获得执行权限。
- **角色隔离：**Discussion 负责讨论、Task、Integration 和结果呈现，不实现业务代码，也不运行 Worker 的实现验证。
- **Claim 绑定：**业务写入和构建要求 Claim 绑定 Task、session、branch、绝对 worktree、scope 和 validation plan。
- **可检查 Worker：**只有拥有稳定 thread/session ID、独立上下文、可查看和可控制过程的 Agent 才能成为 Formal Worker；隐藏子代理只能做只读辅助。
- **单写者状态：**Worker 在 Run Report 中提出共享状态更新，只有持有 Integration lease 的 Discussion-local Integration 才能更新共享项目事实。
- **真实终态：**自然语言“完成了”不算证据；Task 状态、Run Report、验证结果和 Claim closeout 必须一致。
- **本机边界：**Claim 能协调共享同一个本地 Git common directory 的 worktree，不是跨机器分布式锁。

WishGraph 当前是 **v0.1 public beta**。CI 在 Ubuntu 与 macOS 的 Python 3.9、3.13 上运行完整测试，并在 Windows Python 3.13 上运行完整测试和 PowerShell 安装路径；独立冷进程基准检查 Hook 延迟与源码树规模耦合。进入稳定 v1 前仍需要更多真实项目和宿主版本验证。

## 项目记忆放在哪里

| 文件 | 人类可以把它理解成 |
| --- | --- |
| `PRD.md` | 目标说明：做什么、为什么做、暂时不做什么。 |
| `ARCHITECTURE.md` | 结构图：模块、依赖、数据流和边界。 |
| `CODEMAP.md` | 地址簿：功能、入口、状态、存储和测试分别在哪里。 |
| `CONVENTIONS.md` | 项目自己的构建、测试、编码、权限和 Git 规则。 |
| `tasks/*.md` | 正式 Task：范围、非目标、验证和回滚边界。 |
| `tasks/revisions/*.md` | 低风险小修订。 |
| `reports/runs/*.md` | Worker 的不可变执行与验证证据。 |
| `reports/PROJECT_STATUS.md` | 当前仪表盘：最新结果、风险、进行中工作和下一步。 |

已有项目不必机械创建全部文件。WishGraph 会优先复用已经承担相同职责的原生文档。

WishGraph 只创建上述明确命名的文档和目录，不会管控仓库根目录的其他内容。`AGENTS.md`、`CLAUDE.md`、框架配置和项目原生目录均保持用户所有；WishGraph 也不会向用户项目复制项目级 Prompt 或空白 Run Report 模板。

## 继续深入

信息优先级：当前行为以 Skill runtime 和自动测试为准，用户体验以本页和上手指南为准，详细规则以 `skills/wishgraph/references/` 为准。`docs/` 是便于 GitHub 阅读的同步说明，不另立一套行为。

| 你想了解 | 文档 |
| --- | --- |
| 从安装到第一次完整流程 | [中文上手指南](GETTING_STARTED.zh-CN.md) |
| 方法论和“项目压缩”思路 | [WishGraph 方法论](docs/wishgraph-method.md) |
| 角色、状态与命令解析 | [编排状态机](docs/orchestration-state-machine.md) |
| Hooks、门禁、性能与宿主限制 | [外置记忆 Hooks](docs/memory-sync-hooks.zh-CN.md) |
| Claude Code CLI 的真实适配 | [Claude Code 中文适配器](adapters/claude-code/README.zh-CN.md) |
| 不支持原生 Skill 的工具 | [通用 Agent 适配器](adapters/generic/README.zh-CN.md) |
| 仓库里的模板 | [Templates](templates/README.md) |

```text
skills/wishgraph/   可安装 Skill 和内置 runtime
templates/          可人工查看的中英文项目模板
adapters/           Claude Code 与通用 Agent 适配说明
docs/               方法、状态机和 Hooks 参考
scripts/            Bash 与 PowerShell 安装器
tests/              安装器和 runtime 回归测试
```

## 社区与联系

- Bug 和明确的功能建议：[GitHub Issues](https://github.com/odopk-spring/wishgraph/issues)
- 商业授权与合作：[zuelfma@foxmail.com](mailto:zuelfma@foxmail.com)
- 中文文章、实践记录与项目更新：微信公众号 **有言以对Spring**

<img src="docs/assets/community/youyanyidui-spring-wechat.jpg" width="180" alt="微信公众号有言以对Spring的二维码">

正式版本、安装说明、兼容性和项目状态仍以本仓库为准。

## 许可证

WishGraph 使用 [PolyForm Noncommercial License 1.0.0](LICENSE)。你可以为非商业目的下载、学习、修改和再分发；商业使用需要获得著作权人的单独书面许可。它是 source-available 非商业许可证，不是 OSI 开源许可证。
