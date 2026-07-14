# WishGraph 流程控制状态机规格

- 状态：Frozen / Implemented（2026-07-14）
- 范围：Discussion、Worker、Integration、Review 的流程控制层
- 目标：以已冻结语义和状态转换统一 Hook、运行时、模板与宿主适配器

## 1. 设计原则

WishGraph 的流程控制必须由机器可读状态和纯转换函数决定。提示词负责解释 `FlowPlan`，不能创造、跳过或覆盖状态转换。

本规格采用四个原则：

1. 窗口、角色、阶段和宿主动作分离。
2. Discussion 永远不能因为宿主缺少多 Agent 能力而接管 Worker 工作。
3. Integration 是 Discussion-local 临时阶段，不是独立窗口或永久角色。
4. 用户的简短肯定回复只在存在唯一 `expected_transition` 时才有确定含义。

## 2. 规范术语

| 术语 | 定义 |
| --- | --- |
| Window / 窗口 | Codex、Claude Code 或其他宿主提供的用户界面与会话容器。 |
| Role / 角色 | 当前窗口被允许承担的职责。角色决定可执行的操作边界。 |
| Phase / 阶段 | 当前流程正在处理的临时步骤。阶段可以变化，但不必改变窗口角色。 |
| Host action / 宿主动作 | 宿主为落实状态机动作而实际执行的 UI、task、thread 或文本输出操作。 |
| Discussion | 用户可见的长期窗口角色，负责规划、授权路由、Discussion-local Integration 和结果呈现。 |
| Worker | 必须在独立执行窗口运行的角色，负责实现、任务验证、Run Report 和原子提交。 |
| Integration | Discussion 内部的临时 phase，负责合并、组合验证、共享状态更新和集成提交。不是独立窗口角色。 |
| Review | Discussion 中向用户呈现结果并等待接受或后续意见的状态。不是第四个 Agent。 |

原“静默 Integration”统一改称：

> 自动触发、Discussion-local、safe-when-silent Integration

它同时表示：Worker 完成后自动触发；在 Discussion 窗口内部执行；只有所有门禁安全时才不询问用户。

## 3. 四个正交状态维度

### 3.1 Session Role

```text
neutral
discussion
worker
```

- 新窗口默认 `neutral`。
- `neutral` 收到“开始讨论”后进入 `discussion`。
- `neutral` 收到精确的 `执行 <task-id> 任务`，并通过执行 preflight 后进入 `worker`。
- 已是 `discussion` 的窗口收到执行授权时，只路由独立 Worker，不把自身改成 `worker`。
- Integration 不出现在 Session Role 中。

### 3.2 Task Lifecycle

```text
draft
approved
running
completed
blocked
incomplete
integrated
reviewed
```

标准路径：

```text
draft -> approved -> running -> completed -> integrated -> reviewed
                         |-> blocked
                         |-> incomplete
```

约束：

- `approved` 表示 Task Spec 已冻结且 Worker 启动已获授权。
- `running` 必须有有效 Worker Claim。
- `completed` 必须有终态 Run Report 和规定验证证据。
- `integrated` 必须有有效 Integration lease、集成提交和共享状态收尾。
- `reviewed` 只表示 Discussion 已向用户呈现，且用户接受结果。
- 缺少报告、验证失败或执行未闭环的任务不能保持 `completed`；应归一化为 `blocked` 或 `incomplete`。

### 3.3 Flow Phase

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

| Flow Phase | 含义 | Discussion 可做什么 |
| --- | --- | --- |
| `planning` | 澄清需求、写规格、判断执行形态 | 读取项目事实；写治理文档和 draft Task |
| `awaiting_worker_authorization` | Task 已就绪，等待用户授权 | 只解释 Task、回答问题、更新授权状态；停止新的源码探索 |
| `routing_worker` | 已授权，正在请求宿主启动 Worker | 调用 Host Adapter；不得实现 Task |
| `waiting_for_user_launch` | 宿主不能自动创建 Worker | 只展示一行执行命令并等待 |
| `waiting_for_worker` | Worker 已启动或由用户另开窗口执行 | 读取状态、观察、停止、重试、接管；不得重复执行 |
| `integration_pending` | Worker 已终态，必须进行集成评估 | 自动评估门禁；不询问“是否集成” |
| `integrating` | Discussion-local Integration 正在进行 | 持有 Integration lease 后合并、组合验证、更新共享状态和提交 |
| `decision_required` | 集成评估发现实质风险或多方案 | 只询问具体风险决策，不询问是否启动流程 |
| `presenting_result` | 集成完成，向用户展示结果 | 呈现结果、接受 review、生成 follow-up |

### 3.4 Expected Transition

`expected_transition` 是零个或一个带参数的结构化值，不是自由文本。

```text
none
approve_worker_launch(task_id)
launch_worker_manually(task_id)
wait_for_worker(task_id)
auto_integrate(task_id, report_id)
resolve_conflict(task_id, decision_id)
repair_worker_closeout(task_id)
accept_result(task_id, integration_id)
```

不变量：

- 同一 Session runtime 最多存在一个 `expected_transition`。
- 上下文批准只有在该值唯一、参数完整且仍然有效时才能消费。
- 多个 Task 同时等待授权时，不得把多个候选压成一个模糊 transition。
- `expected_transition` 由 reducer 产生；提示词不得自行改写。

## 4. 规范状态结构

建议控制层使用以下逻辑结构；具体序列化格式在实现阶段决定。

```text
OrchestrationState
  session
    session_id
    role
    host
    phase
    expected_transition
  task
    task_id
    lifecycle
    attempt
    worker_authorized
    run_report
  worker_runtime
    claim_id
    branch
    worktree
    host_window_or_thread_id
  integration_runtime
    lease_id
    base_branch
    worktree
    selected_reports
    integration_id
  pending_decision
    decision_id
    kind
    options
    recommended_option
```

事实归属：

| 状态 | 真相源 |
| --- | --- |
| Task Lifecycle、授权、attempt、Run Report | 版本化 Task/Run Report 文件 |
| Session Role、Flow Phase、Expected Transition | Git common directory 下的 session runtime |
| Worker Claim | Git common directory 下的 Claim runtime |
| Integration lease | Git common directory 下的 Integration runtime |
| 已集成结果 | Git、`reports/PROJECT_STATUS.md` 与 integration-state |

只有真实存在的宿主窗口或 thread ID 才能写入 runtime。手动等待状态不得虚构 ID。

## 5. 用户事件与解析优先级

### 5.1 明确命令优先

```text
执行 002 任务
停止 002 任务
重新执行 002 任务
接管 002 任务
查看 002 任务
观察 002 任务
```

- Task ID 必须精确匹配结构化 `task_id`。
- `002`、`002b`、`002ba` 是三个不同 ID。
- 不允许按文件名前缀、suffix 长度或最近任务猜测。
- 明确命令仍需通过授权、依赖、Claim、branch 和 worktree 门禁。

### 5.2 上下文批准其次

```text
可以
开始吧
执行吧
继续
按这个做
创建吧
```

解析规则：

1. 当前必须存在唯一 `expected_transition`。
2. transition 的目标 Task 或 decision 必须唯一且仍有效。
3. 回复只消费该 transition，不产生额外授权。
4. `approve_worker_launch(002)` 使“执行吧”表示启动 Worker 002。
5. `accept_result(002, integration-7)` 使“可以”表示接受已呈现结果。

### 5.3 无法唯一解析时询问

示例：

```text
当前有 002 和 003 两个任务等待启动，你希望执行哪一个？
```

任何解析路径都禁止产生 `discussion_window_implements_business_code`。

## 6. 纯状态转换核心

控制层核心是纯函数：

```text
FlowPlan = reduce(current_state, user_event, host_capability)
```

`reduce`：

- 不读写文件；
- 不调用宿主 API；
- 不运行 Git、构建或测试；
- 对同一输入产生相同输出；
- 必须输出唯一的下一动作或唯一的澄清问题；
- 必须同时返回允许的状态变更和拒绝原因。

建议 `FlowPlan` 至少包含：

```text
FlowPlan
  accepted
  next_action
  state_patch
  task_id
  required_claim
  required_integration_lease
  host_route
  user_message
  stop_after_action
  denial_reason
```

语义动作示例：

```text
ask_for_worker_authorization
launch_worker
show_manual_worker_command
wait_for_worker
evaluate_integration
enter_discussion_local_integration
ask_material_decision
present_result
deny_role_violation
```

Host Adapter 只能落实 `FlowPlan.next_action`，不能把拒绝改成允许，也不能把 `launch_worker` 改成 Discussion 直接执行。

## 7. Worker 路由

### 7.1 Discussion 中的启动

```text
planning
-> awaiting_worker_authorization
-> routing_worker
-> waiting_for_worker | waiting_for_user_launch
```

授权后：

- Codex 支持可见 task/thread：自动创建独立 Worker，成功后进入 `waiting_for_worker`。
- Codex 自动创建失败：进入 `waiting_for_user_launch`，只输出 `执行 <task-id> 任务`。
- Claude Code：进入 `waiting_for_user_launch`，只输出 `执行 <task-id> 任务`。
- 未知宿主：与 Claude Code 相同。

降级输出必须严格为一行，例如：

```text
执行 002 任务
```

输出后 Discussion 停止执行动作。禁止附带“也可以在当前窗口直接修改”、完整提示词包或虚构的运行状态。

### 7.2 Neutral 窗口中的启动

`neutral` 窗口收到精确命令 `执行 002 任务` 后：

1. 精确解析 Task；
2. 读取 `CONVENTIONS.md`、`prompts/EXECUTION_AI.md` 和 Task Spec；
3. 验证 `approved`、授权、依赖、attempt、branch/worktree 和 Claim；
4. 原子获取 Worker Claim；
5. Session Role 变为 `worker`；
6. Task Lifecycle 变为 `running`；
7. 执行、验证、写 Run Report、提交并进入终态。

## 8. 自动集成

Worker 进入任何终态后都触发集成评估：

```text
worker terminal
-> integration_pending
-> evaluate_integration
```

评估分流：

| 评估结果 | 状态转换 | 用户交互 |
| --- | --- | --- |
| 报告完整、验证通过、范围安全、无冲突、无新实质决策 | `integration_pending -> integrating` | 不询问 |
| 公共 API、schema、安全、迁移、冲突或新产品/架构决定 | `integration_pending -> decision_required` | 只询问具体决定 |
| 缺少报告、验证失败、状态矛盾 | Task 归一化为 `blocked` 或 `incomplete`，Phase 回到 `waiting_for_worker` | 呈现机械阻塞与修复动作 |

安全路径：

```text
integration_pending
-> acquire Integration lease
-> integrating
-> merge/cherry-pick without premature commit
-> combined validation
-> update shared state
-> integration commit
-> Task integrated
-> presenting_result
```

不再询问“是否开始集成”。只有出现实质选择时才提问，例如：

```text
002 修改了公共 API，有 A/B 两种兼容方案。我推荐 A，是否采用？
```

### 8.1 宿主差异

| 状态机动作 | Codex | Claude Code |
| --- | --- | --- |
| `launch_worker` | 自动创建可见 Worker task/thread | 输出一行执行命令 |
| Worker 自动创建失败 | 输出一行执行命令 | 不适用 |
| `auto_integrate`，Discussion 活跃 | 当前 Discussion 临时进入 Integration phase | 当前 Discussion 临时进入 Integration phase |
| `auto_integrate`，Discussion 不活跃 | 持久化 `integration_pending`，下次 Discussion resume 时自动进入 | 同左 |
| `decision_required` | Discussion 询问具体风险决定 | Discussion 询问具体风险决定 |

Integration 不创建用户可见窗口。

## 9. Claim、Lease 与机械门禁

### 9.1 Worker Claim

Worker 修改业务文件或运行实现验证前，必须持有有效 Claim，且 Claim 绑定：

```text
task_id
attempt
session_id / worker_id
branch
absolute worktree
lease status / heartbeat
```

Discussion 没有 Worker Claim，因此不能进行业务实现。

### 9.2 Integration Lease

Discussion 进入 `integrating` 前必须原子获取独占 Integration lease，绑定：

```text
session_id
integration_id
base branch
absolute worktree
selected Task IDs
selected Run Reports
lease status / heartbeat
```

Integration lease 只授权：

- 合并或 no-commit cherry-pick 已选择 Worker 结果；
- 在已选择 diff 范围内解决合并冲突；
- 运行组合验证；
- 更新共享项目状态；
- 创建集成提交。

它不授权实现新的业务需求。

### 9.3 操作门禁矩阵

| 操作 | neutral | discussion，无 lease | worker + Claim | discussion + Integration lease |
| --- | --- | --- | --- | --- |
| 写治理文档 / draft Task | 拒绝 | 允许 | 按 Task 范围 | 仅集成收尾所需 |
| 写业务文件 | 拒绝 | 拒绝 | 允许，必须绑定 Claim | 仅 merge/conflict-resolution 范围 |
| 安装依赖 | 拒绝 | 拒绝 | Task 明确授权时允许 | 默认拒绝；除非集成验证明确需要且无依赖变更 |
| 构建 / 实现测试 | 拒绝 | 拒绝 | 允许，必须绑定 Claim | 只允许组合验证 |
| 更新共享状态 | 拒绝 | 讨论规划范围内有限允许 | 拒绝 | 允许 |
| 集成提交 | 拒绝 | 拒绝 | 拒绝 | 允许 |

硬度声明：

```text
write/build gate: required
read gate: host capability dependent
```

进入 `awaiting_worker_authorization` 后，Discussion 按策略停止进一步源码探索。只有宿主对所有读取工具提供 Hook 时，这一点才能机械强制；否则必须诚实标记为策略约束，不能宣传为已实现硬门禁。

## 10. 四个现有边界的职责

### `workflow_state.py`

- 定义 `SessionRole`、`TaskLifecycle`、`FlowPhase`、`ExpectedTransition`、事件和 `OrchestrationState`。
- 只负责类型、解析、规范化和序列化。
- 不决定宿主动作，不执行 Git。

### `policy.py`

- 实现纯 `reduce` 和状态不变量。
- 输出唯一 `FlowPlan`。
- 实现授权解析、角色门禁、Task/Phase 转换和集成评估。
- 不写文件，不调用宿主 API。

### `host_adapter.py`

- 把 `FlowPlan` 映射为 Codex、Claude Code 或 unknown host 的真实动作。
- 将成功、失败、用户需手动启动等结果作为 Host Event 重新送回 reducer。
- 不改变流程授权，不提供 Discussion 执行降级。

### `git_state.py`

- 原子保存和检查 Worker Claim。
- 保存 session runtime。
- 原子保存和检查 Integration lease。
- 绑定 branch、worktree、session、heartbeat，并处理 stale/revoke。
- 不解释用户语言，不决定下一步。

## 11. 状态机规格验收

以下测试必须先于模板改写和运行时接线完成。

| ID | 场景 | 预期结果 | 禁止结果 |
| --- | --- | --- | --- |
| OSM-01 | Discussion 在唯一待启动 Task 上收到“执行吧” | `routing_worker`，动作 `launch_worker(002)` | Discussion 修改源码或运行测试 |
| OSM-02 | Neutral 新窗口收到“执行 002 任务” | 精确 preflight 后 `role=worker`，获取 Claim | 进入 Discussion 或模糊匹配 |
| OSM-03 | Claude Code 收到 Worker 启动授权 | `waiting_for_user_launch`，只输出 `执行 002 任务` | 完整提示词包或继续执行 |
| OSM-04 | Codex 自动创建 Worker 失败 | 同 OSM-03 | Discussion 接管实现 |
| OSM-05 | Worker 安全完成 | 自动 `integration_pending -> integrating` | 询问“是否集成” |
| OSM-06 | Integration 执行 | 当前 Discussion 临时 phase + Integration lease | 新建用户可见 Integration 窗口 |
| OSM-07 | 高风险 Worker 结果 | 先进入集成评估，再 `decision_required`，询问具体风险决定 | 询问是否启动集成 |
| OSM-08 | Discussion 写业务代码或运行构建 | Policy/Hook 拒绝，理由为缺少 Worker Claim 或 Integration lease | 只提示但仍执行 |
| OSM-09 | 002 和 003 同时等待授权，用户说“可以” | 询问准确 Task ID | 任意选择或同时启动 |
| OSM-10 | 存在 002、002b、002ba | 所有命令只精确匹配一个结构化 ID | prefix match |

建议补充的失败恢复测试：

| ID | 场景 | 预期结果 |
| --- | --- | --- |
| OSM-11 | Worker thread 创建成功但 runtime 写入失败 | 不宣称 `waiting_for_worker`；返回可恢复错误并根据真实 thread ID 重放状态写入 |
| OSM-12 | Integration lease 已被另一 Session 持有 | 保持 `integration_pending`，观察或等待，不并发集成 |
| OSM-13 | Worker 报告声称 completed 但验证失败 | 归一化为 `blocked/incomplete`，不集成 |
| OSM-14 | Refresh / Inspect | 只读，不消费 `expected_transition`，不启动 Worker 或 Integration |
| OSM-15 | Discussion 中用户要求“就在当前窗口直接修改” | 仍拒绝 Discussion 实现；创建或确认 Task 后路由独立 Worker |

## 12. 实施结果

本规格确认后已按以下顺序实施：

1. OSM-01 至 OSM-15 规格测试先行。
2. `workflow_state.py` 定义正交状态、事件、序列化与 `FlowPlan`。
3. `policy.py` 实现纯 reducer、授权解析、角色门禁和恢复转换。
4. `git_state.py` 增加 Git-common-dir session runtime 与独占 Integration lease。
5. `host_adapter.py` 接入 Codex / Claude Code 动作、CLI、Hook 门禁和 runtime patch 持久化。
6. 业务写入、构建／测试、Claim、lease 与伪造 runtime 校验均有机械测试；源码读取仍明确标记为宿主能力相关。
7. `CONVENTIONS.md`、prompts、Task/Report 模板、Skill、adapters、bootstrap 与中英文镜像已同步。
8. 完整测试套件通过，包含状态机、Claim/lease、Hook、安装迁移和模板镜像场景。

运行时配置版本为 9。`memory_sync.py` 仍是稳定入口，四个纯边界没有增加第五个大型模块。

## 13. 冻结检查表

进入实现前必须确认：

- [x] Integration 固定为 Discussion-local phase，不创建独立窗口。
- [x] Review 固定为 Discussion 状态，不是 Agent。
- [x] 四个状态维度的名称和语义已经冻结。
- [x] `expected_transition` 始终唯一且结构化。
- [x] 通用肯定回复只消费唯一 transition。
- [x] Discussion 永不成为 Worker 降级路径。
- [x] Worker Claim 是业务写入和实现验证的必要条件。
- [x] Integration lease 是合并、组合验证、共享状态更新和集成提交的必要条件。
- [x] 自动集成只询问实质风险决定，不询问是否启动流程。
- [x] write/build gate 与 host-dependent read gate 的能力声明真实可验证。
