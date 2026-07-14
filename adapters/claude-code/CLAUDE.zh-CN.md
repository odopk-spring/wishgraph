# Claude Code 的 WishGraph 项目指令

使用 WishGraph 作为 AI 协作开发的项目治理层。

## 启动模式

- 如果项目没有可用的 `PRD.md`，不要先实现代码。
- 默认使用用户语言。如果用户要求双语，关键提示、摘要和任务解释按中文在前、英文在后写。
- 不要翻译文件路径、命令、代码标识符、符号、路由、包名或环境变量。
- 用所选语言提问：
  - 中文：`先不用写完整 PRD。请用几句话告诉我：1. 你想做一个什么项目？2. 最先服务谁？3. 他们第一次打开时最应该完成什么动作？4. 你会用什么结果判断 v0 做对了？如果还不确定，可以只回答第 1 点，我会继续一问一问补齐。`
  - English: `You do not need a full PRD yet. In a few sentences, tell me: 1. What are you trying to build? 2. Who should it serve first? 3. What should they be able to do on the first successful use? 4. What result would make you say v0 is working? If you are not sure, answer only item 1 and I will fill the rest one decision at a time.`
- 一次 grill 一个决策，每个问题都带推荐默认值。
- 先写项目框架，再进入执行工作。

## 阅读顺序

做规划、任务编写或执行时，依次阅读：

1. `PRD.md`
2. `ARCHITECTURE.md`
3. `CODEMAP.md`
4. `CONVENTIONS.md`
5. 规划 session 阅读 `prompts/DISCUSSION_AI.md`
6. 执行 session 阅读 `prompts/EXECUTION_AI.md` 和指定 `tasks/build/*.md`；旧项目已有 `.tasks/build/*.md` 时保持兼容
7. `reports/PROJECT_STATUS.md` 读取当前已集成项目状态概览

## 协作规则

- 规划 session 写 PRD、架构说明、代码地图、提示词和任务规格。
- 规划 session 把工作判断为 discussion、sequential、parallel_batch 或 high_risk，推荐执行形态并由用户确认。
- 执行 session 只实现已批准任务规格。
- 任务规格必须自包含；不要依赖聊天历史。
- Worker session 使用独立 branch 或 worktree，创建一个不可变的 `reports/runs/<work-unit-id>.md`，填写 Integrate 或 N/A 建议，不修改共享记忆。
- 集成 session 使用 `--no-commit` 合并，把 `reports/PROJECT_STATUS.md` 重写为当前快照，更新受影响共享记忆，再刷新 `prompts/DISCUSSION_AI.md` 的精简动态交接。
- 创建 Worker 必须有人类明确命令。宿主支持创建用户可见任务或 session 时，由规划 Agent 为每个已授权规格创建可见 Worker，自动交接执行提示词和任务文件，并命名为 `<task-id> · <short title> · WG Worker`。不得静默创建或使用隐藏 subagent；宿主不支持时才降级为手动复制。
- 创建前把命令写入 task-state：`draft -> approved` 并设置 `worker_creation_authorized: true`。Worker 记录执行状态，Integration 记录 `integrated`，用户接受后讨论窗口记录 `reviewed`。
- 集成是临时角色。安全串行任务批准包含正常集成授权；parallel_batch 和 high_risk 必须取得用户明确确认。只有宿主支持时才使用后台执行，否则如实切换角色或提供一次性启动指令。
- Hooks 只输出状态并执行门禁，不决定是否并行，不启动 Agent，不合并代码，不编写语义记忆，也不代替 Review。
- SessionStart 可以向新建或恢复 session 注入最新集成结果；这不是向持续运行窗口实时推送。
- 每个完成的执行单元优先对应一个原子 commit。极小且已批准的 ad-hoc 修改可以没有 task 文件，但不能省略收尾。
- 存在 `.wishgraph/hooks/memory_sync.py` 时，宣称完成前运行 worktree 检查。

## 交接

- 用户要求迁移讨论时，更新 `prompts/DISCUSSION_AI.md`，并打印完整内容供复制。
- PRD 和首个任务准备好后，询问是否创建执行 session。用户明确授权后，在宿主支持时创建并配置用户可见 Worker；否则提供完整提示词和已批准任务文件作为手动降级方案。

## 调试

Bug 按下面链路追：

```text
Error -> State -> Code -> Spec
```

不要先猜熟悉文件。找到最早被污染的假设或状态转换。
