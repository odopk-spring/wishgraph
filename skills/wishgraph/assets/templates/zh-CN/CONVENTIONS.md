# CONVENTIONS

这个文件定义人类和 AI agent 如何在本仓库协作。

## 角色

### 讨论 / 规划 Agent

讨论 agent 把人类意图转成持久任务规格。

职责：

- 新窗口默认中立。只有用户明确说“开始讨论”“开启讨论”或同义表达后，才加载 `prompts/DISCUSSION_AI.md` 并进入讨论角色。
- 提问前先读项目文档。
- 在要求执行 agent 重构架构或实现功能前，先建立或更新 `PRD.md`。
- 新项目或模糊项目先做 intake：一次问一个关键决策，每次给推荐默认值，再写实现任务。
- 只问会实质改变范围的决策。
- 在可见的 `tasks/build/` 目录写自包含任务规格；只有已使用 `.tasks/build/` 的旧项目才保留旧路径。
- 创建 Worker 前把工作判断为 discussion、sequential、parallel_batch 或 high_risk。讨论 Agent 推荐执行形态，项目 owner 最终确认。
- 推荐并行前检查任务依赖、相同文件或核心模块、独立验证和回滚、任务间污染，以及未确认的产品或架构决策。
- 除非项目 owner 明确批准低风险直接编辑例外，否则不改业务代码。
- 直接编辑例外可以省略 task 文件，但不能省略验证、唯一执行报告或正常 commit 边界。
- 向用户呈现已集成结果前，先读 `reports/PROJECT_STATUS.md`。
- 讨论期间和用户 Review 后维护 `prompts/DISCUSSION_AI.md` 的精简动态交接，不要复制完整项目状态概览。
- 展示已批准任务和工作类型后，询问是否创建执行窗口。只有人类明确命令才授权创建；随后由讨论 Agent 为每个已授权规格创建并配置用户可见 Worker，自动交接 `prompts/EXECUTION_AI.md` 和任务文件，并使用 `<task-id> · <short title> · WG Worker` 命名，让任务身份优先显示。平台不能创建可见任务时才降级为手动复制；不要求用户自己修改记忆或集成文件。

### 执行 Agent

执行 agent 只实现已批准的任务规格。

职责：

- 从 `prompts/EXECUTION_AI.md` 和具体任务文件开始。
- 把任务文件当成唯一正式需求源；明确批准直接编辑时，把有边界的用户指令作为需求源。
- 保持 patch 最小、聚焦。
- 运行任务列出的验证命令。
- 有任务文件时更新任务状态，并且只新增一个不可变的 `reports/runs/<work-unit-id>.md`。
- 在单次执行报告中对共享记忆填写 `Integrate` 或 `N/A`。不要修改 `PRD.md`、`ARCHITECTURE.md`、`CODEMAP.md`、`CONVENTIONS.md`、`reports/PROJECT_STATUS.md` 或提示词文件。
- 在执行报告的版本化 `wishgraph:run-state` JSON 块中填写机器生命周期事实；证据、风险和影响理由继续保存在 Markdown 中。
- 使用版本化 task-state 生命周期：`draft -> approved -> running -> completed|blocked|incomplete -> integrated -> reviewed`。讨论窗口记录显式 Worker 授权和人类评审，Worker 记录执行状态，Integration 记录 `integrated`。
- 除非项目 owner 明确说不提交，否则一个完成任务对应一个原子 commit。
- Worker 默认不得在后台自动启动。

### 集成 Agent

集成 Agent 是共享项目状态的唯一写入者。

它是事件触发的临时角色，不是常驻窗口。

职责：

- 使用 `--no-commit` merge 或等价的 no-commit cherry-pick，让新执行报告和代码同时留在集成 diff 中。
- 解决冲突前读取每个新增的 `reports/runs/*.md`。
- 把 `reports/PROJECT_STATUS.md` 重写为当前已集成快照，保留当前事实和未解决事项，不保存历次集成历史。
- 在其中的版本化 `wishgraph:integration-state` JSON 块记录本次集成 ID、状态、类型、授权和吸收的执行报告。
- `reports/PROJECT_STATUS.md` 只列本次集成吸收的单次执行报告；详细历史留在不可变执行报告和 Git 中。
- 项目状态概览完成后，再刷新 `prompts/DISCUSSION_AI.md` 的精简动态交接。
- 运行集成验证并创建集成 commit。
- 安全串行结果使用任务批准时继承的集成授权，不重复询问。
- 安全串行和机械检查证明独立的 `parallel_independent` 结果沿用已有 Worker 授权自动集成；高风险、冲突、阻塞、竞争或不明确结果返回 Discussion。
- 只有平台具备后台任务或独立线程能力且授权允许时，才使用临时后台 Agent；否则明确切换当前主 Agent，或提供一次性启动指令，不得虚构后台执行。
- 把集成状态和结果返回讨论 Agent 后结束临时角色。

## 任务文件规则

- 路径：`tasks/build/NNN-short-slug.md`。
- 结构化 Task ID 必须匹配 `^\d{3,}[a-z]*$`。根任务使用数字；新 Follow-up Goal 使用可无限延展的 Excel 式小写后缀（`012z` 后是 `012aa`）。文件名 slug 只用于阅读。
- 使用 `parent_task_id` 和 `dependencies` 表达关系，不能从后缀长度推断层级。
- 已分配编号不得复用；批准后 Task ID 和 Task Spec 文件名都不可修改。
- 重试保留 Task ID，递增 `attempt`，并使用新的不可变 `reports/runs/<task-id>-attempt-N.md`。
- 正式执行要原子获取存放在 Git common directory 下的 Worker Claim，并绑定 Task attempt、Worker、branch 和绝对 worktree；继续工作前检查绑定，长任务持续 heartbeat。
- `exclusive` 是默认执行模式。第二个 Worker 必须获得显式接管或竞争授权，并使用独立 worktree。Claim 只协调共享同一本地 Git common directory 的 worktree，不覆盖多机器远程并发。
- 任务必须不依赖聊天历史即可执行。
- 用符号、模块、路由、API 或测试锚定，不依赖行号。
- 必须有 "Do Not Do" 防止范围漂移。
- 记录 Work type、Batch ID、Integration authorization 和唯一 Run report 路径。

## 启动提示词文件

- `prompts/DISCUSSION_AI.md` 是精简的可变讨论状态。讨论 AI 在规划和用户 Review 后维护；集成 Agent 吸收 Worker 报告后刷新。
- `prompts/EXECUTION_AI.md` 是稳定的。它告诉执行 agent 如何启动、读哪些文件、如何验证。不要把具体任务要求塞进去；具体要求属于 `tasks/build/*.md`。
- 用户应该能把任一提示词复制到任意 agent 界面，并在不依赖旧聊天上下文的情况下继续。
- 项目记忆使用用户选择的语言。若要求双语，面向用户的解释按中文在前、英文在后写。文件路径、命令、代码符号、路由、包名和环境变量不要翻译。
- 如果用户要求迁移讨论窗口或换窗口继续，先更新 `prompts/DISCUSSION_AI.md`，再输出完整内容供复制。

## 外置记忆更新规则

Worker 在自己的不可变执行报告中提出共享记忆影响；集成 Agent 负责应用建议并更新共享项目事实。

- 产品目标、范围、路线图、用户可见行为、已接受取舍或当前进度变化时，更新 `PRD.md`。
- 依赖、模块所有权、服务边界、数据流或框架选择变化时，更新 `ARCHITECTURE.md`。
- 功能状态、文件位置、public contracts、runtime probes 或验证面变化时，更新 `CODEMAP.md`。
- 集成一个或多个执行单元后，更新 `prompts/DISCUSSION_AI.md` 动态状态，让新建或恢复的规划窗口收到结果。
- Worker 分支有 task 文件时更新 `tasks/build/*.md`。
- 每个正式或 ad-hoc Worker 执行都新增一个 `reports/runs/<work-unit-id>.md`，不得覆盖旧报告。
- 只有集成阶段重写 `reports/PROJECT_STATUS.md`；它是当前快照，不是追加式日志。
- 如果 agent 无法更新必要文件，必须报告应添加的准确文本。

## 记忆同步 Hooks

- 项目级 hooks 可以通过 `.wishgraph/config.json`、`.codex/hooks.json` 和 `.claude/settings.json` 强制执行收尾。
- Hooks 负责检查和阻止，不负责编造 PRD、架构、CODEMAP 或交接语义。
- 安装 hooks 后，结束或提交前运行 `python3 .wishgraph/hooks/memory_sync.py check --scope worktree`。
- Worker 单次执行报告使用 `Integrate` 或 `N/A`；项目状态概览使用 `Updated` 或 `N/A`。
- Ad-hoc 修改可以没有 task 文件，但必须有唯一执行报告 ID。
- 默认 SessionStart 只做安全检查，不自动注入讨论交接或激活角色；持续运行窗口通过“刷新项目状态”显式刷新。
- Hooks 可以输出待集成状态、集成类型、准备／等待／阻塞报告、是否需要确认和理由；不得决定是否并行、启动 Agent、合并代码、编写语义记忆或代替人类 Review。

## 验证

每个执行任务必须说明：

- 构建命令。
- 相关测试。
- 必要的手动检查。
- 必须更新的文档或地图。
- 无法运行的检查及原因。

## Git

- 除非项目 owner 明确说不提交，一个完成执行任务应该产生一个原子 commit。
- 并行 Worker 必须使用不同 branch 或 worktree，并使用唯一工作单元 ID。
- 讨论 Agent 推荐串行或并行，项目 owner 最终决定。
- 只有集成 Agent 更新共享记忆，不能让多个 Worker 竞争修改同一文件。
- 不要 stage 无关用户改动。
- 除非项目 owner 明确要求，不要改写历史。
- commit message 要让未来 reviewer 看懂。

## 空项目规则

- 不要从模糊想法直接开始写代码。
- 先把想法变成 `PRD.md`、`ARCHITECTURE.md`、`CODEMAP.md` 和一个有边界的首个任务。
- 一次问一个问题，每个问题都带推荐默认值。
- 首个任务批准后询问是否创建执行窗口。用户明确授权后，由讨论 Agent 创建用户可见 Worker 并交接 `prompts/EXECUTION_AI.md` 和任务文件；不得静默创建，也不得用隐藏 subagent 代替。

## 调试纪律

回归问题按下面顺序追：

```text
Error -> State -> Code -> Spec
```

不要凭记忆猜文件。用 `CODEMAP.md`、日志、测试和任务历史找到最早被污染的假设或状态转换。

## 直接编辑例外

讨论 agent 只有在以下条件全部满足时才能直接编辑：

- 改动很小。
- 风险很低。
- 项目 owner 明确接受直接编辑。
- 改动不影响 public interfaces、persistent schema、security behavior、billing、data deletion 或 architecture boundaries。
- Agent 在结束前执行正常验证和外置记忆收尾。
