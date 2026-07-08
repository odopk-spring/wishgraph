# Getting Started With WishGraph

Use this guide when introducing WishGraph to an existing project or starting a new project with AI collaboration from day one.

## 0. Recommended First Conversation

Start with a planning or discussion AI, not an execution AI.

Ask it to:

```text
Use $wishgraph to help me set up WishGraph for this project.
If this is a new or vague project, first ask me what idea I have, then grill it into a PRD one question at a time.
If this is an existing repository, first read the repository, then discuss the project goal with me.
Create or update the PRD, architecture outline, CODEMAP, conventions, discussion prompt, execution prompt, first task spec, and Dev Report template.
Do not change business code yet.
```

The first useful output should be a project frame, not code.

For a blank project, the first question should be:

```text
你现在有什么想法？可以很粗糙，只要说你想做什么、给谁用、解决什么问题。
```

## 1. Establish The Project Frame

Before restructuring or implementation, discuss enough to produce a rough but usable project frame:

- Project purpose.
- Target users.
- Current stage.
- Main workflows.
- High-level architecture.
- Important constraints.
- Current progress.
- Immediate next task.

Record this in `PRD.md`, `ARCHITECTURE.md`, `CODEMAP.md`, and `prompts/DISCUSSION_AI.md`.

The first pass does not need to be perfect. It only needs to be concrete enough for future agents to continue without relying on chat memory.

Use a grill-first pattern: one question at a time, with a recommended default. The discussion AI should keep asking until it can write a useful PRD and a bounded first implementation task.

## 2. Create The External Memory Files

WishGraph works because the project, not the chat window, stores state.

Minimum files:

- `PRD.md`: product goals, scope, roadmap, and current decisions.
- `ARCHITECTURE.md`: structure, dependency boundaries, and ownership.
- `CODEMAP.md`: feature to file lookup and current implementation status.
- `CONVENTIONS.md`: collaboration rules, validation rules, git rules, and memory update rules.
- `prompts/DISCUSSION_AI.md`: mutable launch prompt for planning windows.
- `prompts/EXECUTION_AI.md`: stable launch prompt for execution windows.
- `.tasks/build/NNN-short-slug.md`: self-contained execution task specs.
- `.tasks/build/001-bootstrap-project.md`: first-use bootstrap task when the project starts from a vague idea.
- `reports/DEV_REPORT.md`: execution evidence and handoff notes.

## 3. Use The Two-Window Workflow

### Discussion AI Window

Use it to:

- Discuss user intent.
- Update or refine the PRD.
- Decide the next task boundary.
- Write `.tasks/build/*.md` execution specs.
- Read execution reports.
- Decide the next discussion direction.
- Capture user dissatisfaction and turn it into a follow-up task or spec update.

The discussion AI should not edit business code unless the project explicitly allows a trivial direct-edit exception.

If you want to move the discussion into another AI window, ask:

```text
请迁移讨论窗口，把当前讨论提示词完整显示出来供我复制。
```

The discussion AI should update `prompts/DISCUSSION_AI.md` first, then print the full prompt.

### Execution AI Window

Use it to:

- Read `prompts/EXECUTION_AI.md`.
- Read the assigned task spec.
- Implement only that task.
- Run validation.
- Output a Dev Report.
- Update the external memory files required by the task.
- Make one atomic commit per task unless the user explicitly says not to commit.

The execution AI should not redesign the feature. If the task spec is wrong, it should stop and report the conflict.

After the PRD and first task are ready, open a new execution window and paste:

1. The full content of `prompts/EXECUTION_AI.md`.
2. The full content of the approved `.tasks/build/NNN-short-slug.md`.

## 4. Execution Loop

The normal loop is:

```text
Human intent
-> Discussion AI updates PRD / roadmap / current state
-> Discussion AI writes task spec
-> Execution AI implements task spec
-> Execution AI validates and reports
-> Execution AI updates external memory
-> Discussion AI reads report
-> Human decides next direction or correction
```

If a single execution result is unsatisfactory, keep the correction in the discussion window. The discussion AI should decide whether the fix is:

- A task-spec clarification.
- A PRD update.
- A dependency or architecture update.
- A CODEMAP update.
- A small follow-up task.
- A rollback or repair task.

## 5. External Memory Must Stay Current

Any agent window must update external memory when it learns something that changes project truth.

Update these files when relevant:

- `PRD.md`: product goal, scope, roadmap, user-visible behavior, accepted tradeoffs.
- `ARCHITECTURE.md`: dependency direction, module ownership, service boundaries, data flow.
- `CODEMAP.md`: feature status, file locations, public contracts, runtime probes.
- `CONVENTIONS.md`: workflow rules, validation rules, git rules, memory update obligations.
- `prompts/DISCUSSION_AI.md`: current progress, active task, next likely task, open decisions, known risks.
- `.tasks/build/*.md`: task status and execution-relevant corrections.
- `reports/DEV_REPORT.md`: what was done, validation evidence, residual risk, next handoff.

If an agent cannot update a required file, it must say so and provide the exact text that should be added.

## 6. First Task Recommendation

For an existing project, the first task should usually be governance setup, not feature implementation:

```text
001-wishgraph-bootstrap
```

It should create the external memory skeleton, summarize current structure, and define the first real implementation task.

For a new project, the first discussion should grill the idea into PRD and architecture before code. The first tracked task can be:

```text
001-bootstrap-project
```

The first implementation task should usually be `002-*`, written only after the PRD is clear enough.

## 7. Success Criteria

WishGraph is working when:

- A fresh discussion AI can understand current project status by reading files.
- A fresh execution AI can implement a task without chat history.
- Every completed task leaves validation evidence.
- PRD, architecture, CODEMAP, prompts, task status, and reports stay synchronized.
- The user can correct direction in the discussion window and have that correction become durable project memory.
