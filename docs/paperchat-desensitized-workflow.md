# PaperChat-Style Desensitized Workflow

This document uses a local reading app as a desensitized carrier example for WishGraph. It explains the collaboration workflow, not private product implementation. Do not treat any file names or feature labels here as proprietary source code.

## What This Example Demonstrates

The project is a local-first reader app with multiple moving parts:

- Import plain text or structured content.
- Parse content into user-facing reading units.
- Render those units in a conversational or card-like reader.
- Track reading progress and restore navigation state.
- Let AI agents safely evolve features without losing project context.

This kind of project is a good WishGraph example because UI behavior, parsing rules, persistence, navigation, and performance constraints can easily drift apart if decisions live only in chat history.

## From Zero Idea To PRD

Start in a discussion window with:

```text
Use $wishgraph to start this project.
```

If there is no PRD yet, the discussion AI should ask:

```text
You do not need a full PRD yet. In a few sentences, tell me:
1. What are you trying to build?
2. Who should it serve first?
3. What should they be able to do on the first successful use?
4. What result would make you say v0 is working?
If you are not sure, answer only item 1 and I will fill the rest one decision at a time.
```

Then it should grill one decision at a time:

1. Who is the first user?
2. What content do they import first?
3. What is the first repeated reading workflow?
4. What should the app explicitly not do in v0?
5. What is the smallest end-to-end slice?
6. What command or manual check proves that slice works?
7. Which decisions require explicit human approval before execution?

The output is not code. The output is a first project frame:

```text
PRD.md
ARCHITECTURE.md
CODEMAP.md
CONVENTIONS.md
tasks/001-bootstrap-project.md
reports/PROJECT_STATUS.md
```

## External Memory Shape

### PRD.md

Records product truth:

- target user
- core reading workflow
- goals and non-goals
- first thin slice
- accepted tradeoffs
- roadmap
- open decisions

### ARCHITECTURE.md

Records project boundaries:

- content import layer
- parser or transformation layer
- reading state layer
- UI rendering layer
- persistence layer
- validation and performance constraints

### CODEMAP.md

Acts as the lookup table:

| Area | Example Responsibility | Why It Matters |
|---|---|---|
| Import | Load local text content | Prevent UI tasks from touching import rules by accident |
| Parsing | Convert text into reading units | Bugs often originate in parser assumptions |
| Reader UI | Render units and interactions | UI polish must not silently rewrite state semantics |
| Progress | Track current and furthest positions | Navigation bugs need causal tracing |
| Reports | Store execution evidence | Future agents need validation history |

### Project Status and role rules

Current planning facts stay in Project Status. A new window opens the same project and says `Start discussion`; stable Discussion and Worker rules come from the installed Skill and Host Adapter rather than project-level prompt files.

## Foreground Discussion, Explicit Worker, Temporary Integration

```text
Human idea
-> Discussion AI grills and updates PRD
-> Discussion AI writes a self-contained task spec
-> Discussion AI classifies sequential / parallel_batch / high_risk
-> Human approves task boundary and explicitly authorizes the named Worker task(s)
-> Discussion AI creates and configures user-visible Worker task(s)
-> Worker reads the exact Task file plus the smallest necessary project state
-> Worker implements only that Task
-> Worker validates, writes one immutable Run Report, and commits
-> Discussion-local Integration applies approved results and shared-memory updates
-> Discussion AI presents the integrated result for human review
```

Discussion controls direction and recommends serial or parallel work. After explicit authorization, the active Codex host may create an inspectable Agent thread; Claude Code prefers its managed background Worker when capability checks pass. Failed or unsupported creation outputs only `执行 <task-id> 任务`. WishGraph never creates Workers silently or uses hidden subagents. Every Worker terminal event enters integration evaluation; safe results integrate in a Discussion-local phase, while risk or ambiguity asks only the concrete decision.

## Example First Implementation Task

After bootstrap, a first real task might be:

```text
tasks/002-import-local-text.md
```

A good task spec should include:

- user-visible intent
- current repo facts
- anchored files or planned files
- implementation instructions
- explicit non-goals
- validation commands
- manual checks
- files that must be updated after execution
- work type, batch ID, and future Integration route
- rollback boundary
- report format

It should not say "make the app better" or "implement reader". Those are not executable boundaries.

## Causal Debugging Example

If the reader restores to the wrong position, do not start by guessing a UI file.

Trace:

```text
Error: wrong restored position
-> State: stored progress value or cache entry
-> Code: writer/reader of that state
-> Spec: decision about current vs furthest position
```

The fix should be the minimal patch that repairs the earliest polluted link.

## What Is Deliberately Omitted

This document does not include:

- private product code
- proprietary UI details
- private task history
- app-specific business decisions
- screenshots or user data

Its purpose is to show how WishGraph should structure AI collaboration for a complex project while remaining reusable for other projects.
