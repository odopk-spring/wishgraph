# WishGraph

**WishGraph / Intent Compilation System** is a reusable Codex skill and template set for turning vague project intent into auditable specs, tasks, code maps, validation evidence, and review reports.

WishGraph is not "let AI write random code." It is a file-backed project operating layer:

```text
Wish -> Spec Graph -> Task Graph -> Code Change -> Probe -> Report -> Human Review
```

The core move is simple: stop depending on chat memory for complex work. Put the project state in durable files that any future agent can read, audit, and continue.

The normal user experience is one foreground discussion AI, human-authorized user-visible Worker tasks created and configured by that Agent, and an event-triggered temporary integration agent. Discussion AI recommends discussion, sequential, parallel_batch, or high_risk work; the user confirms the execution shape and explicitly authorizes Worker creation. Hooks expose state and enforce boundaries but do not choose parallelism, launch workers, merge code, write semantic memory, or replace human review.

## Install For Your Agent

Install only the skill or adapter you need first. You do not need to clone the whole repository just to try WishGraph.

After the Skill is available, users do not need to learn hook names or flags. Say one of these in the project:

```text
只安装 WishGraph Skill，不开启 Hooks。
请为当前项目安全配置 WishGraph。（推荐）
请为当前项目严格配置 WishGraph，阻止遗漏的记忆同步。
```

WishGraph detects Codex or Claude Code, the operating system, the project path, Git, and Python. If the request is vague, it asks only: "只安装 Skill、安全配置（推荐），还是严格配置？"

The agent should recommend before asking. A first-project response looks like:

```text
我检测到你正在为当前项目配置 WishGraph。推荐“安全配置”：安装 Skill 和提醒型 Hooks，不会阻止结束或提交；WishGraph 本身约 0.3 MB，通常不到 1 分钟。

你可以回复“按推荐来”，也可以说“只装 Skill”或“严格配置”。
```

After the choice, the agent continues through prerequisite checks, installation, and verification. It pauses only when the user must install a system dependency, approve `git init`, or restart the agent; every pause gives one next action and an exact reply for resuming.

Safe setup uses non-blocking `warn` hooks. Strict setup uses blocking `enforce` hooks plus the Git pre-commit fallback.

### Codex

In Codex, ask:

```text
Use $skill-installer to install https://github.com/odopk-spring/wishgraph/tree/main/skills/wishgraph
```

Restart Codex after installation if the installer asks you to.

Lowest-friction option: open a terminal in the target project and install both the Codex skill and safe memory-sync hooks in one command:

```bash
curl -fsSL https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.sh | bash -s -- codex --setup-project
```

This starts in non-blocking `warn` mode. After one successful task closeout, re-run with `--setup-project --strict` to enable blocking checks and the Git pre-commit fallback.

On Windows PowerShell, use:

```powershell
& ([scriptblock]::Create((irm 'https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.ps1'))) codex -SetupProject
```

If you installed the older long-name skill, remove `~/.codex/skills/wishgraph-project-governor` and install `wishgraph` instead.

Manual fallback:

```bash
mkdir -p ~/.codex/skills
cp -R skills/wishgraph ~/.codex/skills/
```

Then open any project in Codex and ask:

```text
Use $wishgraph to start or govern this project with WishGraph. If the project is not framed yet, run the WishGraph intake prompt and grill it into a PRD before writing code.
```

For bilingual Chinese and English handoff, add:

```text
Use bilingual Chinese and English for user-facing prompts and summaries. Keep file paths, commands, and code identifiers unchanged.
```

### Claude Code

Install WishGraph as a Claude Code user skill:

```bash
curl -fsSL https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.sh | bash -s -- claude-user
```

To install the skill and safe project hooks together, run the command from the target project with `--setup-project`:

```bash
curl -fsSL https://raw.githubusercontent.com/odopk-spring/wishgraph/main/scripts/install-wishgraph.sh | bash -s -- claude-user --setup-project
```

Then open a Claude Code project and run:

```text
/wishgraph start or govern this project with WishGraph. If the project is not framed yet, run the WishGraph intake prompt and grill it into a PRD before writing code.
```

You can also add the same bilingual instruction after the command.

For project-local installation and `CLAUDE.md` guidance, see [adapters/claude-code](adapters/claude-code).

### Other Agent Tools

For tools that do not support Codex or Claude Code skills, copy the generic adapter into the target project:

```bash
cp adapters/generic/AGENTS.md /path/to/project/AGENTS.md
```

Then start the agent with:

```text
Follow AGENTS.md. Start WishGraph for this project. If there is no PRD, run the WishGraph intake prompt and grill it into a PRD before writing code.
```

See [adapters/generic](adapters/generic) for the tool-agnostic protocol.

The skill is project-neutral. It carries the required templates inside `skills/wishgraph/assets/templates`, so it can create the initial project memory files without asking the user to download the rest of the repository. The top-level `templates/`, `adapters/`, and `docs/` folders are for browsing, manual use, and deeper reading.

Users who already installed the skill can avoid commands entirely. In the project, ask the agent: `Use $wishgraph to enable automatic memory sync for this project in safe mode.` WishGraph will select the current host and install project-local hooks in `warn` mode.

The installer checks prerequisites before writing files. WishGraph itself uses about 0.2 MB and hooks add less than 0.1 MB. Only when Git or Python is missing does it show platform-specific installation guidance and rough cost: Git commonly 200-500 MB and 2-10 minutes; Python commonly 100-300 MB and 2-10 minutes. The Apple Command Line Tools route for Git is larger, roughly 1-3 GB and 5-30 minutes. These are broad estimates, not download guarantees.

For the recommended first-use workflow, see [GETTING_STARTED.md](GETTING_STARTED.md).

For bilingual docs and a desensitized carrier example of the workflow, see [docs](docs). The PaperChat-style example explains the foreground discussion, explicit worker, and temporary integration process without exposing private product code or business details.

## Why This Exists

AI coding fails on complex projects less because it cannot write code, and more because it loses context, expands scope, guesses file locations, forgets prior decisions, and leaves humans unable to audit what changed.

WishGraph addresses that by externalizing the working memory:

- **Spec Graph**: what the project is supposed to do.
- **Dependency Map**: which features, modules, interfaces, and files affect each other.
- **Causal Log**: why the project changed, which decisions were made, and what failed before.
- **Probe**: the checks that catch regressions and prove behavior.
- **Review Window**: the compressed human-facing summary of plans, risks, validation, and choices.

WishGraph uses a hybrid state boundary. PRD, architecture, CODEMAP, evidence, risks, and decisions remain human-readable Markdown. Machine workflow facts such as task status, work type, authorization, safety gates, validation results, and absorbed report paths live in small versioned JSON blocks embedded in Task Specs, Run Reports, and Project Status. Hooks evaluate those blocks but never generate semantic project truth.

Review remains a human-facing view inside discussion, not a permanent fourth agent. Safe sequential task approval includes normal integration authority; parallel batches require a second explicit integration approval.

The human stays in charge of direction and judgment. AI handles the high-bandwidth translation into specs, tasks, code edits, validation, repair, and reports.

## Repository Contents

```text
wishgraph/
├── adapters/
│   ├── claude-code/
│   ├── generic/
│   └── README.md
├── README.md
├── GETTING_STARTED.md
├── LICENSE
├── NOTICE
├── skills/
│   └── wishgraph/
│       ├── assets/hooks/
│       └── scripts/install_project_hooks.py
├── scripts/
│   ├── install-wishgraph.sh
│   └── install-wishgraph.ps1
├── templates/
│   ├── README.md
│   ├── PRD.md
│   ├── CODEMAP.md
│   ├── CONVENTIONS.md
│   ├── ARCHITECTURE.md
│   ├── prompts/
│   │   ├── DISCUSSION_AI.md
│   │   ├── EXECUTION_AI.md
│   │   └── INTEGRATION_AI.md
│   ├── tasks/build/001-bootstrap-project.md
│   ├── tasks/build/EXAMPLE-good-task.md
│   ├── tasks/build/NNN-task.md
│   ├── reports/PROJECT_STATUS.md
│   ├── reports/RUN_REPORT.md
│   └── zh-CN/
└── docs/
    ├── README.md
    ├── wishgraph-method.md
    ├── wishgraph-method.en.md
    ├── intent-compiler.md
    ├── intent-compiler.zh-CN.md
    ├── anti-blackbox-agent-engineering.md
    ├── anti-blackbox-agent-engineering.zh-CN.md
    ├── memory-sync-hooks.md
    ├── memory-sync-hooks.zh-CN.md
    ├── paperchat-desensitized-workflow.md
    └── paperchat-desensitized-workflow.zh-CN.md
```

## Language Support

WishGraph supports Chinese, English, and bilingual project memory.

Repository browsing:

- [templates](templates): English templates plus [`templates/zh-CN`](templates/zh-CN) Chinese templates.
- [adapters](adapters): English and Chinese adapters for Claude Code and generic agent tools.
- [docs](docs): Chinese and English method notes and workflow examples.

The installable skill also bundles both English and Chinese template sets under `skills/wishgraph/assets/templates/`, so users can install only the skill and still bootstrap a Chinese-first project.

The first blank-project intake prompt is:

```text
先不用写完整 PRD。请用几句话告诉我：
1. 你想做一个什么项目？
2. 最先服务谁？
3. 他们第一次打开时最应该完成什么动作？
4. 你会用什么结果判断 v0 做对了？
如果还不确定，可以只回答第 1 点，我会继续一问一问补齐。

You do not need a full PRD yet. In a few sentences, tell me:
1. What are you trying to build?
2. Who should it serve first?
3. What should they be able to do on the first successful use?
4. What result would make you say v0 is working?
If you are not sure, answer only item 1 and I will fill the rest one decision at a time.
```

When bilingual mode is enabled, key user-facing prompts, summaries, decisions, and task explanations should be written Chinese first, English second. File paths, commands, code identifiers, symbols, routes, package names, and environment variables stay unchanged.

## Manual Template Use

If you do not want to install the skill, copy the templates into a project manually:

```bash
cp templates/PRD.md /path/to/project/PRD.md
cp templates/CODEMAP.md /path/to/project/CODEMAP.md
cp templates/CONVENTIONS.md /path/to/project/CONVENTIONS.md
cp templates/ARCHITECTURE.md /path/to/project/ARCHITECTURE.md
mkdir -p /path/to/project/prompts /path/to/project/tasks/build /path/to/project/reports
cp templates/prompts/DISCUSSION_AI.md /path/to/project/prompts/DISCUSSION_AI.md
cp templates/prompts/EXECUTION_AI.md /path/to/project/prompts/EXECUTION_AI.md
cp templates/prompts/INTEGRATION_AI.md /path/to/project/prompts/INTEGRATION_AI.md
cp templates/tasks/build/001-bootstrap-project.md /path/to/project/tasks/build/001-bootstrap-project.md
cp templates/tasks/build/EXAMPLE-good-task.md /path/to/project/tasks/build/EXAMPLE-good-task.md
cp templates/tasks/build/NNN-task.md /path/to/project/tasks/build/001-first-task.md
cp templates/reports/PROJECT_STATUS.md /path/to/project/reports/PROJECT_STATUS.md
cp templates/reports/RUN_REPORT.md /path/to/project/reports/RUN_REPORT.md
```

## What The Skill Creates

In a target project, the skill creates or updates:

- `CODEMAP.md`: feature to file and contract lookup.
- `PRD.md`: product goals, scope, roadmap, current decisions, and progress.
- `CONVENTIONS.md`: collaboration, validation, and git rules.
- `ARCHITECTURE.md`: dependency boundaries and ownership.
- `prompts/DISCUSSION_AI.md`: mutable start prompt for planning or discussion agents; the integration agent updates its dynamic handoff state.
- `prompts/EXECUTION_AI.md`: stable start prompt for execution agents; execution details stay in task files.
- `prompts/INTEGRATION_AI.md`: stable start prompt for merging workers and updating shared project state.
- `tasks/build/001-bootstrap-project.md`: first-use task for turning a vague idea into durable project memory before implementation.
- `tasks/build/EXAMPLE-good-task.md`: a compact example of a good execution spec.
- `tasks/build/NNN-short-slug.md`: visible, self-contained execution task specs with checked task-state and explicit Worker authority. Older projects may keep `.tasks/build/`; Hooks recognize both paths.
- `reports/RUN_REPORT.md`: template for immutable task-scoped worker reports.
- `reports/runs/<work-unit-id>.md`: one report per worker or ad-hoc execution.
- `reports/PROJECT_STATUS.md`: current integrated Project Status; Integration AI rewrites it after each integration while history remains in Run Reports and Git.

Optional project-local memory-sync hooks add:

- `.wishgraph/config.json`: enforcement mode and managed memory paths.
- `.wishgraph/hooks/memory_sync.py`: stable checker entrypoint and compatibility facade.
- `.wishgraph/hooks/git_state.py`: Git and repository-state discovery.
- `.wishgraph/hooks/workflow_state.py`: typed parsing for structured and legacy workflow state.
- `.wishgraph/hooks/policy.py`: lifecycle and closeout policy evaluation.
- `.wishgraph/hooks/host_adapter.py`: CLI and host Hook input/output.
- `.codex/hooks.json` and/or `.claude/settings.json`: host lifecycle integration merged without replacing unrelated hooks.

Install them in `warn` mode first:

```bash
python3 skills/wishgraph/scripts/install_project_hooks.py --target /path/to/project --host all --mode warn
```

See [External-Memory Hooks](docs/memory-sync-hooks.md) or [中文说明](docs/memory-sync-hooks.zh-CN.md).

It should not create personal branding content, social media drafts, or project-specific case studies unless the user explicitly asks.

## Collaboration Model

WishGraph separates three runtime roles:

- **Planning / Discussion Agent**: resolves intent, writes self-contained task specs, and does not touch business code.
- **Execution Agent**: reads the task spec as the only source of formal requirements, implements the smallest safe change, runs validation, records evidence in an immutable run report, and proposes project-memory updates without applying them. Explicitly approved ad-hoc edits may omit the task file but use the same closeout.
- **Temporary Integration Agent**: absorbs approved Worker results, verifies the combined state, and is the single writer for shared project memory before ending.

This keeps the project from depending on one long chat window.

The recommended workflow is to start with a planning AI conversation that creates or refines the PRD and architecture frame, then move implementation into task-by-task execution windows.

For a brand-new project, the planning AI starts by asking what idea the user has, then grills one decision at a time until the PRD and first execution task are concrete enough. It then asks whether to create the execution window. After the user explicitly replies with a command such as `创建执行窗口`, the planning AI creates and configures a user-visible Worker task, hands off `prompts/EXECUTION_AI.md` plus the approved task file, and uses a name such as `012 · Auth Refresh · WG Worker` so task identity appears first. A batch command may authorize exactly the listed parallel Workers. No Worker may be created silently or replaced with a hidden subagent; manual copying is only the fallback on platforms without visible task creation.

If the user wants to migrate the discussion window, the planning AI should update `prompts/DISCUSSION_AI.md` and print the full prompt for copying into another agent.

## Debugging Rule

For bugs, do not start with "open the file I remember."

Trace:

```text
Error -> State -> Code -> Spec
```

The goal is not a large patch. The goal is the minimal patch set that repairs the earliest polluted link in the causal chain.

## Status

This is a v0.1 public-beta repository for a reusable Codex skill and project-governance templates.

## License

WishGraph is released under the [PolyForm Noncommercial License 1.0.0](LICENSE).

You may download, study, modify, and redistribute it for personal, educational, charitable, public-interest, or other noncommercial purposes. Commercial use is not permitted without separate written permission from the copyright holder.

This is a source-available noncommercial license, not an OSI open-source license.
