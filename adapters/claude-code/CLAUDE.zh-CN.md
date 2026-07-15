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

- Discussion session 写 PRD、架构说明、代码地图、提示词和任务规格，不写业务代码，也不运行实现构建或测试。
- Discussion session 把工作判断为 discussion、sequential、parallel_batch 或 high_risk，推荐执行形态并由用户确认。
- 执行 session 只实现已批准任务规格。
- 任务规格必须自包含；不要依赖聊天历史。
- Worker session 使用独立 branch 或 worktree，创建一个不可变的 `reports/runs/<work-unit-id>.md`，填写 Integrate 或 N/A 建议，不修改共享记忆。
- Discussion-local Integration 持有绑定 lease，使用 `--no-commit` 合并，把 `reports/PROJECT_STATUS.md` 重写为当前快照，更新受影响共享记忆，再刷新 `prompts/DISCUSSION_AI.md` 的精简动态交接。
- 创建 Worker 必须有人类明确命令。Claude Code 不自动创建 Worker 窗口：授权后只输出 `执行 <task-id> 任务` 并停止。用户在另一个 neutral 窗口运行这一行；preflight 通过后，该窗口才进入 Worker 角色。
- 精确的执行、停止、重试、接管和明确 competitive 命令通过结构化 Task ID 与 Git common dir Claim 路由。只有存在唯一 `expected_transition` 时，简短上下文批准才有效。
- 创建前把命令写入 task-state：`draft -> approved` 并设置 `worker_creation_authorized: true`。Worker 记录执行状态，Integration 记录 `integrated`，用户接受后讨论窗口记录 `reviewed`。
- 每个 Worker terminal 事件都进入 `integration_pending`。安全串行和机械检查证明独立的 `parallel_independent` 结果自动进入 Discussion-local Integration；风险、冲突、阻塞、竞争或歧义进入具体的 `decision_required` 或 `blocked`。不得创建独立 Integration 窗口。
- Hooks 只输出状态并执行门禁，不决定是否并行，不启动 Agent，不合并代码，不编写语义记忆，也不代替 Review。
- 新窗口默认中立。默认 SessionStart 只做安全检查，不激活 Discussion；明确开始讨论或刷新时再加载当前状态。
- 每个完成的 Task-backed 执行单元优先对应一个原子 commit。
- 存在 `.wishgraph/hooks/memory_sync.py` 时，宣称完成前运行 worktree 检查。

## 交接

- 用户要求迁移讨论时，更新 `prompts/DISCUSSION_AI.md`，并打印完整内容供复制。
- PRD 和首个任务准备好后，设置唯一 `expected_transition` 并询问 Worker 授权；授权后只输出 `执行 <task-id> 任务`。

## 调试

Bug 按下面链路追：

```text
Error -> State -> Code -> Spec
```

不要先猜熟悉文件。找到最早被污染的假设或状态转换。
