# Getting Started With WishGraph

Use this guide when introducing WishGraph to an existing project or starting a new project with AI collaboration from day one.

## 0. Recommended First Conversation

Start in a Discussion window, not a Worker window.

For the lowest-friction setup, say:

```text
使用 $wishgraph 为当前项目做安全配置。请自动检测系统、Agent、Git 和 Python；缺少依赖时先告诉我安装方式、预计空间和时间，不要直接安装系统依赖。
```

WishGraph defaults to non-blocking safe hooks. If the user says "只安装 Skill" it skips hooks; if the user says "严格配置" it enables blocking hooks and the Git pre-commit fallback. If the request is unclear, the agent asks only one choice question.

The agent first recommends the best fit rather than showing an unexplained menu. After the user replies "按推荐来", it guides four short stages—choice, prerequisites, installation, verification—and continues automatically. When a dependency or restart requires user action, it provides the reason, rough cost, one recommended action, and an exact resume phrase.

Use the invocation format for your tool:

```text
Codex: Use $wishgraph to help me set up WishGraph for this project.
Claude Code: /wishgraph help me set up WishGraph for this project.
Generic agent: Follow AGENTS.md and help me set up WishGraph for this project.
```

WishGraph supports Chinese, English, and bilingual handoff. To request bilingual output, add:

```text
Please use bilingual Chinese and English output for user-facing prompts and summaries. Keep file paths, commands, and code identifiers unchanged.
```

Manual materials are also available in both languages:

- Templates: `templates/` and `templates/zh-CN/`
- Adapters: `adapters/`
- Docs: `docs/`

Ask it:

```text
If this is a new or vague project, first run the WishGraph intake prompt, then grill it into a PRD one decision at a time.
If this is an existing repository, first read the repository, then discuss the project goal with me.
Create or update the PRD, architecture outline, CODEMAP, conventions, discussion prompt, execution prompt, first task spec, and Dev Report template.
Do not change business code yet.
```

The first useful output should be a project frame, not code.

For a blank project, the first intake prompt should be:

```text
先不用写完整 PRD。请用几句话告诉我：
1. 你想做一个什么项目？
2. 最先服务谁？
3. 他们第一次打开时最应该完成什么动作？
4. 你会用什么结果判断 v0 做对了？
如果还不确定，可以只回答第 1 点，我会继续一问一问补齐。
```

English:

```text
You do not need a full PRD yet. In a few sentences, tell me:
1. What are you trying to build?
2. Who should it serve first?
3. What should they be able to do on the first successful use?
4. What result would make you say v0 is working?
If you are not sure, answer only item 1 and I will fill the rest one decision at a time.
```

Bilingual mode asks both lines together.

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

Also record the project language mode in `prompts/DISCUSSION_AI.md`, so future Discussion and Worker windows preserve the same Chinese, English, or bilingual style.

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
- `prompts/EXECUTION_AI.md`: stable launch prompt for Worker windows.
- `prompts/INTEGRATION_AI.md`: stable phase prompt for Discussion-local merging and shared-state updates; it never launches a separate window.
- `tasks/build/NNN-short-slug.md`: visible, self-contained execution task specs.
- `tasks/build/001-bootstrap-project.md`: first-use bootstrap task when the project starts from a vague idea.
- `reports/RUN_REPORT.md`: template for one immutable report per worker execution.
- `reports/runs/<work-unit-id>.md`: worker-specific validation and integration proposals.
- `reports/PROJECT_STATUS.md`: current integrated Project Status; it is a rewritten snapshot, not a history log.

New Task Specs, Run Reports, and Project Status snapshots contain small versioned JSON blocks for lifecycle facts. Keep product meaning, evidence, risks, and decisions in normal Markdown; do not move semantic project truth into the structured block.

## 2.5. Optionally Enforce Memory Closeout With Hooks

WishGraph can install project-local Codex and Claude Code hooks without replacing unrelated existing hook groups:

The easiest option is to tell the agent:

```text
Use $wishgraph to enable automatic memory sync for this project in safe mode.
```

The agent selects the current host and installs non-blocking `warn` hooks. No hook parameters need to be learned.

For a first-time command-line installation, add `--setup-project` to install the skill and current-host hooks together:

```bash
curl -fsSL https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.sh | bash -s -- codex --setup-project
```

The lower-level installer remains available for custom paths or dual-host repositories:

```bash
python3 skills/wishgraph/scripts/install_project_hooks.py \
  --target /path/to/project \
  --host all \
  --mode warn
```

The hooks check three boundaries: pending state at session start, staged memory before an agent runs `git commit`, and worktree memory before an agent stops. Start in `warn`; switch `.wishgraph/config.json` to `enforce` after one successful closeout. Codex users must trust the project and review the new definitions with `/hooks`.

To switch in one command, re-run the top-level installer with `--setup-project --strict`. Strict mode also requests a Git pre-commit fallback and will not overwrite an existing Git hook.

Hooks do not write PRD, architecture, CODEMAP, Project Status, or handoff prose. Workers record Integrate or N/A in task-scoped Run Reports; the Discussion-local Integration lease holder applies shared updates and records Updated or N/A in `reports/PROJECT_STATUS.md`.

The read-only command `python3 .wishgraph/hooks/memory_sync.py status` joins Task Specs, Run Reports, and Project Status into `work_units`, then reports ready, waiting, and blocked workers, integration kind, confirmation requirement, and reason. Hooks do not start Workers or create Integration windows.

## 3. Use The Foreground Discussion Workflow

### Discussion AI Window

Open any normal window and say `开始讨论` / `Start discussion`. WishGraph then reads the discussion prompt and current project status in that visible window. New windows remain neutral by default; SessionStart only surfaces safety problems and does not silently choose a role. Say `刷新项目状态` / `Refresh project state` to reload current state without opening another window.

Use it to:

- Discuss user intent.
- Update or refine the PRD.
- Decide the next task boundary.
- Write `tasks/build/*.md` execution specs.
- Read execution reports.
- Read the latest integrated overview before presenting completed results.
- Decide the next discussion direction.
- Capture user dissatisfaction and turn it into a follow-up task or spec update.
- Classify proposed work as discussion, sequential, parallel_batch, or high_risk and explain the recommendation.
- Present completed, waiting, and blocked workers plus pending integration and one next action.

Discussion never edits business code, installs implementation dependencies, or runs Worker implementation validation. Those operations require a separate Worker with a bound Claim; there is no direct-edit exception. Discussion-local Integration may run only the merge and combined validation authorized by its bound Integration lease.

Task IDs are exact structured identifiers such as `012`, `012a`, and `012aa`; readable slugs stay in filenames. Compact commands such as `执行012b` are accepted alongside explicit forms such as `执行012b号任务`; you can also say `查看012号任务` or `查看012系列任务`. Exact execution never prefix-matches a follow-up. A retry keeps `012`, increments its attempt, and writes a new report instead of allocating `012a`.

You can also say `停止012号任务`, `重新执行012号任务`, `接管012号任务`, or `让两个 Agent 分别执行012，最后比较谁做得好`. Stop/takeover preserves prior evidence and requires explicit Claim revocation; competitive execution creates isolated candidates and integrates exactly one winner. Existing `micro` work units remain readable, but they still execute in a separate claimed Worker; Discussion never implements them directly.

WishGraph controls token use by keeping neutral windows role-free, loading only the current dynamic Discussion state, limiting each Worker to its prompt, Task Spec, and necessary code, and limiting Integration to selected reports plus affected shared state. Refresh does not reload a full stable prompt. Historical detail stays in immutable Run Reports and Git; completion callbacks are used only when the host truly supports them, otherwise progress appears on the next explicit Discussion entry or refresh.

If you want to move the discussion into another AI window, ask:

```text
请迁移讨论窗口，把当前讨论提示词完整显示出来供我复制。
```

The discussion AI should update `prompts/DISCUSSION_AI.md` first, then print the full prompt.

### Worker Window

Use it to:

- Read `prompts/EXECUTION_AI.md`.
- Read the assigned task spec.
- Implement only that task.
- Run validation.
- Create one immutable `reports/runs/<work-unit-id>.md`.
- Propose shared-memory updates without editing shared files.
- Make one atomic commit per task unless the user explicitly says not to commit.

The Worker should not redesign the feature. If the Task Spec is wrong, it stops and reports the conflict.

Workers do not start silently or as hidden subagents. When a Task is ready, Discussion asks for explicit authorization to launch the named Worker. After that command, Discussion creates a user-visible Worker task when the platform supports it, hands off `prompts/EXECUTION_AI.md` and the exact Task Spec automatically, and then the user can observe or control that Worker from the task list. The user does not edit project-memory or integration files.

### Discussion-Local Integration Phase

After every Worker terminal event, enter `integration_pending` and evaluate the result. For a safe result, Discussion temporarily enters Integration while holding a bound Integration lease. It merges without committing, reads approved run reports, resolves permitted conflicts, updates shared memory, rewrites the current Project Status, refreshes the discussion handoff, validates, creates the integration commit, and returns to result presentation. Integration is not a separate window or permanent role.

For one safe sequential task, approving the Task also authorizes normal integration after all validation, scope, conflict, decision, rollback, and target-worktree gates pass. Do not ask twice. A `parallel_independent` batch also integrates silently when every expected Worker is terminal and overlap, dependency, interface, risk, merge, and combined-validation gates are mechanically clear. High-risk, conflicting, competitive, or ambiguous results enter `decision_required`; missing reports, failed validation, or inconsistent terminal state become `blocked` or `incomplete`.

If Discussion is not active when a Worker finishes, persist `integration_pending` and continue automatically when Discussion resumes. Ask the user only for a concrete risk, conflict, compatibility, or product decision; never ask whether to start integration.

After the PRD and first Task are ready, Discussion states the work type, explains the sequential or parallel recommendation, names the ready Task files, and asks:

```text
Task 012 is ready. Authorize its Worker launch?
```

The user can reply:

```text
执行 012 任务
```

For a ready parallel batch, one explicit batch command can authorize exactly the listed Workers:

```text
为 012、013、014 分别启动 Worker
```

The discussion Agent then creates one user-visible task per authorized Worker, automatically provides the execution prompt and corresponding task specification, prefers an isolated branch or worktree, and names each task `<task-id> · <short title> · WG Worker` so the useful task identity appears before any sidebar truncation. This is still explicit execution: the Agent cannot create a Worker before the human command, cannot create unlisted Workers, and cannot substitute hidden subagents.

If the current platform cannot create user-visible tasks, or a creation attempt fails, Discussion outputs exactly one line and stops:

```text
执行 <task-id> 任务
```

In a neutral window, that exact command enters the Worker role after all Task and Claim gates pass. Hooks never launch Workers.

## 4. Worker And Integration Loop

The normal loop is:

```text
Human intent
-> Discussion AI updates PRD / roadmap / current state
-> Discussion AI writes task spec
-> Discussion AI explains discussion / sequential / parallel_batch / high_risk
-> Human explicitly authorizes creation of the named Worker task(s)
-> Discussion AI creates and configures user-visible Worker task(s)
-> Worker AI implements task spec in an isolated branch or worktree
-> Worker AI validates and creates an immutable run report
-> Worker terminal event creates integration_pending
-> Discussion-local Integration evaluates and safely integrates with a lease
-> Integration rewrites PROJECT_STATUS and refreshes the concise discussion handoff
-> Risk or conflict becomes one concrete decision_required question
-> Discussion presents the result
-> Human reviews the result and decides next direction or correction
```

If a single execution result is unsatisfactory, keep the correction in the discussion window. The discussion AI should decide whether the fix is:

- A task-spec clarification.
- A PRD update.
- A dependency or architecture update.
- A CODEMAP update.
- A small follow-up task.
- A rollback or repair task.

## 5. External Memory Must Stay Current

Workers review shared-memory impact but do not edit shared project truth. They record Integrate or N/A in their own run report. The Discussion-local Integration phase applies the proposals, updates shared files, and records Updated or N/A in Project Status.

Update these files when relevant:

- `PRD.md`: product goal, scope, roadmap, user-visible behavior, accepted tradeoffs.
- `ARCHITECTURE.md`: dependency direction, module ownership, service boundaries, data flow.
- `CODEMAP.md`: feature status, file locations, public contracts, runtime probes.
- `CONVENTIONS.md`: workflow rules, validation rules, git rules, memory update obligations.
- `prompts/DISCUSSION_AI.md`: current progress, active task, next likely task, open decisions, known risks.
- `tasks/build/*.md`: task status and execution-relevant corrections. Existing `.tasks/build/*.md` projects remain supported.
- `reports/runs/<work-unit-id>.md`: worker facts, validation, risk, and integration proposals.
- `reports/PROJECT_STATUS.md`: current integrated results, validation, unresolved items, Worker state, and next recommendation.
- `.wishgraph/config.json`: hook mode and machine-readable closeout paths when hooks are installed.

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
- A fresh Worker can implement a Task without chat history.
- Every completed task leaves validation evidence.
- PRD, architecture, CODEMAP, prompts, task status, and reports stay synchronized.
- The user can correct direction in the discussion window and have that correction become durable project memory.
- When hooks are enabled, an unsynchronized commit or completion boundary is detected before the work is reported as done.
