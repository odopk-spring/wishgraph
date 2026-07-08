# Mobile HTML Annotator

This is a small forward-test project for WishGraph. It shows how a vague product intent can become a runnable app plus external project memory.

The app is a dependency-free mobile web app for quick annotation of HTML files:

- Load a local `.html` file, paste HTML, or open the bundled sample.
- Select text in the rendered document, or tap a paragraph to stage the whole block.
- Capture the selection, add a note, and keep a highlight in the preview.
- Export annotations as JSON for later processing.

## Run

From this folder:

```bash
python3 -m http.server 4173
```

Open:

```text
http://127.0.0.1:4173/
```

The app has no build step and no package install.

## WishGraph Files

This example includes the same governance shape the skill should create in a target project:

- `PRD.md`
- `ARCHITECTURE.md`
- `CODEMAP.md`
- `CONVENTIONS.md`
- `prompts/DISCUSSION_AI.md`
- `prompts/EXECUTION_AI.md`
- `.tasks/build/001-mobile-html-annotator.md`
- `reports/DEV_REPORT.md`

Use these files as a compact example of how a real task moves from intent to execution evidence.

## Validate

```bash
node tests/smoke-check.mjs
python3 -m http.server 4173
```

Then manually check:

1. Open the sample document.
2. Select text in the article, or tap a paragraph to stage the whole block.
3. Capture the selection if using selected text.
4. Save a note.
5. Export JSON and confirm the note contains the selected quote.
