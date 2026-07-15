# Project Bootstrap, Layout, And Language

Use this reference when starting from a vague idea, adapting an existing repository, selecting templates, setting Chinese/English/bilingual output, or migrating the Discussion handoff.

## Contents

- Reuse and language mode
- First intake and grill loop
- Project-state graph and templates
- Existing-project adoption
- Project Status migration
- Discussion-window migration

## Reuse Before Creating

Inspect README files, product specs, architecture notes, task folders, tests, CI, ownership rules, and status documents. Reuse a native file when it already carries the same truth. Do not create two competing sources for one concept.

Map existing artifacts to product intent, architecture boundaries, feature-to-code lookup, conventions, Discussion/Worker handoffs, executable Tasks, immutable evidence, and current integrated status.

Default existing repositories to **native-lite** adoption. Reuse their README, product spec, architecture notes, code map, conventions, issue/task system, and validation commands. Create a WishGraph file only when no native source can carry that truth without ambiguity.

The first usable entry should stay human-visible and small: add a short WishGraph section to the existing root README with links to Project Status and the three commands `开始讨论`, `刷新项目状态`, and `执行 NNN 任务`. Do not create a second landing-page document. If no README exists, create one concise README rather than a WishGraph-specific manual.

## Language Mode

Record the primary language and whether bilingual output is required in `prompts/DISCUSSION_AI.md`. Follow the user's language by default. For bilingual output, write important prompts, decisions, summaries, and Task explanations Chinese-first, then English.

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
prompts/DISCUSSION_AI.md
prompts/EXECUTION_AI.md
prompts/INTEGRATION_AI.md
tasks/build/001-bootstrap-project.md
tasks/revisions/                 # create only when first needed
reports/PROJECT_STATUS.md
reports/RUN_REPORT.md
reports/runs/
```

For an existing project, create runtime artifacts lazily:

1. Immediately add only the missing Discussion/Worker entry prompts and current `reports/PROJECT_STATUS.md` snapshot needed to enter the loop.
2. Reuse native product, architecture, code-map, conventions, Task, and validation sources when they are authoritative; record their paths in Task context instead of cloning their contents.
3. Create `tasks/build/`, `tasks/revisions/`, report templates, and `reports/runs/` only when the first corresponding work unit is approved.
4. Coalesce additional feedback into a pending or running Revision instead of allocating another Revision file. Allocate a new Revision only after the prior one is terminal and integrated.

Native-lite must preserve the same Claim, role, validation, closeout, and semantic-sync gates. It reduces duplicate files; it does not weaken governance.

Keep `prompts/EXECUTION_AI.md` stable and put work-specific instructions in Tasks or Revisions. Keep only concise current state in the dynamic block of `prompts/DISCUSSION_AI.md`.

## Template Mapping

Use root assets for English/language-neutral projects and `zh-CN` mirrors for Chinese-first projects. Copy either set to the same target paths.

| Purpose | Root asset | Chinese mirror | Target |
| --- | --- | --- | --- |
| Product | `assets/templates/PRD.md` | `assets/templates/zh-CN/PRD.md` | `PRD.md` |
| Architecture | `assets/templates/ARCHITECTURE.md` | `assets/templates/zh-CN/ARCHITECTURE.md` | `ARCHITECTURE.md` |
| Code map | `assets/templates/CODEMAP.md` | `assets/templates/zh-CN/CODEMAP.md` | `CODEMAP.md` |
| Conventions | `assets/templates/CONVENTIONS.md` | `assets/templates/zh-CN/CONVENTIONS.md` | `CONVENTIONS.md` |
| Discussion | `assets/templates/DISCUSSION_AI.md` | `assets/templates/zh-CN/prompts/DISCUSSION_AI.md` | `prompts/DISCUSSION_AI.md` |
| Worker | `assets/templates/EXECUTION_AI.md` | `assets/templates/zh-CN/prompts/EXECUTION_AI.md` | `prompts/EXECUTION_AI.md` |
| Integration | `assets/templates/INTEGRATION_AI.md` | `assets/templates/zh-CN/prompts/INTEGRATION_AI.md` | `prompts/INTEGRATION_AI.md` |
| Bootstrap Task | `assets/templates/001-bootstrap-project.md` | `assets/templates/zh-CN/tasks/build/001-bootstrap-project.md` | `tasks/build/001-bootstrap-project.md` |
| Formal Task | `assets/templates/NNN-task.md` | `assets/templates/zh-CN/tasks/build/NNN-task.md` | `tasks/build/NNN-short-slug.md` |
| Revision | `assets/templates/TASK_REVISION.md` | `assets/templates/zh-CN/tasks/revisions/TASK_REVISION.md` | `tasks/revisions/NNN-rN.md` |
| Project status | `assets/templates/PROJECT_STATUS.md` | `assets/templates/zh-CN/reports/PROJECT_STATUS.md` | `reports/PROJECT_STATUS.md` |
| Run report | `assets/templates/RUN_REPORT.md` | `assets/templates/zh-CN/reports/RUN_REPORT.md` | `reports/RUN_REPORT.md` |

Adapt placeholders to repository facts. Do not inject creator-specific private content, social drafts, or source-project domain rules.

## Existing-Project Adoption

1. Identify authoritative product and architecture files.
2. Add only missing state and role files.
3. Create one bounded Task and unique Run Report path.
4. Install Hooks in `warn` and complete one closeout.
5. Move to `enforce` only when the worktree and project state are clean.

Do not rename native task folders for aesthetics. New projects use `tasks/build/*.md`; legacy `.tasks/build/*.md` remains supported.

## Project Status Migration

Use `reports/PROJECT_STATUS.md` as the current snapshot.

- If only `reports/DEV_REPORT.md` exists, read it and Git state, use `git mv`, and update references.
- If both exist, stop and ask which is authoritative.
- Keep current facts, unresolved risk, pending decisions, latest absorbed reports, and next action.
- Keep detailed history in immutable Run Reports and Git.

## Bootstrap Completion

Stop grilling and prepare Worker authorization only when the first Task has concrete intent, scope, validation, rollback, architecture ownership, and a unique next transition. If the user wants more discussion, keep the handoff current instead of launching work.

## Discussion-Window Migration

When the user asks to migrate or copy the Discussion:

1. Refresh current project facts and `prompts/DISCUSSION_AI.md`.
2. Output the full prompt in a fenced code block.
3. Prepend one short copy instruction.

Do not replace the copyable prompt with a summary unless the user requests one.
