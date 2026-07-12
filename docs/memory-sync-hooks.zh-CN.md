# WishGraph 外置记忆 Hooks

WishGraph hooks 的目标，是机械检查并行 Worker 收尾和单写者集成，同时不要求脚本理解产品语义。

## 为什么使用三个事件

```text
SessionStart -> 恢复遗留状态，并注入最新集成结果
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

建议先用 `warn`。完成一次正式任务和一次 ad-hoc 修改的正确收尾后，再把 `.wishgraph/config.json` 改成 `enforce`。

Codex 用户还需要信任目标仓库，并通过 `/hooks` 审阅新 hook；未信任项目不会运行项目级 hooks。

## 并行收尾规则

每个 Worker 使用独立 branch 或 worktree，并新增一个不可变报告：

```text
reports/runs/<work-unit-id>.md
```

Worker 使用 `Integrate` 或 `N/A`，不直接修改共享项目记忆：

```markdown
| File | Result | Reason |
|---|---|---|
| `PRD.md` | N/A | 用户可见行为没有变化 |
| `CODEMAP.md` | Integrate | 新代码锚点需要写入项目地图 |
| `prompts/DISCUSSION_AI.md` | Integrate | 合并后向讨论 AI 呈现完成结果 |
```

集成 Agent 使用 `--no-commit` 合并 Worker commit，读取全部新增执行报告，更新受影响共享记忆、`reports/DEV_REPORT.md` 和 `prompts/DISCUSSION_AI.md` 动态状态。项目概览列出全部已吸收报告，并使用 Updated 或 N/A。

任务和执行报告元数据使用 `sequential`、`parallel_batch` 和 `high_risk` 区分工作。安全串行任务的批准包含正常集成授权；并行批次和高风险工作必须在集成前取得用户明确确认。Hooks 只检查已记录授权，不授予权限。

创建 Worker 始终需要人类明确命令；随后宿主支持时可以由讨论 Agent 创建用户可见 Worker，Hooks 绝不创建。隐藏 subagent 不等于 Worker 窗口，平台不能创建可见任务时才降级为手动复制。集成是临时事件角色：平台支持且授权允许时使用后台任务或独立线程，否则明确切换当前主 Agent，或给出一条用户启动指令；不得虚构后台执行。

下一次受支持的 session 启动或恢复时，Hook 会把 `Latest Integrated Results` 精简结果和讨论交接注入上下文，讨论 AI 可以自动向用户呈现。它不是向持续运行窗口实时推送；这种情况需要显式刷新项目状态。

持续运行的讨论窗口中可以直接说：`刷新 WishGraph 项目状态并呈现最新集成结果。`

Ad-hoc 修改可以省略 `.tasks/build/*.md`，但不能省略验证、唯一执行报告 ID 或正常 commit 边界。

## 直接运行检查

```bash
python3 .wishgraph/hooks/memory_sync.py check --scope worktree
python3 .wishgraph/hooks/memory_sync.py check --scope staged
python3 .wishgraph/hooks/memory_sync.py status
```

`status` 输出机器可读的待集成状态、集成类型、准备报告、等待报告、阻塞报告、是否需要用户确认和理由。它读取可见 Git refs 中的不可变报告，不写入共享队列文件。SessionStart 可以注入这个状态，让讨论 AI 主动引导用户。

严格使用 `enforce` 模式时，建议给安装器增加 `--git-hook`，从而覆盖 Agent 以外的提交和生命周期 hook 无法拦截的工具路径。安装器不会覆盖已有 Git pre-commit hook，而是提示如何手动串联。

## 边界

- Hooks 不生成 PRD、架构、CODEMAP 或交接语义。
- Hooks 不会自动 stage、commit 或 amend。
- Hooks 会忽略自己的运行时和宿主配置文件。
- Hooks 不决定是否并行，不启动 Worker 或集成 Agent，不合并代码，也不代替人类 Review。
- Worker 被阻塞或未完成时，只要创建唯一的 Blocked 或 Incomplete 执行报告并记录验证、影响建议，就可以正常停下。
- 为仓库适配规则期间使用 `warn`，不要用虚假的 Updated 记录绕过检查。
