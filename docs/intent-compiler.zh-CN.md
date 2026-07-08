# Intent Compiler

Intent Compiler 是 WishGraph 的工程侧。

它把模糊的人类愿望转换为可以实现、测试、评审和跨会话接续的结构化产物。

## 输入

人类输入是低带宽的：

- 自然语言。
- 语音。
- 截图。
- 视频。
- 屏幕状态。
- 行为轨迹。
- “这里感觉不对”。

Compiler 不应该期待人类直接提供完整规格。它应该提取意图、提出聚焦问题，并把模糊点转成明确假设。

## 编译阶段

```text
Wish
-> Intent
-> Acceptance criteria
-> Spec Graph update
-> Task Graph update
-> Execution task
-> Patch
-> Probe result
-> Review summary
```

## 必需产物

### Intent Record

用自然语言记录用户想要什么。

### Spec Delta

记录项目事实是否变化，以及变化在哪里。

### Task Spec

实现 agent 可以执行的任务单元。

### Probe Plan

验证面：测试、构建、截图、日志、指标或手动检查。

### Review Report

面向人类的压缩结果。

## Compiler 失败模式

- 把模糊意图当成发明范围的许可。
- 在澄清成功标准前写实现。
- 依赖聊天上下文，而不是任务文件。
- 省略验证。
- 隐藏不确定性。
- 执行后没有更新项目地图。

## 原则

当另一个 agent 不需要原始对话也能继续项目时，compiler 才算成功。
