# PaperChat 风格脱敏工作流

本文用一个本地阅读 app 作为 WishGraph 的脱敏载体示例。它解释协作工作流，不暴露私有产品实现。不要把这里的文件名或功能标签当成专有源码。

## 这个例子展示什么

项目是一个 local-first reader app，包含多个会相互影响的部分：

- 导入纯文本或结构化内容。
- 把内容解析成用户可见的阅读单元。
- 用对话式或卡片式 reader 渲染这些单元。
- 记录阅读进度并恢复导航状态。
- 让 AI agent 在不丢失项目上下文的情况下安全演化功能。

这种项目很适合展示 WishGraph，因为 UI 行为、解析规则、持久化、导航和性能约束很容易漂移，如果决策只存在聊天历史里会很危险。

## 从零想法到 PRD

从讨论窗口开始：

```text
Use $wishgraph to start this project.
```

如果还没有 PRD，讨论 AI 应该先问：

```text
先不用写完整 PRD。请用几句话告诉我：
1. 你想做一个什么项目？
2. 最先服务谁？
3. 他们第一次打开时最应该完成什么动作？
4. 你会用什么结果判断 v0 做对了？
如果还不确定，可以只回答第 1 点，我会继续一问一问补齐。
```

然后一次 grill 一个决策：

1. 首批用户是谁？
2. 他们第一次导入什么内容？
3. 第一个重复阅读工作流是什么？
4. v0 明确不做什么？
5. 最小端到端切片是什么？
6. 哪个命令或手动检查证明这个切片可用？
7. 哪些决策在执行前需要人类明确批准？

输出不是代码，而是第一版项目框架：

```text
PRD.md
ARCHITECTURE.md
CODEMAP.md
CONVENTIONS.md
prompts/DISCUSSION_AI.md
prompts/EXECUTION_AI.md
tasks/build/001-bootstrap-project.md
reports/PROJECT_STATUS.md
```

## 外置记忆形态

### PRD.md

记录产品事实：

- 目标用户
- 核心阅读工作流
- 目标和非目标
- 第一个薄切片
- 已接受取舍
- 路线图
- 开放决策

### ARCHITECTURE.md

记录项目边界：

- 内容导入层
- 解析或转换层
- 阅读状态层
- UI 渲染层
- 持久化层
- 验证和性能约束

### CODEMAP.md

作为查找表：

| 区域 | 示例职责 | 为什么重要 |
|---|---|---|
| Import | 加载本地文本内容 | 防止 UI 任务误改导入规则 |
| Parsing | 把文本转换为阅读单元 | Bug 经常来自 parser 假设 |
| Reader UI | 渲染单元和交互 | UI polish 不能悄悄改写 state 语义 |
| Progress | 记录当前位置和最远位置 | 导航 bug 需要因果追踪 |
| Reports | 保存执行证据 | 未来 agent 需要验证历史 |

### prompts/DISCUSSION_AI.md

保存当前规划状态。换窗口继续前，讨论 AI 更新这里的精简交接；新窗口打开同一项目后输入“开始讨论”，无需复制完整提示词。

### prompts/EXECUTION_AI.md

保持稳定。它告诉 Worker 如何启动、读哪些文件、如何收尾。具体任务要求属于 `tasks/build/*.md`，不属于这个提示词。

## 前台讨论、显式 Worker、临时集成

```text
Human idea
-> Discussion AI grills and updates PRD
-> Discussion AI writes a self-contained task spec
-> Discussion AI classifies sequential / parallel_batch / high_risk
-> Human approves task boundary and explicitly authorizes the named Worker task(s)
-> Discussion AI creates and configures user-visible Worker task(s)
-> Worker reads EXECUTION_AI.md plus the Task file
-> Worker implements only that Task
-> Worker validates, writes one immutable Run Report, and commits
-> Discussion-local Integration applies approved results and shared-memory updates
-> Discussion AI presents the integrated result for human review
```

Discussion 控制方向并推荐串行或并行；人类明确授权后，当前 Codex 宿主可以创建可检查 Agent thread，Claude Code 在能力检查通过时优先使用受管后台 Worker。宿主不支持或创建失败时输出精简的跨宿主启动交接。不得静默创建或使用隐藏 subagent。每个 Worker terminal 事件都进入集成评估；安全结果在 Discussion-local 阶段集成，风险或歧义只询问具体决定。

## 示例首个实现任务

Bootstrap 后，第一个真实任务可能是：

```text
tasks/build/002-import-local-text.md
```

好的任务规格应该包含：

- 用户可见意图
- 当前仓库事实
- 锚定文件或计划文件
- 实现说明
- 明确非目标
- 验证命令
- 手动检查
- 执行后必须更新的文件
- 工作类型、批次 ID 和未来的 Integration route
- 回滚边界
- 报告格式

它不应该写“把 app 做好”或“实现 reader”。这些不是可执行边界。

## 因果调试示例

如果 reader 恢复到错误位置，不要先猜 UI 文件。

按下面链路追：

```text
Error: wrong restored position
-> State: stored progress value or cache entry
-> Code: writer/reader of that state
-> Spec: decision about current vs furthest position
```

修复应该是修复最早污染链路的最小 patch。

## 刻意省略什么

本文不包含：

- 私有产品代码
- 专有 UI 细节
- 私有任务历史
- app-specific business decisions
- 截图或用户数据

目的只是展示 WishGraph 如何为复杂项目组织 AI 协作，同时保持对其他项目可复用。
