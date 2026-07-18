# CONVENTIONS

这个文件定义人类和 AI agent 如何在本仓库协作。

## 角色

### Discussion Role

讨论 agent 把人类意图转成持久任务规格。

职责：

- 当前项目必须先被显式启用；首次启用后窗口仍保持中立。用户说“开始讨论”进入规划讨论；在 Discussion 输入精确执行命令会派发独立 Worker，在普通 neutral 窗口输入则直接绑定当前窗口为 Worker，不再创建第二个窗口。
- 提问前先读项目文档。
- 授权 Worker 重构架构或实现功能前，先建立或更新 `PRD.md`。
- 新项目或模糊项目先做 intake：一次问一个关键决策，每次给推荐默认值，再写实现任务。
- 只问会实质改变范围的决策。
- 在可见的 `tasks/build/` 目录写自包含任务规格；不猜测隐藏或其他 Task 目录。
- 创建 Worker 前把工作判断为 discussion、sequential、parallel_batch 或 high_risk。讨论 Agent 推荐执行形态，项目 owner 最终确认。
- 推荐并行前检查任务依赖、相同文件或核心模块、独立验证和回滚、任务间污染，以及未确认的产品或架构决策。
- Discussion 不得修改业务代码、安装依赖、运行构建或实现测试，也不得执行 Task 验证。这些操作必须由持有绑定 Claim 的独立 Worker 完成。
- 用户要求在当前窗口直接修改也不能覆盖角色边界。
- 向用户呈现已集成结果前，先读 `reports/PROJECT_STATUS.md`。
- 讨论期间和用户 Review 后维护 `prompts/DISCUSSION_AI.md` 的精简动态交接，不要复制完整项目状态概览。
- Task 就绪后进入 `awaiting_worker_authorization`，并设置唯一 `approve_worker_launch(<task-id>)` expected transition。模型与推理强度必须根据用户约束、Task 复杂度、风险和已知可用性逐次推荐，不能硬编码通用组合；有依据的建议写入 `worker_execution_profiles`，没有建议的宿主使用真实默认。询问前展示当前宿主的本次建议；短肯定回复在 transition 唯一时使用该建议，准确执行命令可以覆盖。随后进入 `routing_worker`：请求当前 Codex 宿主创建用户可见、可检查的原生 `wishgraph-worker` Agent thread；Claude Code 只有在能力检查通过时才优先创建受管后台 Worker；未知宿主或创建失败时进入 `waiting_for_user_launch`，使用 Host Adapter 生成的跨宿主可复制交接。

### Worker 角色

Worker 只实现已批准的 Task Spec。

职责：

- 从 `prompts/EXECUTION_AI.md` 和具体任务文件开始。
- 把 Task 文件当成唯一正式需求源。
- 保持 patch 最小、聚焦。
- 运行任务列出的验证命令。
- 有任务文件时更新任务状态，并且只新增一个不可变的 `reports/runs/<work-unit-id>.md`。
- 在单次执行报告中对共享记忆填写 `Integrate` 或 `N/A`。不要修改 `PRD.md`、`ARCHITECTURE.md`、`CODEMAP.md`、`CONVENTIONS.md`、`reports/PROJECT_STATUS.md` 或提示词文件。
- 在执行报告的版本化 `wishgraph:run-state` JSON 块中填写机器生命周期事实；证据、风险和影响理由继续保存在 Markdown 中。
- 持久 task-state 使用 `draft -> approved -> integrated -> reviewed`。Git common dir 中的规范 Run 记录派发、运行、终态证据与集成。
- 除非项目 owner 明确说不提交，否则一个完成任务对应一个原子 commit。
- Formal Worker 可以运行在独立窗口或宿主原生后台 Agent thread，但必须用户可见、可检查、可控制，并持有准确 Claim；Explorer、Reviewer、Plan 和隐藏子代理只能作为只读 Helper。

### Discussion-local Integration Phase

Integration 是当前 Discussion 窗口内部、事件触发的临时 phase，不是独立 Role 或用户可见窗口。它是共享项目状态的唯一写入阶段。

职责：

- 使用 `--no-commit` merge 或等价的 no-commit cherry-pick，让新执行报告和代码同时留在集成 diff 中。
- 解决冲突前读取每个新增的 `reports/runs/*.md`。
- 把 `reports/PROJECT_STATUS.md` 重写为当前已集成快照，保留当前事实和未解决事项，不保存历次集成历史。
- 在其中的版本化 `wishgraph:integration-state` JSON 块记录本次集成 ID、状态、类型、授权和吸收的执行报告。
- `reports/PROJECT_STATUS.md` 只列本次集成吸收的单次执行报告；详细历史留在不可变执行报告和 Git 中。
- 项目状态概览完成后，再刷新 `prompts/DISCUSSION_AI.md` 的精简动态交接。
- 运行集成验证并创建集成 commit。
- 安全串行结果沿用 Task 批准，由原 Discussion 自动集成，不重复询问；这不会把 Integration 权限交给 Worker。
- 安全串行和机械检查证明独立的 `parallel_independent` 结果沿用已有 Task 批准，由原 Discussion 自动集成；Worker 不获得 Integration 权限。高风险、冲突、阻塞、竞争或不明确结果返回 Discussion。
- 合并前必须获取绑定 Discussion session、base branch、worktree、所选 Task ID 和 Run Report 的独占 Integration lease。
- 每个 Worker 终态都进入 `integration_pending`。安全证据自动进入 `integrating`；重大风险进入 `decision_required`；证据缺失则变为 blocked 或 incomplete。
- 不询问是否开始集成；只有需要重大决定时才询问具体问题。
- 集成提交后释放 lease，并在同一 Discussion 窗口进入 `presenting_result`。

## 任务文件规则

- 路径：`tasks/build/NNN-short-slug.md`。
- 结构化 Task ID 必须匹配 `^\d{3,}[a-z]*$`。根任务使用数字；新 Follow-up Goal 使用可无限延展的 Excel 式小写后缀（`012z` 后是 `012aa`）。文件名 slug 只用于阅读。
- 使用 `parent_task_id` 和 `dependencies` 表达关系，不能从后缀长度推断层级。
- 已分配编号不得复用；批准后 Task ID 和 Task Spec 文件名都不可修改。
- 重试保留 Task ID，递增 `attempt`，并使用新的不可变 `reports/runs/<task-id>-attempt-N.md`。
- 正式执行要原子获取存放在 Git common directory 下的 Worker Claim，并绑定 Task attempt、Worker、branch 和绝对 worktree；继续工作前检查绑定，长任务持续 heartbeat。
- `exclusive` 是默认执行模式。第二个 Worker 必须获得显式接管或竞争授权，并使用独立 worktree。Claim 只协调共享同一本地 Git common directory 的 worktree，不覆盖多机器远程并发。
- 竞争候选使用子编号、同一 comparison group、独立 Claim/worktree/report，并且只集成一个胜者；失败证据保留并标记 `rejected` 或 `superseded`。
- 任务必须不依赖聊天历史即可执行。
- 用符号、模块、路由、API 或测试锚定，不依赖行号。
- 必须有 "Do Not Do" 防止范围漂移。
- 记录 Work type、Batch ID、Integration authorization 和唯一 Run report 路径。

## 启动提示词文件

- `prompts/DISCUSSION_AI.md` 是精简的可变讨论状态。Discussion 在规划和用户 Review 后维护；Discussion-local Integration 吸收 Worker 报告后刷新。
- `prompts/EXECUTION_AI.md` 保持稳定，用于说明 Worker 如何启动、读取哪些文件以及怎样验证。具体任务要求属于 `tasks/build/*.md`，不要写进这个固定提示词。
- 新的受支持 Agent 窗口应在输入“开始讨论”后从项目文件继续；用户不需要复制完整提示词或旧聊天记录。
- 项目记忆使用用户选择的语言。若要求双语，面向用户的解释按中文在前、英文在后写。文件路径、命令、代码符号、路由、包名和环境变量不要翻译。
- 换窗口继续前保持 `prompts/DISCUSSION_AI.md` 的精简状态为最新；新窗口输入“开始讨论”，已在 Discussion 中时输入“刷新项目状态”。

## Orchestration State

- Session Role：`neutral`、`discussion` 或 `worker`；Integration 不是 Role。
- 持久 Task Lifecycle：`draft`、`approved`、`integrated`、`reviewed`。规范 Run Phase：`dispatching`、`running`、`succeeded`、`failed`、`decision_required`、`integrating`、`integrated`。
- Flow Phase：`planning`、`awaiting_worker_authorization`、`routing_worker`、`waiting_for_user_launch`、`waiting_for_worker`、`integration_pending`、`integrating`、`decision_required`、`presenting_result`。
- `expected_transition` 为空或只有一个结构化 transition；缺失或歧义时，上下文肯定回复不得推进。
- `reduce(current_state, user_event, host_capability)` 产生唯一 `FlowPlan`，提示词和 Host Adapter 都不能覆盖。

## 外置记忆更新规则

Worker 在自己的不可变执行报告中提出共享记忆影响；持有 lease 的 Discussion-local Integration 阶段负责应用建议并更新共享项目事实。

- 产品目标、范围、路线图、用户可见行为、已接受取舍或当前进度变化时，更新 `PRD.md`。
- 依赖、模块所有权、服务边界、数据流或框架选择变化时，更新 `ARCHITECTURE.md`。
- 功能状态、文件位置、public contracts、runtime probes 或验证面变化时，更新 `CODEMAP.md`。
- 集成一个或多个执行单元后，更新 `prompts/DISCUSSION_AI.md` 动态状态，让新建或恢复的规划窗口收到结果。
- Worker 分支有 task 文件时更新 `tasks/build/*.md`。
- 每个 Worker 执行都新增一个 `reports/runs/<task-id>-attempt-N.md`，不得覆盖旧报告。
- 只有集成阶段重写 `reports/PROJECT_STATUS.md`；它是当前快照，不是追加式日志。
- 如果 agent 无法更新必要文件，必须报告应添加的准确文本。

## 记忆同步 Hooks

- Hooks 可以全局或项目级安装，但只有 `.wishgraph/config.json` 会明确启用当前项目；它们负责收尾与权限门禁，不覆盖无关宿主设置。
- Hooks 负责检查和阻止，不负责编造 PRD、架构、CODEMAP 或交接语义。
- 安装 hooks 后，结束或提交前运行 `python3 .wishgraph/hooks/memory_sync.py check --scope worktree`。
- Worker 单次执行报告使用 `Integrate` 或 `N/A`；项目状态概览使用 `Updated` 或 `N/A`。
- Session runtime、Worker Claim 和 Integration lease 保存在 Git common directory，不写入业务文件。
- 全局安装 Skill 不代表当前项目已经启用。只有 `.wishgraph/config.json` 的 `mode` 为 `warn` 或 `enforce` 才表示项目已显式加入；缺少配置或 `mode: off` 时，通用入口短语不触发 WishGraph。
- 已启用项目的新窗口默认中立。SessionStart 只做安全检查，不自动注入讨论交接或激活角色；首次启用不会在同一步进入 Discussion，持续运行窗口通过“刷新项目状态”显式刷新。
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
- 只有持有 Integration lease 的 Discussion-local Integration 阶段更新共享记忆，不能让多个 Worker 竞争修改同一文件。
- 不要 stage 无关用户改动。
- 除非项目 owner 明确要求，不要改写历史。
- commit message 要让未来 reviewer 看懂。

## 空项目规则

- 不要从模糊想法直接开始写代码。
- 先把想法变成 `PRD.md`、`ARCHITECTURE.md`、`CODEMAP.md` 和一个有边界的首个任务。
- 一次问一个问题，每个问题都带推荐默认值。
- 首个 Task 就绪后建立唯一 expected transition；授权后路由独立、用户可见且可检查的 Worker thread 或窗口，不得用 Discussion 实现或隐藏 subagent 代替。

## 调试纪律

回归问题按下面顺序追：

```text
Error -> State -> Code -> Spec
```

不要凭记忆猜文件。用 `CODEMAP.md`、日志、测试和任务历史找到最早被污染的假设或状态转换。

## Discussion 无直接实现路径

Discussion 永不执行 Worker 实现。业务文件写入和实现验证必须持有 Worker Claim；merge/conflict-resolution 写入、组合验证、共享状态更新和集成提交必须持有 Discussion-local Integration lease。写入/构建门禁必须机械执行；读取门禁取决于宿主能力，不得夸大。
