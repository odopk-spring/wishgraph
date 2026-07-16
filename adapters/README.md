# Host Adapters / 宿主适配器

WishGraph keeps project truth portable, but every Agent host exposes different lifecycle and Worker controls. Adapters explain how one host realizes the same Discussion → Worker → Integration state machine.

WishGraph 把项目事实保存在仓库中，但不同 Agent 宿主提供的生命周期和 Worker 控制能力不同。适配器负责说明当前宿主怎样实现同一套 Discussion → Worker → Integration 状态机。

## Normal user path / 普通用户路径

Codex and Claude Code users should use the installer and project runtime described in the root README. They do not need to copy these instruction files or migrate a full prompt between windows.

Codex 和 Claude Code 用户应使用首页里的安装器和项目 runtime。正常流程不需要复制本目录的 instruction，也不需要在窗口之间搬运完整提示词。

| Route / 路径 | Formal Worker | Mechanical gates / 机械门禁 |
| --- | --- | --- |
| Codex Skill + project runtime | Inspectable Agent thread when supported; one-line fallback otherwise | Codex project Hooks |
| Claude Code Skill + project runtime | Managed background session after capability checks; one-line fallback otherwise | Claude Code project Hooks |
| Generic instruction adapter | User-opened inspectable session unless the host supplies an equivalent integration | Policy guidance and direct checker commands only |

An adapter is not the WishGraph runtime. Copying an instruction file can explain roles, but it does not install native Worker creation, lifecycle Hooks, write/build gates, or completion notifications.

适配器不等于 WishGraph runtime。复制 instruction 文件只能解释角色，不能自动获得原生 Worker 创建、生命周期 Hooks、写入／构建门禁或完成提醒。

## Choose a guide / 选择指南

- Claude Code CLI: [English guide](claude-code/README.md) · [中文指南](claude-code/README.zh-CN.md)
- Generic Agent: [English guide](generic/README.md) · [中文指南](generic/README.zh-CN.md)

The `CLAUDE.md` and `AGENTS.md` files in this folder are optional always-loaded bridges. Use them only when a team deliberately wants those rules in the host's project instruction file.

本目录中的 `CLAUDE.md` 和 `AGENTS.md` 是可选的 always-loaded bridge。只有团队明确希望把规则常驻宿主项目 instruction 时才需要它们。

Installing a Skill globally still means “available,” not “active in every project.” Every project must explicitly opt in.

全局安装 Skill 仍然只表示“可用”，不代表每个项目自动启用。每个项目都必须明确选择加入。
