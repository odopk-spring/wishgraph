# WishGraph

**WishGraph / Intent Compilation System** is a practical method for turning low-bandwidth human intent into auditable project specs, tasks, code changes, validation evidence, and review reports.

In Chinese: **许愿式工程系统**. A stricter technical name is **意图编译式自修复项目系统**.

WishGraph is not "let AI write random code." It is a file-backed project operating layer:

```text
Wish -> Spec Graph -> Task Graph -> Code Change -> Probe -> Report -> Human Review
```

The core move is simple: stop depending on chat memory for complex work. Put the project state in durable files that any future agent can read, audit, and continue.

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
├── skills/
│   └── wishgraph-project-governor/
├── templates/
│   ├── CODEMAP.md
│   ├── CONVENTIONS.md
│   ├── ARCHITECTURE.md
│   ├── .tasks/build/NNN-task.md
│   └── reports/DEV_REPORT.md
├── case-studies/
│   └── paperchat/
├── docs/
│   ├── wishgraph-method.md
│   ├── intent-compiler.md
│   └── anti-blackbox-agent-engineering.md
└── social/
    ├── xiaohongshu-cards.md
    └── douyin-script.md
```

## Quick Start

Copy the templates into a project:

```bash
cp templates/CODEMAP.md /path/to/project/CODEMAP.md
cp templates/CONVENTIONS.md /path/to/project/CONVENTIONS.md
cp templates/ARCHITECTURE.md /path/to/project/ARCHITECTURE.md
mkdir -p /path/to/project/.tasks/build /path/to/project/reports
cp templates/.tasks/build/NNN-task.md /path/to/project/.tasks/build/001-first-task.md
cp templates/reports/DEV_REPORT.md /path/to/project/reports/DEV_REPORT.md
```

Install the Codex skill locally:

```bash
mkdir -p ~/.codex/skills
cp -R skills/wishgraph-project-governor ~/.codex/skills/
```

Then ask Codex:

```text
Use $wishgraph-project-governor to set up an auditable AI collaboration system for this project.
```

## The Collaboration Model

WishGraph separates two roles:

- **Planning / Discussion Agent**: grills the intent, resolves ambiguity, writes self-contained task specs, and does not touch business code.
- **Execution Agent**: reads the task spec as the only source of requirements, implements the smallest safe change, runs validation, updates project maps, and reports evidence.

This keeps the project from depending on one long chat window.

## Debugging Rule

For bugs, do not start with "open the file I remember."

Trace:

```text
Error -> State -> Code -> Spec
```

The goal is not a large patch. The goal is the minimal patch set that repairs the earliest polluted link in the causal chain.

## Status

This is a v1 method repository. It includes a reusable Codex skill, governance templates, a desensitized PaperChat case study, and content drafts for public writing.

Before public GitHub release, choose a license and decide whether to publish under your personal account or an organization.
