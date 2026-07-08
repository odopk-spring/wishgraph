# 001 - Mobile HTML Annotator minimal experiment

Status: Done
Spec source: User asked for a minimal app-form experiment for quick annotation of HTML files on mobile.
Dependencies: None.

## Intent

Create a smallest useful app that lets a phone or tablet user load an HTML document, select text or tap a block in the rendered document, save a short annotation, and export the annotations as JSON.

This task also acts as a WishGraph forward-test: the example must include external memory files, a task spec, validation evidence, and a handoff report.

## Current State

- The WishGraph repository already contains a reusable skill and templates.
- No example app existed before this task.
- The target should be public, project-neutral, and dependency-free.

## Change Set

| Target | Anchor | Required Change |
|---|---|---|
| `examples/html-annotator-mobile/index.html` | App shell and stable DOM IDs | Add mobile-first UI for loading HTML, reading content, capturing notes, listing annotations, and exporting JSON. |
| `examples/html-annotator-mobile/src/styles.css` | Responsive layout | Add readable mobile/desktop layout, selection highlight style, and fixed annotation controls. |
| `examples/html-annotator-mobile/src/app.js` | App behavior | Implement HTML loading, basic sanitization, selection capture, tap-to-stage block fallback, note save, list/jump/delete, local persistence, and JSON export. |
| `examples/html-annotator-mobile/samples/article.html` | Sample content | Add a tiny sample HTML document for manual testing. |
| `examples/html-annotator-mobile/tests/smoke-check.mjs` | Probe | Add a dependency-free smoke check for critical files, anchors, and report evidence. |
| `examples/html-annotator-mobile/*.md` | External memory | Add PRD, architecture, code map, conventions, prompts, task spec, and Dev Report. |
| Top-level `README.md` | Repository map | Link the example as the first forward-tested sample. |

## Implementation Notes

- Use plain HTML, CSS, and JavaScript.
- Keep the app runnable with `python3 -m http.server`.
- Render simple sanitized HTML into the document pane.
- Store annotation metadata as `{ id, sourceName, quote, note, createdAt }`.
- If exact pointer selection is unavailable, allow tapping a paragraph or heading to stage that block for annotation.
- Preserve the no-build-step property.

## Do Not Do

- Do not create a native iOS or Android project in this task.
- Do not add React, Vite, npm dependencies, a backend, accounts, or sync.
- Do not claim production-grade HTML sanitization.
- Do not implement robust DOM-range import/reload.
- Do not include personal case-study or social-media content.

## Validation

- [x] `node tests/smoke-check.mjs`
- [x] `python3 -m http.server 4173`
- [x] Manual check: open sample, tap a paragraph, save note, export JSON.
- [x] `PRD.md` updated.
- [x] `ARCHITECTURE.md` updated.
- [x] `CODEMAP.md` updated.
- [x] `reports/DEV_REPORT.md` updated.
- [x] `prompts/DISCUSSION_AI.md` updated.
- [x] One atomic commit prepared for this task.

## Rollback Boundary

Revert the single commit for this task to remove the example app and its WishGraph evidence.

## Execution Report Requirements

Report changed files, validation commands, manual check result, memory updates, commit hash, and remaining risks.
