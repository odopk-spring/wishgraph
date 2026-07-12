# User-Visible Worker Launch

Use this protocol when a discussion agent has finished one or more approved task specs and the user wants Worker execution to begin.

## Authority Boundary

The discussion agent may offer:

```text
The task is ready. Create the execution window?
```

That offer is not authority to create anything. Create Worker tasks only after an explicit human command, such as:

```text
创建执行窗口
```

or:

```text
为这三个任务分别创建执行窗口
```

Equivalent wording in the user's language is valid when it clearly authorizes creation. A single-task command authorizes only the current approved task. A batch command authorizes exactly the approved tasks named or unambiguously referenced by the user. Do not create extra Workers.

This remains an explicit Worker workflow because the human authorizes creation and each resulting task is visible, user-owned, inspectable, and controllable. Never substitute a hidden subagent or silently create a background Worker.

Worker-creation authority is not integration authority. Apply the separate sequential, parallel-batch, and high-risk integration rules after execution.

## Before Creation

Verify all of the following:

- The task is approved and has a self-contained `.tasks/build/*.md` specification.
- The discussion agent has classified the work and explained the serial or parallel recommendation.
- `prompts/EXECUTION_AI.md` is present and current.
- Each Worker can use an isolated branch or worktree when the platform supports it.
- The Worker will receive the actual approved prompt and task specification, not merely paths that may be absent from its starting snapshot.

Prefer a committed planning state so a new worktree can read the files directly. If the approved prompt or task spec is not present in the Worker's starting snapshot, include its full content in the initial message or use a platform-supported working-tree snapshot only when that is safe and authorized. Do not create an empty Worker that cannot see its instructions.

## Creation Payload

Give each Worker:

1. Its canonical display name as the first line.
2. The instruction to act only as the Worker for the assigned task.
3. The authoritative content or accessible location of `prompts/EXECUTION_AI.md`.
4. The authoritative content or accessible location of the assigned `.tasks/build/*.md` file.
5. The project, target branch, isolated-worktree expectation, and required immutable run-report path.
6. A reminder that it must not edit shared project memory or start other agents.

Use this naming format:

```text
<task-id> · <short title> · WG Worker
```

Examples:

```text
012 · Auth Refresh · WG Worker
013 · Settings UI · WG Worker
```

If the platform supports explicit task titles, set the title. If it only supports automatic naming, put the canonical name on the first line of the initial message.

## Platform Routing

Use the current host's user-visible task or thread creation capability when it exists.

- In Codex, create a user-owned visible task in the current project, prefer an isolated worktree environment, pass the execution prompt and task specification in the initial message, and set the canonical title when title control is available. Do not use a hidden subagent as the Worker.
- On another host, use the equivalent user-visible session, task, or thread capability with the same authority and payload rules.
- If the platform cannot create user-visible tasks, or creation fails, say so truthfully and provide one complete copyable launch package containing the canonical name, `prompts/EXECUTION_AI.md`, and the approved task specification. Manual copying is the fallback, not the default.

After creation, report which visible Worker tasks were created and where the user can find them. If only some tasks in a batch were created, identify the successful and failed items separately; do not imply the whole batch started.
