# Conventions

## Collaboration Roles

- Discussion AI writes or revises product intent, task specs, and handoff state.
- Execution AI reads the assigned task spec, implements only that task, validates, updates memory files, reports evidence, and commits one atomic change if the repository workflow permits.
- Do not rely on chat memory for project state. Put durable facts in files.

## Execution Rules

- Read `PRD.md`, `ARCHITECTURE.md`, `CODEMAP.md`, `prompts/EXECUTION_AI.md`, and the assigned task before editing code.
- Keep tasks small enough for one commit and one rollback boundary.
- Do not introduce dependencies unless the task spec explicitly allows it.
- Do not convert the static app into a framework app without a new approved task.
- Keep all code project-neutral and public-safe.

## Validation Order

Run:

```bash
node tests/smoke-check.mjs
```

For UI changes, also run a static server:

```bash
python3 -m http.server 4173
```

Then manually check the scenario listed in the task spec.

## Memory Update Rule

Update these files when relevant:

- `PRD.md` for scope, roadmap, user-visible behavior, accepted tradeoffs, and progress.
- `ARCHITECTURE.md` for boundaries, data flow, dependencies, or risk.
- `CODEMAP.md` for feature locations, anchors, contracts, probes, and runtime symptoms.
- `.tasks/build/*.md` for task status and execution notes.
- `reports/DEV_REPORT.md` for validation evidence and handoff.
- `prompts/DISCUSSION_AI.md` for current state, next task, open decisions, and known risks.

If a required update is skipped, explain why in `reports/DEV_REPORT.md`.

## Git Rule

- Prefer one atomic commit per approved task.
- Commit message should state the task outcome in a short imperative or descriptive sentence.
- Do not stage unrelated files.
