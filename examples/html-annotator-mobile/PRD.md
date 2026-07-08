# PRD

## Product Frame

- Project name: Mobile HTML Annotator
- Product purpose: Give mobile users a fast way to mark text inside a local HTML document and export lightweight annotation data.
- Target users: Readers, researchers, editors, and builders reviewing HTML drafts on phone or tablet.
- Current stage: Minimal experiment.
- Primary workflows:
  - Load a sample, local file, or pasted HTML.
  - Select rendered text, or tap a paragraph to stage the whole block.
  - Capture the target and save a note.
  - Review, jump to, delete, copy, or export annotations.

## Goals

- Load and render simple HTML without a build step.
- Let a mobile user create annotations from selected text or a tapped block in under a few taps.
- Export a portable JSON payload containing source, quote, note, and timestamp.
- Demonstrate a complete WishGraph execution loop on a small real app.

## Non-Goals

- Pixel-perfect native iOS or Android shell.
- PDF, EPUB, DOCX, or remote URL ingestion.
- Cross-device sync, user accounts, server storage, or collaboration.
- Exact persistent DOM-range restoration after reload.

## Current Decisions

| Decision | Rationale | Date / Source | Status |
|---|---|---|---|
| Ship as dependency-free mobile web app | Lowest setup cost for a public forward-test; can later become PWA or native wrapper | `001-mobile-html-annotator` | Active |
| Store annotation export as JSON | Portable enough for future import, sync, or review workflows | `001-mobile-html-annotator` | Active |
| Sanitize obvious risky markup before rendering | Local HTML should not execute scripts in the annotator surface | `001-mobile-html-annotator` | Active |
| Use text quote as v0 anchor | Enough for the experiment; exact DOM anchoring can be a later task | `001-mobile-html-annotator` | Active |
| Allow tap-to-stage whole block | Mobile text selection is inconsistent, and whole-block notes keep the quick annotation loop usable | `001-mobile-html-annotator` | Active |

## Roadmap

### Now

- Build the minimal app and record the WishGraph forward-test evidence.

### Next

- Add import of prior annotation JSON and best-effort re-highlighting by quote match.
- Add a share sheet path for exported JSON on mobile browsers that support Web Share.

### Later

- Package as PWA with installable icons and offline cache.
- Explore native iOS wrapper if file access and share extension become important.

## Current Progress

- Last completed task: `001-mobile-html-annotator`.
- Current active task: None.
- Next planned task: Decide whether to add annotation import and re-highlight.
- Known blockers: Exact DOM position persistence is intentionally deferred.

## Acceptance Standards

- Build: no build step; static files must load from `python3 -m http.server`.
- Tests: `node tests/smoke-check.mjs` must pass.
- Manual checks: load sample, tap a paragraph or select text, save note, export JSON.
- Documentation / map updates: update `CODEMAP.md`, task status, `reports/DEV_REPORT.md`, and `prompts/DISCUSSION_AI.md`.
- Release or review criteria: example must stay project-neutral and not include private or personal case-study content.

## Open Questions

| Question | Why It Matters | Recommended Default | Status |
|---|---|---|---|
| Should exact DOM-range persistence be added? | Needed for robust reload/import behavior | Defer until users need import/reopen workflow | Open |
| Should this become native iOS? | Affects file access, share extension, and distribution | Keep web app until interaction value is validated | Open |
