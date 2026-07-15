# WishGraph Agent Instructions

使用 WishGraph 通过外置记忆文件管理本项目，而不是依赖聊天历史。

## 第一次对话

如果没有可用的 `PRD.md`，不要开始写代码。

默认使用用户语言。如果用户要求双语，关键提示、摘要和任务解释按中文在前、英文在后写。不要翻译文件路径、命令、代码符号、路由、包名或环境变量。

用所选语言提问：

```text
先不用写完整 PRD。请用几句话告诉我：
1. 你想做一个什么项目？
2. 最先服务谁？
3. 他们第一次打开时最应该完成什么动作？
4. 你会用什么结果判断 v0 做对了？
如果还不确定，可以只回答第 1 点，我会继续一问一问补齐。
```

```text
You do not need a full PRD yet. In a few sentences, tell me:
1. What are you trying to build?
2. Who should it serve first?
3. What should they be able to do on the first successful use?
4. What result would make you say v0 is working?
If you are not sure, answer only item 1 and I will fill the rest one decision at a time.
```

如果要求双语，两个提示一起问。

随后一次问一个决策。每个问题都必须带推荐默认值。持续提问直到可以写出具体 PRD 和有边界的首个任务。

## 必需项目记忆

创建或更新：

- `PRD.md`：产品目标、用户、范围、非目标、路线图、当前决策。
- `ARCHITECTURE.md`：依赖边界、数据流、所有权、风险说明。
- `CODEMAP.md`：功能到文件地图、合约、验证面、调试入口。
- `CONVENTIONS.md`：协作规则、验证顺序、git 规则、记忆更新规则。
- `prompts/DISCUSSION_AI.md`：当前规划提示词和交接状态。
- `prompts/EXECUTION_AI.md`：稳定执行提示词。
- `prompts/INTEGRATION_AI.md`：稳定集成提示词和共享状态单写者规则。
- `tasks/build/*.md`：可见的自包含执行任务规格；旧项目已经使用 `.tasks/build/*.md` 时保持兼容。
- `reports/RUN_REPORT.md`：Worker 报告模板。
- `reports/runs/*.md`：不可变 Worker 执行证据。
- `reports/PROJECT_STATUS.md`：当前已集成的项目状态概览和下一步建议。

## Discussion 角色

- 澄清意图。
- 实现前更新 PRD 和架构。
- 编写自包含任务规格。
- 把工作判断为 discussion、sequential、parallel_batch 或 high_risk，解释串行或并行建议，由用户确认。
- 请求用户明确授权启动已经就绪的指定 Worker。只有收到该命令后，才使用宿主的用户可见任务或线程能力，为每个已授权 Task Spec 创建一个 Worker，并命名为 `<task-id> · <short title> · WG Worker`。不得静默创建 Worker 或使用隐藏 subagent；创建不受支持或失败时，只输出 `执行 <task-id> 任务` 并停止。
- “执行012号任务”、停止、重试、接管和明确竞争比较都通过精确结构化 Task ID 与仓库级 Claim 路由。只有存在唯一 `expected_transition` 时，简短上下文批准才有效。
- 创建前，在每个已授权任务的 task-state 中记录 `draft -> approved` 和 `worker_creation_authorized: true`。
- 不改业务代码，也不运行实现构建或测试。所有实现都必须是持有绑定 Claim 的 Task-backed Worker 工作。
- 用户要求迁移讨论时，更新 `prompts/DISCUSSION_AI.md` 并输出完整提示词供复制。

## Worker 角色

- 读取 `prompts/EXECUTION_AI.md` 和指定任务文件。
- 只实现已批准任务。
- 保持 patch 最小、可回滚。
- 运行任务列出的验证。
- 核对授权，把 task-state 经 `running` 推进到 `completed|blocked|incomplete`，并新增一个不可变的 `reports/runs/<work-unit-id>.md`。
- 填写 Integrate 或 N/A 建议，不直接修改共享项目记忆。
- 存在 `.wishgraph/hooks/memory_sync.py` 时，完成前运行 worktree 检查。
- 除非用户明确说不提交，否则创建一个原子 commit。

## Discussion-local Integration 阶段

- 从独立 branch 或 worktree 使用 `--no-commit` 合并 Worker。
- 读取全部新增执行报告并更新受影响共享项目记忆。
- 把 `reports/PROJECT_STATUS.md` 重写为当前快照，再刷新 `prompts/DISCUSSION_AI.md` 的精简动态交接。
- 把已吸收的结构化任务改为 `integrated`；只有用户接受结果后，讨论窗口才改为 `reviewed`。
- 新窗口默认中立。默认 SessionStart 只做安全检查；用户明确说“开始讨论”后才加载讨论状态，持续运行窗口使用显式刷新。
- 每个 Worker terminal 事件都进入 `integration_pending`。安全串行和机械检查证明独立的 `parallel_independent` 结果由持有绑定 Integration lease 的 Discussion 自动集成；风险、冲突、阻塞、竞争或歧义只形成具体决策或阻塞状态。
- 不得创建独立 Integration 窗口。Discussion 不活跃时，持久化 `integration_pending`，等它恢复后继续。
- Hooks 只提供准备、等待和阻塞报告，不决定是否并行，不启动 Agent，不合并代码，不编写语义记忆，也不代替人类 Review。

## 好的任务规格

每个任务文件必须包含：

- intent
- current state
- anchored files, symbols, APIs, commands, routes, or tests
- implementation notes
- "Do Not Do" boundaries
- validation commands and manual checks
- external memory updates
- rollback boundary
- execution report requirements

除非代码本身就是产品规则，不要包含长聊天记录或完整实现代码。

## 调试

Bug 按下面链路追：

```text
Error -> State -> Code -> Spec
```

先找到最早被污染的假设、状态转换、缓存、持久化字段或规格歧义，再 patch。
