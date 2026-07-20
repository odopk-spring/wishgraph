# Project Bootstrap, Layout, And Language

Use this reference when starting from a vague idea, adapting an existing repository, selecting templates, setting Chinese/English/bilingual output, or continuing Discussion in another window or host.

## Contents

- Reuse and language mode
- First intake and grill loop
- Project-state graph and templates
- Existing-project adoption
- Project Status migration
- Cross-window and cross-host continuation

## Reuse Before Creating

Inspect README files, product specs, architecture notes, task folders, tests, CI, ownership rules, and status documents. Finding a document does not make it authoritative. For only the facts needed by the current Task, check:

1. The responsibility the document actually performs.
2. Whether referenced paths and key symbols exist.
3. Whether important build and test commands are available.
4. Whether it obviously conflicts with code or another core document.
5. Whether it is sufficient for the current Task and marks unknown facts explicitly.

Default existing repositories to **native-lite** adoption. Choose one simple outcome: reuse the native source, reuse it while recording the current gap in the Task, or create the smallest missing entry/index when no source can perform the responsibility. `Reuse`, `Adapt`, and `Bridge` may describe this judgment in discussion, but never persist them as document trust state.

Do not replace or delete a user's existing document without explicit confirmation. Do not create two competing sources for one concept.

The first usable entry should stay human-visible and small: add a short WishGraph section to the existing root README stating that the project has explicitly opted in, with links to Project Status and the three post-activation commands `开始讨论`, `刷新项目状态`, and `执行 NNN 任务`. Do not create a second landing-page document. If no README exists, create one concise README rather than a WishGraph-specific manual.

## Language Mode

Record the primary language and any bilingual requirement in the current Task or Project Status when it affects delivery. Follow the user's language by default. For bilingual output, write important decisions, summaries, and Task explanations Chinese-first, then English.

Never translate file paths, commands, code identifiers, symbols, routes, package names, environment variables, or literal API names. Avoid duplicating long context in two languages; use short paired summaries.

## First Intake

Treat the first conversation as Discussion, not implementation. For a vague or empty project, ask:

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

Ask both when bilingual mode is explicit. Otherwise ask only in the selected language.

## Grill Loop

Ask one decision at a time, recommend a default, and skip facts already established by the repository or user:

1. Product outcome.
2. First target user.
3. Core repeated workflow.
4. Platform, cost, privacy, and latency constraints.
5. v0 non-goals.
6. First useful end-to-end slice.
7. User-visible acceptance.
8. Build, test, and manual validation.
9. Decisions requiring explicit human authority.

Use:

```text
问题 N / Question N: <one concrete decision>
推荐 / Recommended default: <default>
原因 / Reason: <one sentence>
```

Do not turn the first interaction into a long questionnaire.

## Project-State Graph

For a blank project, create the full graph as it becomes useful:

```text
PRD.md
ARCHITECTURE.md
CODEMAP.md
CONVENTIONS.md
tasks/001-bootstrap-project.md
tasks/revisions/                 # create only when first needed
reports/PROJECT_STATUS.md
reports/runs/
```

These are WishGraph defaults, not a root-directory allowlist. Preserve user-owned files such as `AGENTS.md`, `CLAUDE.md`, framework configuration, and any native project layout. WishGraph constrains only the files it creates.

For an existing project, create runtime artifacts lazily:

1. Immediately add only the current `reports/PROJECT_STATUS.md` snapshot needed to enter the loop.
2. Reuse native product, architecture, code-map, conventions, Task, and validation sources when they are authoritative; record their paths in Task context instead of cloning their contents.
3. Create `tasks/`, `tasks/revisions/`, and `reports/runs/` only when the first corresponding work unit needs them. Do not copy a Run Report placeholder into the project.
4. Coalesce additional feedback into a pending or running Revision instead of allocating another Revision file. Allocate a new Revision only after the prior one is terminal and integrated.

Native-lite must preserve the same Claim, role, validation, closeout, and semantic-sync gates. It reduces duplicate files; it does not weaken governance.

Native-lite readiness belongs to the current Task, not to a global documentation score. A Task is ready when its intended result, scope and Do Not Do boundary, real code anchors, executable validation, permission/risk boundary, and blocking unknowns are explicit. The goal is reliable facts for this Task, not perfect documentation for the whole project.

Stable role rules come from the installed Skill and Host Adapter. Put work-specific instructions in Tasks or Revisions. Current user-readable state belongs only in `reports/PROJECT_STATUS.md`; do not create project-level prompt files.

## Template Mapping

Use root assets for English/language-neutral projects and `zh-CN` mirrors for Chinese-first projects. Copy either set to the same target paths.

| Purpose | Root asset | Chinese mirror | Target |
| --- | --- | --- | --- |
| Product | `assets/templates/PRD.md` | `assets/templates/zh-CN/PRD.md` | `PRD.md` |
| Architecture | `assets/templates/ARCHITECTURE.md` | `assets/templates/zh-CN/ARCHITECTURE.md` | `ARCHITECTURE.md` |
| Code map | `assets/templates/CODEMAP.md` | `assets/templates/zh-CN/CODEMAP.md` | `CODEMAP.md` |
| Conventions | `assets/templates/CONVENTIONS.md` | `assets/templates/zh-CN/CONVENTIONS.md` | `CONVENTIONS.md` |
| Bootstrap Task | `assets/templates/001-bootstrap-project.md` | `assets/templates/zh-CN/tasks/build/001-bootstrap-project.md` | `tasks/001-bootstrap-project.md` |
| Formal Task | `assets/templates/NNN-task.md` | `assets/templates/zh-CN/tasks/build/NNN-task.md` | `tasks/NNN-short-slug.md` |
| Revision | `assets/templates/TASK_REVISION.md` | `assets/templates/zh-CN/tasks/revisions/TASK_REVISION.md` | `tasks/revisions/NNN-rN.md` |
| Project status | `assets/templates/PROJECT_STATUS.md` | `assets/templates/zh-CN/reports/PROJECT_STATUS.md` | `reports/PROJECT_STATUS.md` |
| Run report source | `assets/templates/RUN_REPORT.md` | `assets/templates/zh-CN/reports/RUN_REPORT.md` | Generate `reports/runs/<work-unit-id>-attempt-N.md` only when needed |

Adapt placeholders to repository facts. Do not inject creator-specific private content, social drafts, or source-project domain rules.

## Existing-Project Adoption

1. Identify authoritative product and architecture files.
2. Add only the missing state files required by the current Task.
3. Create one bounded Task and unique Run Report path.
4. Install Hooks in `warn` and complete one closeout.
5. Move to `enforce` only when the worktree and project state are clean.

Use `tasks/*.md` for formal Tasks and `tasks/revisions/*.md` for Revisions. Do not infer hidden or alternate Task directories.

## Cross-Window And Cross-Host Continuation

Do not make the user copy a full Discussion prompt or previous chat as a normal handoff.

Before the current Discussion ends, keep `reports/PROJECT_STATUS.md` accurate. A new supported window in the same Git project says `开始讨论` / `Start discussion`; an already active Discussion says `刷新项目状态` / `Refresh project status`.

When switching hosts, preserve project files, Tasks, reports, Claims, and integrated state. Require the destination host to be selected in `required_hosts`; otherwise explicitly enable and install it before reopening the session. Never route a Codex thread ID to Claude or a Claude session ID to Codex; the new host establishes its own valid Worker binding before execution.

## Project Status Migration

Use `reports/PROJECT_STATUS.md` as the current snapshot.

- If a pre-release WishGraph layout is detected, explain the unsupported paths and reactivate or migrate them explicitly before execution. Do not silently treat two formats as one truth source.
- If both exist, stop and ask which is authoritative.
- Keep current facts, unresolved risk, pending decisions, latest absorbed reports, and next action.
- Keep detailed history in immutable Run Reports and Git.

## Bootstrap Completion

Stop grilling and prepare Worker authorization only when the first Task has concrete intent, scope, validation, rollback, architecture ownership, and a unique next transition. If the user wants more discussion, keep Project Status current instead of launching work.

## Discussion-Window Migration

When the user asks to continue the Discussion elsewhere, first refresh current project facts in `reports/PROJECT_STATUS.md`. The new supported window opens the same Git project and says `开始讨论` / `Start discussion`; do not create or copy a project-level prompt.
