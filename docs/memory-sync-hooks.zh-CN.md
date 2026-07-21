# WishGraph 外置记忆 Hooks

WishGraph hooks 的目标，是机械检查并行 Worker 收尾和单写者集成，同时不要求脚本理解产品语义。

## 为什么使用这些事件

```text
SessionStart -> 执行中立安全检查，不替窗口选择角色
UserPromptSubmit -> 路由精确的进入、刷新和 Task 命令
PreToolUse   -> 门禁受支持的写入/构建和未同步 commit
Stop         -> Agent 试图提前结束时让它继续完成收尾
```

Claude Code 还支持 `TaskCompleted`，所以 Claude 适配器会在那里运行同一个检查器；可移植核心不依赖这个宿主专有事件。

## 安装到目标项目

运行时依赖 Git 和 Python 3.9 或更高版本，不需要第三方 Python 包。

### 最简方式

已经安装 Skill 的用户只需在项目里明确启用：

```text
在当前项目使用 WishGraph，按推荐安全配置。
```

推荐配置会选择 Codex 和 Claude Code，并安装 `warn` 模式 hooks；用户也可明确只选一个宿主。不需要学习安装参数。

也可以直接用自然语言选择：

```text
只安装 Skill，不开启 Hooks。
安全配置 WishGraph。（推荐；`warn` 下检查安静且不阻止任务分发）
严格配置 WishGraph。（会阻止未同步的结束和提交）
```

如果用户没有说清楚，Agent 只问这一个问题，不再要求选择系统、宿主、路径或 Hook 事件。

Agent 不应该只抛出菜单，而是先根据当前项目主动推荐。例如：

```text
我检测到你正在为一个首次配置的 Git 项目安装 WishGraph。推荐“安全配置”：`warn` 下所有 Hook 检查都安静且不阻止，任务仍可正常分发。通常不到 1 分钟。

回复“按推荐来”即可继续；也可以说“只装 Skill”或“严格配置”。
```

用户选择后，Agent 按“选择 → 环境检查 → 安装配置 → 验证完成”持续执行。只有缺少系统依赖、需要同意 `git init` 或必须重启时才暂停；暂停时只给一个下一步，并告诉用户完成后回复什么继续。

首次安装 Codex Skill 时，也可以在目标项目根目录用一条命令同时安装 Skill 和 hooks：

```bash
curl -fsSL https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.sh | bash -s -- codex --setup-project
```

Claude Code 将 `codex` 换成 `claude-user`。默认 `warn` 完全非阻断；只有明确添加 `--strict` 切换到 `enforce` 时才启用机械门禁和 Git pre-commit 兜底。

Windows PowerShell 可以使用原生安装器：

```powershell
& ([scriptblock]::Create((irm 'https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.ps1'))) codex -SetupProject
```

安装器会在写入文件前检查 Git、Python 3.9+ 和 Git 仓库。WishGraph 是不安装 Python 包的小型源码安装；只有缺少依赖时才提示额外成本。Git 通常约 200-500 MB、2-10 分钟；Python 通常约 100-300 MB、2-10 分钟；macOS 通过 Apple Command Line Tools 安装 Git 时可能约 1-3 GB、5-30 分钟。具体结果取决于系统、镜像和已有依赖。

### 自定义方式

从本仓库运行：

```bash
python3 skills/wishgraph/scripts/install_project_hooks.py \
  --target /path/to/project \
  --host all \
  --mode warn
```

首次配置默认使用 `--host all`；明确选择 `codex` 或 `claude` 时保持单端。Doctor 不传 `--host` 时检查配置中的 `required_hosts`。适配器修复始终只处理明确指定的一端，也不会改变该列表。

`current_host` 只表示执行安装的 Agent，不能静默缩小 `required_hosts`。双端激活会预检四个 Adapter/Agent 文件；任一写入失败都会恢复 runtime、配置和两端文件。现有无关 Hook 继续保留。单端选择完全有效，但未选择宿主中的普通会话不受保护。

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

安装器会把本次实际使用的 Python 可执行文件写入宿主命令和 `.wishgraph/config.json`，避免后续出现 `python3` 与 `py -3` 指向不同环境的问题。

对已启用项目，Skill 内的安装器还提供三个有界维护动作：`--doctor --json` 只读取固定路径并输出健康状态；`--upgrade --json` 可以为当前文件补齐缺失元数据，或原子替换内置已知版本的生成运行时，失败时自动回滚；`--repair-host-adapter --host codex|claude --json` 只修复所选当前宿主并保留其他 Hook。未知或本地修改过的运行时会停止并交给用户检查，不会直接覆盖。

正常用户只需要启用 WishGraph 并输入“开始讨论”。Doctor 会分别报告静态安装和近期宿主执行。`warn` 下缺少回执只是一项诊断，已批准任务仍可交给可见 Worker；`enforce` 下才需要使用对应 CLI 的 Hook 审查入口。

`memory_sync.py` 是稳定入口，内部保留四个公共边界：`workflow_state.py` 定义类型化状态，`policy.py` 实现纯状态转换，`host_adapter.py` 把唯一已授权动作映射到当前宿主，`git_state.py` 保存 Git 事实、规范 Run、Claim、session 和 Integration lease。`codex_worker_provider.py`、`claude_worker_provider.py` 和 `tool_gate_provider.py` 都是 `host_adapter.py` 背后的私有实现，不增加公共边界。项目语义真相仍保存在 Markdown 和 Git 中。

建议先用 `warn`。完成一次 Task-backed Worker 收尾和一次 Discussion-local Integration 后，再把 `.wishgraph/config.json` 改成 `enforce`。

`warn` 在没有加载 Adapter 时仍然可用且从不实施阻止；`enforce` 才要求已安装并加载 Adapter。两者都不是操作系统沙箱，可选 Git hook 也只是提交阶段兜底。

Codex 项目 Hook 需要项目配置层和精确 Hook 定义都被信任后才能运行；只有正常入口失败时，Doctor 才向用户显示这项排障信息。

## 并行收尾规则

每个 Worker 使用独立 branch 或 worktree，并新增一个不可变报告：

```text
reports/runs/<work-unit-id>-attempt-N.md
```

任务规格包含 `wishgraph:task-state`，执行报告包含 `wishgraph:run-state`，项目状态快照包含 `wishgraph:integration-state`。持久 Task 只走 `draft -> approved -> integrated -> reviewed`。`enforce` 由 Git common dir 中的规范 Run 负责派发、终态证据与集成进度；`warn` 把它作为可选自动化，直接交接边界是已批准 Task、不可变报告、结果 commit 和验证。

对已完成 Task 的小范围修正可以使用 `tasks/revisions/<task-id>-rN.md`，其中只保存 `wishgraph:revision-state`：原 Task、精确请求、允许范围、针对性验证、状态和一个不可变报告。Revision 报告使用 `change_class: revision`、原 Task 的 `task_id` 和精确 `revision_id`。只要涉及 API、schema、持久化、迁移、依赖、权限、安全、隐私或新产品决定，就必须升级为正式后续 Task。

Task Lifecycle 只是一个状态维度。Session Role（`neutral|discussion|worker`）、Flow Phase 和唯一结构化 `expected_transition` 分别保存在 Git common dir。`可以`、`执行吧` 之类简短回复只有在 transition 唯一时才可执行。

Worker 使用 `Integrate` 或 `N/A`，不直接修改共享项目记忆：

```markdown
| File | Result | Reason |
|---|---|---|
| `PRD.md` | N/A | 用户可见行为没有变化 |
| `CODEMAP.md` | Integrate | 新代码锚点需要写入项目地图 |
```

Discussion-local Integration 使用 `--no-commit` 合并 Worker commit，读取全部新增单次执行报告，更新受影响共享记忆，并把 `reports/PROJECT_STATUS.md` 重写为唯一面向用户的动态快照。`enforce` 要求绑定 lease；`warn` 保持 Discussion 本地单写，但不因 lease 自动化缺失而阻塞。

默认长度限制用于保持快照可用：项目状态概览最多 160 行、12000 字符，明确进入 Discussion 时的上下文最多 2000 字符。项目状态概览任一限制超出时，`warn` 静默放行，`enforce` 会阻止集成结束和提交；主动状态检查仍展示完整诊断。历史细节应移动到单次执行报告和 Git 历史；不能为了满足限制而删除仍未解决的风险、冲突或待决定事项。

WishGraph 要求一个明确的 `reports/PROJECT_STATUS.md` 真相源。预发布阶段的 `paths.dev_report`、`reports/DEV_REPORT.md`、隐藏 Task 路径和缺失 `required_hosts` 的配置不再自动猜测；请重新启用项目或重新生成对应结构化记录。

任务和执行报告元数据使用 `sequential`、`parallel_batch` 和 `high_risk` 区分工作，执行模式使用 `exclusive`、`parallel_independent` 和 `competitive`。有运行时自动化时，Worker terminal 事件进入 `integration_pending`；否则 `warn` Worker 直接返回报告和结果 commit。原 Discussion 集成安全结果，Worker 不获得 Integration 权限。

创建 Worker 始终需要人类明确命令。Codex 路径由适配器准备已授权的 `wishgraph-worker` payload，当前宿主创建可检查 Agent thread，再由 WishGraph 注册真实 thread ID；Hook 从不创建 Agent。Claude Code 只有在 `background_session` 能力检查通过时，才由 Host Adapter 执行等价于 `claude --bg --agent wishgraph-worker --worktree <unique> --settings <ephemeral-json> "执行 <task-id> 任务"` 的命令。受管 Agent 与全局 Adapter 可以只安装一次；每个项目仍由 `.wishgraph/config.json` 明确开启。宿主不支持或创建失败时输出项目目录、Codex/Claude 启动命令、各自配置和 Task 口令，然后停止。隐藏 subagent 不等于 Worker thread。Integration 是自动触发、Discussion-local、safe-when-silent 的阶段，不创建用户可见窗口；Discussion 不活跃时持久化 `integration_pending`，等下次进入或刷新后继续。

两条启动路径都不能把意图或自然语言当成完成证据。准确 Task preflight、不可变报告、结果 commit 和验证始终必需；`enforce` 还要求真实宿主身份、规范 Run、Claim 和已释放 Claim，`warn` 不因这些自动化缺失而阻塞。

新 session 默认中立且安静，只有恢复、待集成、失败恢复或待用户决定需要处理时才提示。Hook 不加载讨论提示词，也不激活窗口角色。用户说“开始讨论”后，当前可见窗口才读取 Project Status；持续运行窗口说“刷新项目状态”即可刷新。

持续运行的讨论窗口中可以直接说：`刷新 WishGraph 项目状态并呈现最新集成结果。`

业务代码工作必须在绑定准确 Task 的可见 Worker 中执行。`enforce` 要求 Claim，`warn` 把 Claim 作为可选自动化。正式 Task 使用 `tasks/*.md`，局部修订使用 `tasks/revisions/*.md`，报告必须包含结构化状态块。

## 直接运行检查

```bash
python3 .wishgraph/hooks/memory_sync.py check --scope worktree
python3 .wishgraph/hooks/memory_sync.py check --scope staged
python3 .wishgraph/hooks/memory_sync.py status
python3 .wishgraph/hooks/memory_sync.py status --task 012
python3 .wishgraph/hooks/memory_sync.py status --full
```

默认 `status` 输出精简 active 视图，只在可见 Git refs 中解析当前候选报告路径。`--task` 精确选择一个 Task，`--full` 才执行历史扫描。status 命令不会创建项目队列，也不会修改语义状态；独立的 Git-common notification inbox 只由通过验证的 Worker closeout 写入。讨论入口和刷新使用 active 视图；SessionStart 不注入它。

它还输出 `auto_integration_eligible`，以及 `nothing_to_integrate`、`wait_for_worker`、`auto_integrate`、`await_user_confirmation`、`discuss_blocker`、`compare_candidates` 之一作为 `next_action`。这些是内部路由字段，普通用户只看到 Discussion 和显式 Worker 窗口。

宿主适配器可以通过 `flow-plan` 只读计算纯 reducer。`enforce` 的 Discussion 语义变化经过 reducer、一次性 Integration grant 和 lease；`warn` 的 runtime 持久化失败时直接回退到准确可见 Worker 交接，不阻塞分发。Worker 不能把自己提升为 Discussion 或 Integration。

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

严格执行使用存放在 `git rev-parse --git-common-dir` 下、不会进入业务提交的仓库级 Runtime Claim；`warn` 可以尝试这些命令，但失败只作提示：

```bash
python3 .wishgraph/hooks/memory_sync.py claim acquire 012 --worker-id worker-012 --session-id worker-012 --discussion-session-id discussion-1 --host codex
python3 .wishgraph/hooks/memory_sync.py claim inspect 012
python3 .wishgraph/hooks/memory_sync.py claim heartbeat CLAIM_ID
python3 .wishgraph/hooks/memory_sync.py claim release CLAIM_ID
python3 .wishgraph/hooks/memory_sync.py claim revoke CLAIM_ID
```

获取 Claim 使用原子文件系统操作，默认同一 Task 只允许一个 active exclusive Claim，并记录 attempt、worker、branch、绝对 worktree、时间、lease 状态、执行模式、可选宿主线程引用，以及可用时的来源 Discussion。传入 `--session-id` 时同时持久化 Worker runtime；持久化失败会撤销新 Claim。heartbeat 与 release 校验 branch/worktree 绑定；显式 revoke 是接管控制路径。stale 检测保留旧记录。它能协调共享同一本地 Git common directory 的进程与 worktree，但不是只共享远程仓库的多机器分布式锁。

已经取得 Claim 时，`claim release` 会验证 Task/Revision 终态及 Run Report，再写入一条幂等 pending notification。`warn` 没有 Claim 自动化时，可见 Worker 结果就是交接。该机制不使用 daemon、终端轮询、跨终端 IPC、自动弹窗，也不从自然语言猜测 Worker 是否完成。

只有 `enforce` 会在 Worker 仍持有 active Claim 时阻止 terminal 事件。进程被强制结束后留下的 stale Claim 会保留为恢复证据，但不会阻止新的 Worker。

终态 Worker 窗口可以复用。先释放仍有效且已经取得的 Claim，并清除旧 scope；`enforce` 使用 `claim rebind`，`warn` 自动化不可用时可直接按准确新 Task 或 Revision 继续。旧工作仍在运行时不得复用。

`revision next 012` 分配下一个精确 Revision ID，`revision resolve 012-r1` 检查轻量记录，`revision route 012-r1 --host codex|claude` 计算宿主动作。Codex 有可复用的真实 Worker 记录时返回其目标，否则返回创建可见 Revision Worker 的动作；Claude Code 只返回最短手动命令。

`enforce` 下，Discussion-local Integration 先持久化 `phase: integrating`，再获取绑定 session、integration ID、Task、报告、branch 与 worktree 的 lease：

```bash
python3 .wishgraph/hooks/memory_sync.py integration-lease acquire \
  --session-id discussion-1 \
  --integration-id integration-012 \
  --task-id 012 \
  --report reports/runs/012-attempt-1.md
```

`enforce` 下，受支持的原生写入、可识别的 shell 构建／写入命令和写入类 MCP 工具要求活跃 Worker Claim，Integration 写入要求 Discussion-local lease；`warn` 下这些检查静默且不阻断。这是宿主工具门禁，不是操作系统 sandbox。

宿主未传 `--authorized-by-user` 时，`claim revoke` 返回 `explicit_user_authorization_required`。停止或拒绝尚未集成的工作会保留 branch/report；重试保留 Task ID 并递增 attempt。已集成历史只能通过新的回滚或 Follow-up Task 替换。

竞争执行使用只读计划：

```bash
python3 .wishgraph/hooks/memory_sync.py competitive-plan 012 --candidates 2
```

它提出 `012a`、`012b`、共同的 `comparison_group: 012`、独立 Claim/worktree/report，并规定只选一个胜者。status 只把客观唯一胜者放入 `selected_reports`；平分或 `selection_requires_judgment` 路由到 `compare_candidates`。失败候选不合并，标记为 `rejected` 或 `superseded`。

明确局部修正使用 Task Revision，新工作或扩展工作使用正式 Task；两者都不授权 Discussion 修改业务代码。

严格使用 `enforce` 模式时，建议给安装器增加 `--git-hook`，从而覆盖 Agent 以外的提交和生命周期 hook 无法拦截的工具路径。安装器不会覆盖已有 Git pre-commit hook，而是提示如何手动串联。

## 边界

- Hooks 不生成 PRD、架构、CODEMAP 或交接语义。
- Hooks 不会自动 stage、commit 或 amend。
- Hooks 会忽略自己的运行时和宿主配置文件。
- Hooks 不决定是否并行，不启动 Worker，不创建 Integration 窗口，不合并代码，也不代替人类 Review。
- Worker 被阻塞或未完成时，只要创建唯一的 Blocked 或 Incomplete 执行报告并记录验证、影响建议，就可以正常停下。
- 为仓库适配规则期间使用 `warn`，不要用虚假的 Updated 记录绕过检查。
