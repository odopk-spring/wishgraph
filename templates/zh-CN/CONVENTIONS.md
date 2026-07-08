# CONVENTIONS

这个文件定义人类和 AI agent 如何在本仓库协作。

## 角色

### 讨论 / 规划 Agent

讨论 agent 把人类意图转成持久任务规格。

职责：

- 新讨论窗口启动时，从 `prompts/DISCUSSION_AI.md` 开始。
- 提问前先读项目文档。
- 在要求执行 agent 重构架构或实现功能前，先建立或更新 `PRD.md`。
- 新项目或模糊项目先做 intake：一次问一个关键决策，每次给推荐默认值，再写实现任务。
- 只问会实质改变范围的决策。
- 在 `.tasks/build/` 写自包含任务规格。
- 除非项目 owner 明确启用低风险直接编辑例外，否则不改业务代码。
- 当路线图、进度、状态或交接规则变化时，更新 `prompts/DISCUSSION_AI.md`。

### 执行 Agent

执行 agent 只实现已批准的任务规格。

职责：

- 从 `prompts/EXECUTION_AI.md` 和具体任务文件开始。
- 把任务文件当成唯一需求源。
- 保持 patch 最小、聚焦。
- 运行任务列出的验证命令。
- 更新 `CODEMAP.md`、任务状态、`reports/DEV_REPORT.md` 和 `prompts/DISCUSSION_AI.md` 的当前进度。
- 除非项目 owner 明确说不提交，否则一个完成任务对应一个原子 commit。

## 任务文件规则

- 路径：`.tasks/build/NNN-short-slug.md`。
- 使用稳定任务编号。同一功能线后续任务使用 `003b` 或 `014c` 这类后缀。
- 任务必须不依赖聊天历史即可执行。
- 用符号、模块、路由、API 或测试锚定，不依赖行号。
- 必须有 "Do Not Do" 防止范围漂移。

## 启动提示词文件

- `prompts/DISCUSSION_AI.md` 是可变的。它保存项目结构、大纲、当前进度、开放决策、交接规则和任务规格写法。每个执行任务完成后都要更新。
- `prompts/EXECUTION_AI.md` 是稳定的。它告诉执行 agent 如何启动、读哪些文件、如何验证。不要把具体任务要求塞进去；具体要求属于 `.tasks/build/*.md`。
- 用户应该能把任一提示词复制到任意 agent 界面，并在不依赖旧聊天上下文的情况下继续。
- 项目记忆使用用户选择的语言。若要求双语，面向用户的解释按中文在前、英文在后写。文件路径、命令、代码符号、路由、包名和环境变量不要翻译。
- 如果用户要求迁移讨论窗口或换窗口继续，先更新 `prompts/DISCUSSION_AI.md`，再输出完整内容供复制。

## 外置记忆更新规则

任何 agent 窗口只要学到会改变项目事实的信息，都必须更新外置记忆。

- 产品目标、范围、路线图、用户可见行为、已接受取舍或当前进度变化时，更新 `PRD.md`。
- 依赖、模块所有权、服务边界、数据流或框架选择变化时，更新 `ARCHITECTURE.md`。
- 功能状态、文件位置、public contracts、runtime probes 或验证面变化时，更新 `CODEMAP.md`。
- 每个执行任务完成后更新 `prompts/DISCUSSION_AI.md`，让新规划窗口能接续。
- 执行后更新 `.tasks/build/*.md` 和 `reports/DEV_REPORT.md`。
- 如果 agent 无法更新必要文件，必须报告应添加的准确文本。

## 验证

每个执行任务必须说明：

- 构建命令。
- 相关测试。
- 必要的手动检查。
- 必须更新的文档或地图。
- 无法运行的检查及原因。

## Git

- 除非项目 owner 明确说不提交，一个完成执行任务应该产生一个原子 commit。
- 不要 stage 无关用户改动。
- 除非项目 owner 明确要求，不要改写历史。
- commit message 要让未来 reviewer 看懂。

## 空项目规则

- 不要从模糊想法直接开始写代码。
- 先把想法变成 `PRD.md`、`ARCHITECTURE.md`、`CODEMAP.md` 和一个有边界的首个任务。
- 一次问一个问题，每个问题都带推荐默认值。
- 首个任务批准后，告诉用户用 `prompts/EXECUTION_AI.md` 和任务文件开启独立执行窗口。

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
