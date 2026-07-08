# WishGraph

**WishGraph / Intent Compilation System** is a reusable Codex skill and template set for turning vague project intent into auditable specs, tasks, code maps, validation evidence, and review reports.

WishGraph is not "let AI write random code." It is a file-backed project operating layer:

```text
Wish -> Spec Graph -> Task Graph -> Code Change -> Probe -> Report -> Human Review
```

The core move is simple: stop depending on chat memory for complex work. Put the project state in durable files that any future agent can read, audit, and continue.

## Use The Skill Directly

Install the Codex skill locally:

```bash
mkdir -p ~/.codex/skills
cp -R skills/wishgraph-project-governor ~/.codex/skills/
```

Then open any project in Codex and ask:

```text
Use $wishgraph-project-governor to start or govern this project with WishGraph. If the project is not framed yet, ask me what idea I have and grill it into a PRD before writing code.
```

The skill is project-neutral. It should inspect the target repository first and adapt the templates to that project instead of imposing this repository's examples.

For the recommended first-use workflow, see [GETTING_STARTED.md](GETTING_STARTED.md).

## Why This Exists

AI coding fails on complex projects less because it cannot write code, and more because it loses context, expands scope, guesses file locations, forgets prior decisions, and leaves humans unable to audit what changed.

WishGraph addresses that by externalizing the working memory:

- **Spec Graph**: what the project is supposed to do.
- **Dependency Map**: which features, modules, interfaces, and files affect each other.
- **Causal Log**: why the project changed, which decisions were made, and what failed before.
- **Probe**: the checks that catch regressions and prove behavior.
- **Review Window**: the compressed human-facing summary of plans, risks, validation, and choices.

The human stays in charge of direction and judgment. AI handles the high-bandwidth translation into specs, tasks, code edits, validation, repair, and reports.

## Repository Contents

```text
wishgraph/
├── README.md
├── GETTING_STARTED.md
├── LICENSE
├── skills/
│   └── wishgraph-project-governor/
├── templates/
│   ├── PRD.md
│   ├── CODEMAP.md
│   ├── CONVENTIONS.md
│   ├── ARCHITECTURE.md
│   ├── prompts/
│   │   ├── DISCUSSION_AI.md
│   │   └── EXECUTION_AI.md
│   ├── .tasks/build/001-bootstrap-project.md
│   ├── .tasks/build/EXAMPLE-good-task.md
│   ├── .tasks/build/NNN-task.md
│   └── reports/DEV_REPORT.md
└── docs/
    ├── wishgraph-method.md
    ├── intent-compiler.md
    └── anti-blackbox-agent-engineering.md
```

## Manual Template Use

If you do not want to install the skill, copy the templates into a project manually:

```bash
cp templates/PRD.md /path/to/project/PRD.md
cp templates/CODEMAP.md /path/to/project/CODEMAP.md
cp templates/CONVENTIONS.md /path/to/project/CONVENTIONS.md
cp templates/ARCHITECTURE.md /path/to/project/ARCHITECTURE.md
mkdir -p /path/to/project/prompts /path/to/project/.tasks/build /path/to/project/reports
cp templates/prompts/DISCUSSION_AI.md /path/to/project/prompts/DISCUSSION_AI.md
cp templates/prompts/EXECUTION_AI.md /path/to/project/prompts/EXECUTION_AI.md
cp templates/.tasks/build/001-bootstrap-project.md /path/to/project/.tasks/build/001-bootstrap-project.md
cp templates/.tasks/build/EXAMPLE-good-task.md /path/to/project/.tasks/build/EXAMPLE-good-task.md
cp templates/.tasks/build/NNN-task.md /path/to/project/.tasks/build/001-first-task.md
cp templates/reports/DEV_REPORT.md /path/to/project/reports/DEV_REPORT.md
```

## What The Skill Creates

In a target project, the skill creates or updates:

- `CODEMAP.md`: feature to file and contract lookup.
- `PRD.md`: product goals, scope, roadmap, current decisions, and progress.
- `CONVENTIONS.md`: collaboration, validation, and git rules.
- `ARCHITECTURE.md`: dependency boundaries and ownership.
- `prompts/DISCUSSION_AI.md`: mutable start prompt for planning or discussion agents; update it after every completed execution task.
- `prompts/EXECUTION_AI.md`: stable start prompt for execution agents; execution details stay in task files.
- `.tasks/build/001-bootstrap-project.md`: first-use task for turning a vague idea into durable project memory before implementation.
- `.tasks/build/EXAMPLE-good-task.md`: a compact example of a good execution spec.
- `.tasks/build/NNN-short-slug.md`: self-contained execution task specs.
- `reports/DEV_REPORT.md`: execution evidence and handoff notes.

It should not create personal branding content, social media drafts, or project-specific case studies unless the user explicitly asks.

## Collaboration Model

WishGraph separates two roles:

- **Planning / Discussion Agent**: resolves intent, writes self-contained task specs, and does not touch business code.
- **Execution Agent**: reads the task spec as the only source of requirements, implements the smallest safe change, runs validation, updates project maps, and reports evidence.

This keeps the project from depending on one long chat window.

The recommended workflow is to start with a planning AI conversation that creates or refines the PRD and architecture frame, then move implementation into task-by-task execution windows.

For a brand-new project, the planning AI starts by asking what idea the user has, then grills one decision at a time until the PRD and first execution task are concrete enough. After that, the user opens a separate execution window and copies `prompts/EXECUTION_AI.md` plus the approved task file.

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

MIT
