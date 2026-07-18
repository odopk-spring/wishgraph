# WishGraph 流程控制状态机

- 状态：Implemented
- 范围：Discussion、Formal Worker、Helper、Integration 与 Review
- 权威实现：`skills/wishgraph/assets/hooks/`
- 详细规则：`skills/wishgraph/references/orchestration-state-machine.md`、`worker-execution.md`、`task-revisions.md`、`integration-flow.md`

本页说明用户会遇到的流程和当前实现边界。它不复制全部内部字段，也不固定 runtime 版本号；安装版本以 `.wishgraph/hooks/runtime-manifest.json` 和 Doctor 输出为准。

## 1. 最短使用流程

WishGraph 按项目显式启用。全局安装 Skill 只表示“可用”，不会改变所有项目。

```text
1. 在项目里明确说：使用 WishGraph
2. 完成安全配置后重新打开当前 Agent 会话
3. 输入：开始讨论
```

项目没有已启用的 `.wishgraph/config.json` 时，“开始讨论”“刷新项目状态”“执行 012 任务”都只是普通文本，不触发 WishGraph，也不创建文件。

| 意图 | 命令 | 读取范围 |
| --- | --- | --- |
| 进入讨论 | `开始讨论` / `Start discussion` | 精简交接、当前 Project Status、active state |
| 执行任务 | `执行 012 任务` / `Execute task 012` | 精确 Task；授权后再路由 Worker |
| 刷新状态 | `刷新项目状态` / `Refresh project status` | 当前候选 Task、Claim 和相关终态报告 |

默认刷新不会读取完整源码树、全部历史报告或无关 Task。只有 `status --full` 用于显式历史诊断。

## 2. 角色、阶段与 Agent 类型

| 概念 | 当前定义 |
| --- | --- |
| Discussion | 用户长期使用的讨论角色；负责规划、Task、路由、Integration 和结果呈现，不实现业务代码 |
| Formal Worker | 独立、用户可见、可检查、可控制的 Agent thread 或窗口；一次绑定一个 Task 或 Revision |
| Helper Subagent | 探索、检索、日志分析、审查或短时验证辅助；默认只读，没有 Worker Claim |
| Hidden/Internal Agent | 用户无法独立检查和追踪；不能成为 Formal Worker |
| Integration | Discussion 内部的临时 phase，不是角色，也不创建第四个窗口 |
| Review | Discussion 向用户呈现结果的状态，不是第四个 Agent |

Formal Worker 不要求一定是“物理新窗口”，但必须有稳定 thread/session ID、独立上下文、可查看与控制的过程、精确 Task/Claim/branch/worktree 绑定、写入和构建门禁，以及结构化终态与 Run Report。

Agent 身份不会自动产生权限。Codex Explorer、Reviewer，Claude Explore、Plan、`/fork` 和隐藏子代理默认都是 Helper，不能取得 Worker Claim。Formal Worker 也不得继续创建另一个 Formal Worker。

## 3. 四个正交状态

### Session Role

```text
neutral
discussion
worker
```

新会话默认 `neutral`。启用项目后仍需明确“开始讨论”才能进入 `discussion`；精确执行命令通过 preflight 和 Claim 后才能进入 `worker`。

### Task Lifecycle

```text
draft -> approved -> running -> completed|blocked|incomplete -> integrated -> reviewed
```

- `approved`：Task 已获得准确 Worker 启动授权。
- `running`：存在真实 Worker 和有效 Claim。
- `completed`：存在终态记录与预期 Run Report。
- `integrated`：Integration lease、合并、组合验证和共享状态收尾完成。
- `reviewed`：Discussion 已呈现，用户接受结果。

### Flow Phase

```text
planning
awaiting_worker_authorization
routing_worker
waiting_for_user_launch
waiting_for_worker
integration_pending
integrating
decision_required
presenting_result
```

### Expected Transition

同一 Discussion 最多保存一个结构化 `expected_transition`，例如：

```text
approve_worker_launch(012)
wait_for_worker(012)
auto_integrate(012, reports/runs/012-attempt-1.md)
resolve_conflict(012, api-compatibility)
accept_result(012, integration-012)
```

“可以”“开始吧”“执行吧”只有在 transition 唯一且仍有效时才有意义。两个 Task 同时等待授权时，系统必须询问准确 ID。

在刚刚询问某个 Task 是否启动的上下文中，普通确认也可以推进，例如“行，就按推荐执行吧”或“Sounds good, go ahead”。带有否定、条件、范围修改、问题或另一个 Task 的回复不会启动 Worker。

## 4. 命令识别边界

低风险入口可以归一化大小写、空格、终止标点、引号和少量礼貌词，但仍只与有限 alias 做整句相等匹配。

- 可识别：`进入讨论模式`、`回到 Discussion`、`Begin discussion`、`Reload project status`。
- 不识别：`我们讨论一下颜色`、`刷新项目状态并执行 012`。

执行、停止、重试和接管属于高风险命令，保持严格匹配：

```text
执行 002 任务
停止 002 任务
重新执行 002 任务
接管 002 任务
```

执行命令后可选地附上紧凑的模型配置，例如 `执行 002 terra 极高`、`execute 002 sonnet high`。Discussion 会根据用户对质量、速度、成本、额度和可用模型的要求，以及本 Task 的复杂度和风险，形成这一次的建议；不会给所有用户固定同一组合。用户只回复“批准”或不附加配置时使用本 Task 建议；没有可靠建议才保留宿主当前默认。未知后缀不会被当成执行授权；属于另一宿主的模型名不会被擅自翻译。

自动创建失败时，系统给出一份跨宿主交接：准确项目目录、Codex 与 Claude Code 各自可复制的启动命令、各自模型/推理强度，以及最后一行 `执行 002`。模型选择放在启动命令里，Task 口令保持稳定。

Formal Worker 使用本地 Git 的 `HEAD` 作为独立 worktree 基线：只需要本地仓库至少有一个 commit，不需要 GitHub、`origin` 或任何 remote。没有首个 commit 时，系统会要求先确认并建立本地基线提交。

`002`、`002b`、`002ba`、`002-r1` 和 `002-r10` 都是不同结构化 ID，不能按文件名前缀猜测。

## 5. 状态机与宿主的分工

```text
FlowPlan = reduce(current_state, user_event, host_capability)
```

- `workflow_state.py`：类型、结构化状态、命令解析。
- `policy.py`：纯状态转换和拒绝理由。
- `host_adapter.py`：把唯一下一动作映射到当前宿主。
- `git_state.py`：Git 事实、session runtime、Claim、notification 和 Integration lease。

`codex_worker_provider.py` 是 `host_adapter.py` 背后的私有延迟加载实现，不是第五个公共边界。状态机决定“应该创建 Worker”；Host Adapter 决定“当前宿主怎么做”。宿主能力不能扩大 Discussion 权限。

## 6. Worker 启动的真实行为

### Codex

Codex App、CLI 和 IDE 能显示可检查的 Agent thread；CLI 可用 `/agent` 切换。WishGraph 安装项目级 `.codex/agents/wishgraph-worker.toml`。

```text
codex-worker prepare
-> Host Adapter 返回准确 Task、scope、validation、report path 和 Agent payload
-> 当前 Codex 宿主创建原生 Agent thread
-> 宿主返回真实 thread ID
-> codex-worker register 持久化 ID 和可检查/可控制证明
-> Worker preflight 并取得 Claim
```

Hook 不创建 Agent。`prepare` 成功不等于 Worker 已创建；真实 thread ID 注册前不得进入 `waiting_for_worker`。创建或注册失败时输出精简的跨宿主启动交接。

### Claude Code CLI

| 能力 | 当前行为 |
| --- | --- |
| `background_session` | 运行等价于 `claude --bg --agent wishgraph-worker --worktree <unique> --settings <ephemeral-json> "执行 <task-id> 任务"` 的命令 |
| `forked_subagent` | 只用于短时、低风险 Helper 检查 |
| `manual_command_only` | 输出项目目录、Codex/Claude 启动命令、配置和 Task 口令 |

进入 `background_session` 需要：`--bg`、`agents --json`、`--worktree`、`--settings`、受管 Agent、隔离 worktree 可见的 `.wishgraph`，以及与当前 `HEAD` 一致的已授权 Task。Worktree 设置只对本次启动生效，不改写用户或项目设置；全局 Adapter 与 Agent 可以服务多个已启用项目，但每个项目仍须存在有效 `.wishgraph/config.json`。

启动后保存稳定完整 session ID，并可使用：

```text
claude agents --json --all --cwd <project>
claude agents --cwd <project>
claude --resume <full-session-id>
```

第一条用于结构化刷新，第二条打开原生交互视图进行查看与控制，第三条用于适合恢复时按完整 ID 继续会话。当前 CLI 不提供 `claude logs`、`claude attach` 或 `claude stop` 子命令，WishGraph 不得假装这些命令成功。已创建但 Worktree/runtime 验证失败的 session 进入明确人工处理状态，同时用户侧降级仍只显示一行执行命令。

`claude --bg` 返回不等于 Task 已 `running`。Worker 进入实际 worktree 后仍需取得绑定 Claim。`/tasks` 只查看当前 Claude session 关联的后台工作，不创建 WishGraph Task，也不授予权限。

### 未知或不支持的宿主

只输出一份有界的启动交接，让用户任选 Codex 或 Claude Code，在新的可检查执行会话中运行。Discussion 到此停止执行动作，不附带“我也可以直接修改”。

## 7. Claim、worktree 与并行

业务写入、依赖安装、实现构建／测试和 Worker commit 都需要有效 Claim，至少绑定：

```text
task_id / revision_id
attempt
worker/session/thread identity
branch
absolute worktree
allowed_scope
validation_plan
execution_ownership
lease status / heartbeat
```

一个 Worker thread 同一时刻只能绑定一个工作单元。复用前必须让旧工作进入终态或明确停止、释放旧 Claim、清空旧 scope/validation，再取得新 Claim。

并行写入必须使用独立 worktree。Claim 只协调共享同一本地 Git common directory 的进程和 worktree，不是跨机器分布式锁。

## 8. 轻量 Revision

明确、低风险、属于原 Task 的局部修改使用 `tasks/revisions/<task-id>-rN.md`，不创建完整 Task Spec。

```text
用户提出局部修正
-> 识别唯一 parent Task
-> 创建或合并一个轻量 Revision
-> 路由到空闲原 Worker，或创建新的可检查 Revision Worker
-> 局部验证和短 Run Report
-> 安全时自动集成
```

运行中的原 Task 可直接吸收同范围反馈，不创建 Revision 文件。公共 API、schema、持久化、迁移、依赖、权限、安全、隐私或新产品决定必须升级为正式 Follow-up Task。

当前 Codex 路径可以复用或创建 Revision thread。Claude Code 没有完整原生 Revision 回送控制路径时，只输出 `在任务 <task-id> 的执行窗口执行修订 <revision-id>`。

## 9. Worker 终态、提醒与 Integration

Worker 写结构化终态、Run Report 并释放 Claim 后，Claim release 写一条幂等 pending notification：

```text
Worker terminal evidence + released Claim
-> .git/wishgraph/notifications/inbox.json
-> 绑定 Discussion 下次 SessionStart 或下一条输入时消费
-> 切换宿主后，明确开始讨论或刷新可以接管
-> 标记已读
```

这是“下次激活时拉取”，不是实时推送。没有 daemon、轮询、跨终端 IPC 或自动弹窗。宿主被强制结束可能绕过 terminal Hook；下一次 Discussion 只能根据 stale Claim 或结构化宿主状态恢复。

```text
completed|blocked|incomplete
-> integration_pending
-> evaluate_integration
```

- 报告、验证、范围、冲突和风险门禁通过：Discussion 取得 Integration lease，自动进行 safe-when-silent Integration。
- 公共接口、数据、安全、产品决定或冲突：进入 `decision_required`，只问具体选择。
- 缺报告、验证失败、Claim 未释放或状态矛盾：进入 Worker repair / `blocked`，不集成。

宿主的 `completed` 状态或自然语言“做完了”都不是充分证据。Integration 必须重新读取准确 Task/Revision、预期 Run Report、Claim、branch 和 worktree。

合法权限链固定为：

```text
已验证的 Discussion(integration_pending)
-> reducer 计算唯一 transition
-> 根据持久证据签发一次性 Integration grant
-> lease 获取前重新核对并原子消费 grant
-> Discussion-local Integration
```

公开 `session set` 不能写角色或阶段，公开 `session apply` 只接受诊断元数据。Worker、Helper、neutral session、其他 Discussion、选择变化或重复使用的 grant 都会被拒绝；Worker 也不能修改已批准 Task 的 Integration route 来扩大权限。Claim 获取与 Integration lease 获取共享互斥门禁，避免实现与集成同时写入。

## 10. 门禁能力的真实边界

```text
write/build gate: required
read gate: host capability dependent
```

WishGraph 能拦截受支持的原生写入工具、可识别的 shell 写入／构建命令，以及名称暴露写意图的 MCP 工具。它不是操作系统沙箱：不透明脚本或 MCP 工具可能隐藏副作用；宿主没有覆盖所有读取工具时，也不能把“Worker 只读相关文件”宣传成机械硬门禁。

普通非 commit `PreToolUse` 只检查请求操作、session、Claim、branch/worktree 和固定配置，不遍历业务源码树。SessionStart 的 worktree 检查范围更广，因此有独立性能预算。

## 11. 验收不变量

1. 未启用项目不会因通用短语进入 WishGraph。
2. Discussion 中“执行吧”只有唯一 transition 时才路由准确 Worker。
3. Discussion 不修改业务代码，也不运行实现验证。
4. Codex/Claude 只有保存真实 thread/session ID 后才进入 `waiting_for_worker`。
5. Worker 没有 Claim 不能写业务代码或构建。
6. Helper 和 Hidden Agent 不能取得 Worker Claim。
7. 启动失败输出有界的跨宿主交接，Discussion 不接管实现。
8. Worker 不能通过公开 session 命令或“开始讨论”把自己提升为 Discussion。
9. Integration lease 必须消费 reducer 签发、精确绑定且尚未使用的 grant。
10. Task、Report、Claim、branch 或 worktree 在 grant 后变化时，lease 获取失败关闭。
8. 没有 Run Report 或 Claim 未释放时不能集成。
9. 安全结果不再询问“是否开始集成”。
10. Revision 不会让已集成或已 review 的 parent Task 生命周期回退。
11. 两个并行写入 Worker 必须使用独立 worktree。
12. Project Status 是当前快照，历史留在不可变 Run Report 和 Git。
13. 提醒在下次 Discussion 激活时消费，不承诺主动唤醒。

## 12. 核对当前安装

普通用户不需要记诊断命令。重新打开会话后仍无法“开始讨论”时，再说“检查 WishGraph 状态”。Doctor 只读固定路径，区分文件安装、最近宿主调用、runtime 升级、当前宿主 adapter 修复和需人工检查的本地修改。

Codex 触发未确认时检查 `/hooks`；Claude Code CLI 可额外运行 `claude doctor`。更新全局 Skill 不会自动改写已有项目的 `.wishgraph/hooks/`；项目 runtime 需要单独执行指纹校验的安全升级。
