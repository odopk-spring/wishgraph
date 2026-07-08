# CODEMAP

Use this file as the project lookup table. Update it after each execution task.

## Feature To Code Index

| Area | Feature | Files / Modules | Key Symbols / Interfaces | Status | Notes |
|---|---|---|---|---|---|
| App shell | Mobile-first single page UI | `index.html`, `src/styles.css` | `#document-content`, `.workspace`, `.note-pane` | Done | Static app with no build step |
| HTML input | Load sample, file, or pasted HTML | `src/app.js`, `samples/article.html` | `loadHtml`, `parseHtml`, `fileInput`, `pasteButton`, `sampleButton` | Done | Sample fetch falls back to inline HTML |
| Sanitization | Remove obvious risky markup | `src/app.js` | `removeRiskyMarkup` | Done | Not a full security sandbox |
| Annotation capture | Capture selected rendered text or tapped block and note | `src/app.js` | `getCurrentSelection`, `setPendingRange`, `wrapRange`, `createAnnotation` | Done | Quote-based v0 anchor; tap-to-stage fallback |
| Annotation review | List, jump to, and delete annotations | `src/app.js`, `src/styles.css` | `renderAnnotations`, `activateAnnotation`, `deleteAnnotation` | Done | Delete unwraps the highlight |
| Export | Export/copy JSON payload | `src/app.js` | `exportAnnotations`, `copyExport` | Done | Clipboard fallback selects output text |
| Probe | Static smoke check | `tests/smoke-check.mjs` | Required file and anchor assertions | Done | Complements manual UI check |

## Contract Index

| Contract / Type / API | Defined In | Consumers | Change Risk | Validation |
|---|---|---|---|---|
| Annotation JSON shape | `src/app.js` `exportAnnotations` | Users copying/exporting notes | Medium if import is later added | Manual export check; future import tests |
| Rendered document mount | `index.html` `#document-content` | Selection capture and smoke test | High if renamed without map update | `node tests/smoke-check.mjs` |
| Annotation IDs | `src/app.js` `state.nextId`, `data-annotation-id` | Jump/delete/highlight state | Medium | Manual jump/delete check |

## Runtime Debug Map

| Symptom | First Files To Inspect | Logs / Probes | Known False Leads |
|---|---|---|---|
| Sample does not load | `src/app.js` `sampleButton`, `samples/article.html` | Browser console, network tab | Do not debug file input first |
| Selection cannot be captured | `src/app.js` `getCurrentSelection`, `selectionInsideDocument`, tap-to-stage handler | Manual selection or paragraph-tap check | Do not rewrite UI before checking selection containment |
| Export JSON is empty | `src/app.js` `state.annotations`, `exportAnnotations` | Inspect `#export-output` | Do not blame clipboard before checking saved annotations |
| Smoke test fails | `tests/smoke-check.mjs`, renamed anchors | `node tests/smoke-check.mjs` | Do not change app code if only test anchors are stale |

## Maintenance Rule

- Add or update rows when a task changes UI anchors, app state, annotation JSON, persistence, probes, or user-visible workflow.
- If a task changes behavior, update `PRD.md` and `prompts/DISCUSSION_AI.md` in the same task.
