# Architecture

## System Shape

Mobile HTML Annotator is a static browser app:

```text
index.html
-> src/app.js
-> DOMParser sanitization
-> rendered document pane
-> selection capture
-> annotation state
-> JSON export
```

There is no server, build step, package manager, database, or backend API in v0.

## Boundaries

- `index.html` owns the stable UI anchors and accessible control structure.
- `src/styles.css` owns responsive layout and visual states.
- `src/app.js` owns loading, sanitization, selection capture, annotation state, persistence, and export.
- `samples/article.html` is test content only.
- `tests/smoke-check.mjs` is a lightweight probe for file presence and critical app anchors.

## Data Flow

1. User loads sample, file, or pasted HTML.
2. App parses HTML with `DOMParser`.
3. App removes obvious risky markup and event handler attributes.
4. App renders sanitized body HTML into `#document-content`.
5. User selects text and captures the current selection range, or taps a block to stage the whole block.
6. User saves a note.
7. App wraps the selected range in a local highlight and stores annotation metadata.
8. User exports annotations as JSON.

## Dependency Rules

- Keep the app dependency-free unless a future task proves a library is necessary.
- Do not introduce a framework for this experiment.
- Keep tests runnable with built-in Node.js modules.
- Do not add backend or account assumptions to frontend code.

## Risk Notes

- Selection range wrapping can fail for some complex nested selections; current fallback uses `extractContents` and `insertNode`.
- Tap-to-stage creates a range around the full block, which is more stable on mobile than pointer-drag selection.
- Reload persistence keeps annotation metadata but does not reconstruct highlights yet.
- Sanitization is only a small local safety guard, not a full HTML security sandbox.
- Mobile browser selection behavior varies; manual phone testing is required before claiming production readiness.
