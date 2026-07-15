# WishGraph 外置记忆 Hooks

WishGraph hooks 的目标，是机械检查并行 Worker 收尾和单写者集成，同时不要求脚本理解产品语义。

## 为什么使用三个事件

```text
SessionStart -> 执行中立安全检查，不替窗口选择角色
PreToolUse   -> 阻止外置记忆未同步的 git commit
Stop         -> Agent 试图提前结束时让它继续完成收尾
```

Claude Code 还支持 `TaskCompleted`，所以 Claude 适配器会在那里运行同一个检查器；可移植核心不依赖这个宿主专有事件。

## 安装到目标项目

运行时依赖 Git 和 Python 3.9 或更高版本，不需要第三方 Python 包。

### 最简方式

已经安装 Skill 的用户只需要在项目里告诉 Agent：

```text
使用 $wishgraph 为这个项目开启自动记忆同步，先使用安全模式。
```

Agent 会识别当前宿主并安装 `warn` 模式 hooks，不需要用户理解参数。

也可以直接用自然语言选择：

```text
只安装 Skill，不开启 Hooks。
安全配置 WishGraph。（推荐，不阻止结束和提交）
严格配置 WishGraph。（会阻止未同步的结束和提交）
```

如果用户没有说清楚，Agent 只问这一个问题，不再要求选择系统、宿主、路径或 Hook 事件。

Agent 不应该只抛出菜单，而是先根据当前项目主动推荐。例如：

```text
我检测到你正在为一个首次配置的 Git 项目安装 WishGraph。推荐“安全配置”：提醒遗漏但不阻止结束或提交，WishGraph 本身约 0.3 MB，通常不到 1 分钟。

回复“按推荐来”即可继续；也可以说“只装 Skill”或“严格配置”。
```

用户选择后，Agent 按“选择 → 环境检查 → 安装配置 → 验证完成”持续执行。只有缺少系统依赖、需要同意 `git init` 或必须重启时才暂停；暂停时只给一个下一步，并告诉用户完成后回复什么继续。

首次安装 Codex Skill 时，也可以在目标项目根目录用一条命令同时安装 Skill 和 hooks：

```bash
curl -fsSL https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.sh | bash -s -- codex --setup-project
```

Claude Code 将 `codex` 换成 `claude-user`。默认 `warn` 不会阻止结束或提交；完成一次正确收尾后，可加 `--strict` 切换到 `enforce` 并安装 Git pre-commit 兜底。

Windows PowerShell 可以使用原生安装器：

```powershell
& ([scriptblock]::Create((irm 'https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.ps1'))) codex -SetupProject
```

安装器会在写入文件前检查 Git、Python 3.9+ 和 Git 仓库。WishGraph Skill 约占 0.2 MB，项目 Hooks 小于 0.1 MB；只有缺少依赖时才提示额外成本。Git 通常约 200-500 MB、2-10 分钟；Python 通常约 100-300 MB、2-10 分钟；macOS 通过 Apple Command Line Tools 安装 Git 时可能约 1-3 GB、5-30 分钟。具体结果取决于系统、镜像和已有依赖。

### 自定义方式

从本仓库运行：

```bash
python3 skills/wishgraph/scripts/install_project_hooks.py \
  --target /path/to/project \
  --host all \
  --mode warn
```

从 Codex 用户 skill 安装目录运行：

```bash
python3 ~/.codex/skills/wishgraph/scripts/install_project_hooks.py \
  --target /path/to/project \
  --host codex \
  --mode warn
```

从 Claude Code 用户 skill 安装目录运行：

```bash
python3 ~/.claude/skills/wishgraph/scripts/install_project_hooks.py \
  --target /path/to/project \
  --host claude \
  --mode warn
```

安装器会把公共运行时放进 `.wishgraph/`，并安全合并 Codex 或 Claude Code 的项目级 JSON 配置，不会替换无关的现有 hooks。

`memory_sync.py` 现在只是稳定入口，内部拆成四个明确边界：`workflow_state.py` 定义 Session Role、Task Lifecycle、Flow Phase、Expected Transition、事件和计划；`policy.py` 实现纯函数 `reduce(current_state, user_event, host_capability)`；`host_adapter.py` 把唯一下一动作映射为 Codex、Claude Code、CLI 与 Hook 行为；`git_state.py` 保存 Git 事实、session runtime、Worker Claim 和 Discussion-local Integration lease。项目语义真相仍保存在 Markdown 和 Git 中。

建议先用 `warn`。完成一次 Task-backed Worker 收尾和一次 Discussion-local Integration 后，再把 `.wishgraph/config.json` 改成 `enforce`。

Codex 用户还需要信任目标仓库，并通过 `/hooks` 审阅新 hook；未信任项目不会运行项目级 hooks。

## 并行收尾规则

每个 Worker 使用独立 branch 或 worktree，并新增一个不可变报告：

```text
reports/runs/<work-unit-id>.md
```

新任务规格包含 `wishgraph:task-state`，执行报告包含 `wishgraph:run-state`，项目状态快照包含 `wishgraph:integration-state`。Hooks 检查 `draft -> approved -> running -> completed|blocked|incomplete -> integrated -> reviewed`，包括显式 Worker 创建授权和集成策略。Draft 在批准前可以继续修改；批准后执行身份固定，只有阻塞／未完成重试必须换用新的执行报告路径。授权、重试和评审转换只有在周围任务正文不变时才可不创建 Worker 报告；`running` 不是有效收尾。旧标签文件继续兼容；已存在但无效的结构化块会明确报错。

Task Lifecycle 只是一个状态维度。Session Role（`neutral|discussion|worker`）、Flow Phase 和唯一结构化 `expected_transition` 分别保存在 Git common dir。`可以`、`执行吧` 之类简短回复只有在 transition 唯一时才可执行。

Worker 使用 `Integrate` 或 `N/A`，不直接修改共享项目记忆：

```markdown
| File | Result | Reason |
|---|---|---|
| `PRD.md` | N/A | 用户可见行为没有变化 |
| `CODEMAP.md` | Integrate | 新代码锚点需要写入项目地图 |
| `prompts/DISCUSSION_AI.md` | Integrate | 合并后向讨论 AI 呈现完成结果 |
```

Discussion-local Integration 阶段持有绑定 lease，使用 `--no-commit` 合并 Worker commit，读取全部新增单次执行报告，更新受影响共享记忆，把 `reports/PROJECT_STATUS.md` 重写为当前项目状态概览，再刷新 `prompts/DISCUSSION_AI.md` 的精简动态交接。项目状态概览只列本次吸收的报告，并使用 Updated 或 N/A。

默认长度限制用于保持快照可用：项目状态概览最多 160 行、12000 字符，讨论动态区最多 30 行，兼容模式下的 SessionStart 上下文最多 2000 字符。项目状态概览任一限制超出时，`warn` 会提醒压缩但不阻止，`enforce` 会阻止集成结束和提交。历史细节应移动到单次执行报告和 Git 历史；不能为了满足限制而删除仍未解决的风险、冲突或待决定事项。

旧配置中的 `paths.dev_report` 会迁移为 `paths.project_status`，并保留原有自定义路径。只有旧 `reports/DEV_REPORT.md` 时仍可读取，但会收到迁移提醒；新旧标准文件同时存在时，WishGraph 会报告事实来源冲突，严格模式在只保留一个权威 `reports/PROJECT_STATUS.md` 前阻止集成。

任务和执行报告元数据使用 `sequential`、`parallel_batch` 和 `high_risk` 区分工作，执行模式使用 `exclusive`、`parallel_independent` 和 `competitive`。每个 Worker terminal 事件都先进入 `integration_pending`。安全串行结果和机械检查证明独立的并行批次沿用已有 Worker 授权，自动进入 Discussion-local Integration；高风险、冲突、阻塞、竞争或无法机械判断的结果进入具体 `decision_required` 或 `blocked`。Hooks 只计算和检查已记录门禁，不授予权限，也不启动 Agent。

创建 Worker 始终需要人类明确命令；Codex 随后可以创建用户可见 Worker。Claude Code、宿主不支持或创建失败时只输出 `执行 <task-id> 任务` 并停止。隐藏 subagent 不等于 Worker 窗口。Integration 是自动触发、Discussion-local、safe-when-silent 的阶段，不创建用户可见窗口；Discussion 不活跃时持久化 `integration_pending`，等下次进入或刷新后继续。

新 session 默认中立。使用默认 `session_start_context_mode: safety_only` 时，Hook 只在发现安全或同步问题时输出上下文，不加载讨论提示词，也不激活窗口角色。用户说“开始讨论”后，当前可见窗口才读取讨论状态；持续运行窗口说“刷新项目状态”即可刷新。明确保留 `discussion_summary` 兼容模式的旧安装仍可收到旧式精简注入。

持续运行的讨论窗口中可以直接说：`刷新 WishGraph 项目状态并呈现最新集成结果。`

已有 legacy ad-hoc 报告继续可读，但新的业务代码工作必须在持有 Claim 的 Worker 中执行；旧项目的 `.tasks/build/*.md` 仍受支持。

## 直接运行检查

```bash
python3 .wishgraph/hooks/memory_sync.py check --scope worktree
python3 .wishgraph/hooks/memory_sync.py check --scope staged
python3 .wishgraph/hooks/memory_sync.py status
```

`status` 输出机器可读的待集成状态、集成类型、准备报告、等待报告、阻塞报告、是否需要用户确认和理由。它读取可见 Git refs 中的不可变报告，不写入共享队列文件。讨论入口和显式刷新会读取这个状态；SessionStart 仅在显式兼容模式下包含它。

它还输出 `auto_integration_eligible`，以及 `nothing_to_integrate`、`wait_for_worker`、`auto_integrate`、`await_user_confirmation`、`discuss_blocker`、`compare_candidates` 之一作为 `next_action`。这些是内部路由字段，普通用户只看到 Discussion 和显式 Worker 窗口。

宿主适配器可以通过 `flow-plan` 计算纯 reducer；标准输入为 `{"state": {...}, "event": {...}}`。把返回的 `host_action.state_patch` 作为 JSON 标准输入交给 `session apply SESSION_ID` 原子持久化；`session get` 和 `session set` 用于检查与初始角色设置。真实可见 Worker ID 和 runtime 写入成功之前，不得持久化 `waiting_for_worker`。

宿主可以只读选择真实可用的静默降级路径，而不是让 Hook 启动任何东西：

```bash
python3 .wishgraph/hooks/memory_sync.py integration-plan --host-capability background
python3 .wishgraph/hooks/memory_sync.py integration-plan --host-capability active_agent
python3 .wishgraph/hooks/memory_sync.py integration-plan --host-capability inactive
```

`background` 和 `active_agent` 都返回 `enter_discussion_local_integration`；`inactive` 返回 `persist_integration_pending_until_discussion_resume`。任何结果都不创建 Integration 窗口。该命令只读；Hooks 绝不调用 `subprocess.Popen`、合并分支或写入语义状态。

宿主适配器还可以调用只读任务路由：

```bash
python3 .wishgraph/hooks/memory_sync.py task route "执行012号任务"
python3 .wishgraph/hooks/memory_sync.py task resolve 012
python3 .wishgraph/hooks/memory_sync.py task family 012
```

它只精确匹配结构化 ID，报告重复声明，不会执行相近编号或文件名前缀匹配。Task ID 遵循 `^\d{3,}[a-z]*$`；重试保留编号并递增 attempt，新 Follow-up Goal 才分配下一个字母后缀。

正式执行使用存放在 `git rev-parse --git-common-dir` 下、不会进入业务提交的仓库级 Runtime Claim：

```bash
python3 .wishgraph/hooks/memory_sync.py claim acquire 012 --worker-id worker-012 --session-id worker-012 --host codex
python3 .wishgraph/hooks/memory_sync.py claim inspect 012
python3 .wishgraph/hooks/memory_sync.py claim heartbeat CLAIM_ID
python3 .wishgraph/hooks/memory_sync.py claim release CLAIM_ID
python3 .wishgraph/hooks/memory_sync.py claim revoke CLAIM_ID
```

获取 Claim 使用原子文件系统操作，默认同一 Task 只允许一个 active exclusive Claim，并记录 attempt、worker、branch、绝对 worktree、时间、lease 状态、执行模式和可选宿主线程引用。传入 `--session-id` 时同时持久化 Worker runtime；持久化失败会撤销新 Claim。heartbeat 与 release 校验 branch/worktree 绑定；显式 revoke 是接管控制路径。stale 检测保留旧记录。它能协调共享同一本地 Git common directory 的进程与 worktree，但不是只共享远程仓库的多机器分布式锁。

Discussion-local Integration 先持久化 `phase: integrating`，再获取绑定 session、integration ID、Task、报告、branch 与 worktree 的 lease：

```bash
python3 .wishgraph/hooks/memory_sync.py integration-lease acquire \
  --session-id discussion-1 \
  --integration-id integration-012 \
  --task-id 012 \
  --report reports/runs/012-attempt-1.md
```

业务文件写入和实现构建／测试必须匹配活跃 Worker Claim；合并、组合验证、共享状态写入和集成提交必须持有 Discussion-local Integration lease。这是强制的 `write/build gate`。完整读取拦截取决于宿主 Hook 能力，因此源码读取只能声明为 `host capability dependent`，不能包装成通用硬门禁。

宿主未传 `--authorized-by-user` 时，`claim revoke` 返回 `explicit_user_authorization_required`。停止或拒绝尚未集成的工作会保留 branch/report；重试保留 Task ID 并递增 attempt。已集成历史只能通过新的回滚或 Follow-up Task 替换。

竞争执行使用只读计划：

```bash
python3 .wishgraph/hooks/memory_sync.py competitive-plan 012 --candidates 2
```

它提出 `012a`、`012b`、共同的 `comparison_group: 012`、独立 Claim/worktree/report，并规定只选一个胜者。status 只把客观唯一胜者放入 `selected_reports`；平分或 `selection_requires_judgment` 路由到 `compare_candidates`。失败候选不合并，标记为 `rejected` 或 `superseded`。

Legacy `micro` Run Report 继续兼容读取，但绝不授权 Discussion 修改业务代码；继续执行 micro 时也必须放在单独持有 Claim 的 Worker 中，并保留验证、不可变报告、提交、回滚和 Integrate/N/A 证据。新工作应使用正式 Task。

严格使用 `enforce` 模式时，建议给安装器增加 `--git-hook`，从而覆盖 Agent 以外的提交和生命周期 hook 无法拦截的工具路径。安装器不会覆盖已有 Git pre-commit hook，而是提示如何手动串联。

## 边界

- Hooks 不生成 PRD、架构、CODEMAP 或交接语义。
- Hooks 不会自动 stage、commit 或 amend。
- Hooks 会忽略自己的运行时和宿主配置文件。
- Hooks 不决定是否并行，不启动 Worker，不创建 Integration 窗口，不合并代码，也不代替人类 Review。
- Worker 被阻塞或未完成时，只要创建唯一的 Blocked 或 Incomplete 执行报告并记录验证、影响建议，就可以正常停下。
- 为仓库适配规则期间使用 `warn`，不要用虚假的 Updated 记录绕过检查。
