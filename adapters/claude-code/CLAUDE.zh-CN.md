# Claude Code 的 WishGraph 项目指令

使用 WishGraph 作为 AI 协作开发的项目治理层。

## 启动模式

- 全局 `/wishgraph` Skill 只表示可用，不会自动在每个项目启用。没有已启用的 `.wishgraph/config.json` 时，不要把“开始讨论”或“执行 012 任务”这类通用短语解释成 WishGraph 命令。
- 只有明确点名 WishGraph 的请求才能启用项目。安全配置完成后保持 neutral，请用户重新打开 Claude Code 会话，之后再通过“开始讨论”进入 Discussion。
- 如果项目没有可用的 `PRD.md`，不要先实现代码。
- 默认使用用户语言。如果用户要求双语，关键提示、摘要和任务解释按中文在前、英文在后写。
- 不要翻译文件路径、命令、代码标识符、符号、路由、包名或环境变量。
- 用所选语言提问：
  - 中文：`先不用写完整 PRD。请用几句话告诉我：1. 你想做一个什么项目？2. 最先服务谁？3. 他们第一次打开时最应该完成什么动作？4. 你会用什么结果判断 v0 做对了？如果还不确定，可以只回答第 1 点，我会继续一问一问补齐。`
  - English: `You do not need a full PRD yet. In a few sentences, tell me: 1. What are you trying to build? 2. Who should it serve first? 3. What should they be able to do on the first successful use? 4. What result would make you say v0 is working? If you are not sure, answer only item 1 and I will fill the rest one decision at a time.`
- 一次 grill 一个决策，每个问题都带推荐默认值。
- 先写项目框架，再进入执行工作。

## 按角色读取

- **进入 Discussion：**先读 `reports/PROJECT_STATUS.md` 和紧凑 active status。只有当前问题需要时，才打开 `PRD.md`、`ARCHITECTURE.md`、`CODEMAP.md`、`CONVENTIONS.md` 或某一个 Task。
- **Worker：**只读准确分配的 Task 或 Revision、必要的 Project Status 小节，以及其范围明确要求的 Reference 和源码。不要扫描无关 Task、历史报告或完整源码树。
- **Integration：**只读被选中的 Run Report、对应 Task/Revision，以及报告指出需要更新的共享记忆文件。
- 正式 Task 使用 `tasks/*.md`；不猜测隐藏或其他 Task 目录。

## 协作规则

- Discussion session 写 PRD、架构说明、代码地图、提示词和任务规格，不写业务代码，也不运行实现构建或测试。
- Discussion session 把工作判断为 discussion、sequential、parallel_batch 或 high_risk，推荐执行形态并由用户确认。
- 执行 session 只实现已批准任务规格。
- 任务规格必须自包含；不要依赖聊天历史。
- Worker session 使用独立 branch 或 worktree，创建一个不可变的 `reports/runs/<work-unit-id>-attempt-N.md`，填写 Integrate 或 N/A 建议，不修改共享记忆。
- Discussion-local Integration 持有绑定 lease，使用 `--no-commit` 合并，把 `reports/PROJECT_STATUS.md` 重写为当前快照，并在同一个集成提交中更新受影响共享记忆。
- 创建 Worker 必须有人类明确命令。Discussion 中优先在独立 Worktree 使用受管后台 Worker；普通 neutral 窗口则在取得 Claim 后直接绑定当前可检查会话，不再创建第二个 Worker。Host Adapter 会临时增加 `--worktree` 和 `--settings`，不改写用户设置。原生启动不可用时，输出项目目录、Codex/Claude 启动命令及最后的 `执行 <task-id> 任务`，Discussion 不得降级为实现者。
- 宿主能检查和引导原 Worker 时，把轻量 Revision 路由回该 Worker；否则创建合法 Worker 路由或输出准确 Revision 交接。复用前必须释放旧 Claim，再获取 Revision 的新 scope/validation 绑定。
- 精确的执行、停止、重试、接管和明确 competitive 命令通过结构化 Task ID 与 Git common dir Claim 路由。只有存在唯一 `expected_transition` 时，简短上下文批准才有效。
- 把 Task 授权持久化为 `draft -> approved` 和 `worker_creation_authorized: true`，并原子创建规范 Run。Run 记录派发、运行、终态证据和集成；Task 只在 Integration 时改为 `integrated`，用户接受后改为 `reviewed`。
- Claim release 在 Git common runtime 中写入一条幂等 pending notification。绑定的 Discussion 下一次激活时消费并标记已读；切换宿主后，明确开始讨论或刷新可接管。安全串行和机械检查证明独立的 `parallel_independent` 结果自动进入 Discussion-local Integration；风险、冲突、阻塞、竞争或歧义进入具体的 `decision_required` 或 `blocked`。不得创建独立 Integration 窗口、daemon、轮询、IPC 服务或弹窗。
- Hooks 只输出状态并执行门禁，不决定是否并行，不启动 Agent，不合并代码，不编写语义记忆，也不代替 Review。
- 新窗口默认中立。默认 SessionStart 只做安全检查，不激活 Discussion；明确开始讨论或刷新时再加载当前状态。
- 每个完成的 Task-backed 执行单元优先对应一个原子 commit。
- 存在 `.wishgraph/hooks/memory_sync.py` 时，宣称完成前运行 worktree 检查。

## 继续工作

- 同一项目的新 Claude Code 窗口通过“开始讨论”继续；已经处于 Discussion 时使用“刷新项目状态”。从持久交接和当前状态读取，不输出完整提示词让用户手工复制。
- 切换宿主时保留项目文件，但不复用宿主自己的 thread/session ID。目标宿主必须已在 `required_hosts` 中；否则先明确启用并安装，再重新打开它的会话。
- PRD 和首个 Task 准备好后，设置唯一 `expected_transition` 并询问 Worker 授权；授权后优先使用受管后台 Worker，不可用时输出可复制的跨宿主交接。

## 调试

Bug 按下面链路追：

```text
Error -> State -> Code -> Spec
```

不要先猜熟悉文件。找到最早被污染的假设或状态转换。
