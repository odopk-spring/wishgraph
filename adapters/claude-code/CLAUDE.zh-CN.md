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
6. 执行 session 阅读 `prompts/EXECUTION_AI.md` 和指定 `.tasks/build/*.md`
7. `reports/DEV_REPORT.md` 读取上一次交接

## 协作规则

- 规划 session 写 PRD、架构说明、代码地图、提示词和任务规格。
- 执行 session 只实现已批准任务规格。
- 任务规格必须自包含；不要依赖聊天历史。
- 项目事实变化时更新外置记忆。
- 每个完成的执行任务优先对应一个原子 commit。

## 交接

- 用户要求迁移讨论时，更新 `prompts/DISCUSSION_AI.md`，并打印完整内容供复制。
- PRD 和首个任务准备好后，告诉用户开启新的执行 session，提供 `prompts/EXECUTION_AI.md` 和已批准任务文件。

## 调试

Bug 按下面链路追：

```text
Error -> State -> Code -> Spec
```

不要先猜熟悉文件。找到最早被污染的假设或状态转换。
