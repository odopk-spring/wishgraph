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

## 规划 Agent

- 澄清意图。
- 实现前更新 PRD 和架构。
- 编写自包含任务规格。
- 把工作判断为 discussion、sequential、parallel_batch 或 high_risk，解释串行或并行建议，由用户确认。
- 询问是否创建已批准的执行窗口。只有人类明确命令后，才使用宿主的用户可见任务或线程能力，为每个已授权规格创建 Worker，自动交接执行提示词和任务文件，并命名为 `<task-id> · <short title> · WG Worker`。不得静默创建 Worker 或使用隐藏 subagent；宿主不能创建可见任务时才降级为手动复制。
- 创建前，在每个已授权任务的 task-state 中记录 `draft -> approved` 和 `worker_creation_authorized: true`。
- 除非用户明确批准低风险直接编辑，否则不改业务代码。
- 极小直接修改可以没有 task 文件，但仍必须验证、创建唯一执行报告，并遵守正常 commit 边界。
- 用户要求迁移讨论时，更新 `prompts/DISCUSSION_AI.md` 并输出完整提示词供复制。

## 执行 Agent

- 读取 `prompts/EXECUTION_AI.md` 和指定任务文件。
- 只实现已批准任务。
- 保持 patch 最小、可回滚。
- 运行任务列出的验证。
- 核对授权，把 task-state 经 `running` 推进到 `completed|blocked|incomplete`，并新增一个不可变的 `reports/runs/<work-unit-id>.md`。
- 填写 Integrate 或 N/A 建议，不直接修改共享项目记忆。
- 存在 `.wishgraph/hooks/memory_sync.py` 时，完成前运行 worktree 检查。
- 除非用户明确说不提交，否则创建一个原子 commit。

## 集成 Agent

- 从独立 branch 或 worktree 使用 `--no-commit` 合并 Worker。
- 读取全部新增执行报告并更新受影响共享项目记忆。
- 把 `reports/PROJECT_STATUS.md` 重写为当前快照，再刷新 `prompts/DISCUSSION_AI.md` 的精简动态交接。
- 把已吸收的结构化任务改为 `integrated`；只有用户接受结果后，讨论窗口才改为 `reviewed`。
- 新建或恢复的讨论 session 可以从 SessionStart 收到精简集成结果；持续运行窗口需要显式刷新。
- 集成是临时角色。安全串行任务批准包含正常集成授权；parallel_batch 和 high_risk 必须取得用户明确集成确认。
- 只有平台支持时才使用已授权后台任务；否则明确切换主 Agent 或给出一条启动指令，不得虚构后台执行。
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
