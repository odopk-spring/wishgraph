# WishGraph Documentation / 文档

Start with the repository homepage. The files below move from normal use to implementation detail; ordinary users do not need to read them all.

请先从仓库首页开始。下面的文档从普通使用逐步深入到实现细节，普通用户不需要全部阅读。

## Start here / 从这里开始

- Overview: [English README](../README.md) · [中文首页](../README.zh-CN.md)
- First complete run: [Getting Started](../GETTING_STARTED.md) · [中文上手指南](../GETTING_STARTED.zh-CN.md)
- Claude Code CLI: [English](../adapters/claude-code/README.md) · [中文](../adapters/claude-code/README.zh-CN.md)

## Understand the idea / 理解方法

- WishGraph method: [English](wishgraph-method.en.md) · [中文](wishgraph-method.md)
- Intent compiler: [English](intent-compiler.md) · [中文](intent-compiler.zh-CN.md)
- Anti-black-box Agent engineering: [English](anti-blackbox-agent-engineering.md) · [中文](anti-blackbox-agent-engineering.zh-CN.md)
- Desensitized project example: [English](paperchat-desensitized-workflow.md) · [中文](paperchat-desensitized-workflow.zh-CN.md)

## Protocol and safety / 协议与安全

- Roles, states, commands, and host behavior: [Orchestration state machine](orchestration-state-machine.md)
- Hooks, gates, installation details, performance, and host limits: [English](memory-sync-hooks.md) · [中文](memory-sync-hooks.zh-CN.md)

The installable Skill keeps detailed operational rules in `skills/wishgraph/references/`. Agents load those references on demand; they are not a reading list for users.

可安装 Skill 的详细运行规则位于 `skills/wishgraph/references/`。Agent 会按当前任务选择读取，用户不需要把它们当作必读清单。
