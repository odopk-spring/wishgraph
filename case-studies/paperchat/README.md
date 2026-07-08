# PaperChat Case Study

PaperChat is the motivating case for WishGraph: a local iOS dialogue-novel reader that grew complex enough that chat memory was no longer a reliable coordination layer.

This case study is desensitized. It does not include business source code. It shows only governance patterns that can transfer to other projects.

## What Worked

### 1. Code Map As Lookup Table

The project kept a `CODEMAP.md` that mapped product features to modules, files, symbols, status, and contract risks.

This turned "where is the bug?" from a memory game into a lookup operation.

### 2. Planning / Execution Split

The project used two AI roles:

- Planning AI: grill the design and write self-contained task specs.
- Execution AI: read only the task spec, implement, validate, update maps, and commit.

The split reduced scope drift because implementation agents were not asked to redesign while editing.

### 3. Self-Contained Task Files

Task files lived under `.tasks/build/` and included:

- Product summary.
- Anchored files and symbols.
- Implementation notes.
- Validation checklist.
- "Do not do" boundaries.
- Documentation updates.

This made cross-session continuation possible.

### 4. Causal Debugging

When navigation and reading progress bugs appeared, the useful path was not "open the reader view and patch randomly." The project traced:

```text
wrong visual position -> polluted persisted anchor -> async navigation callback -> missing spec guard
```

The fix was a smaller navigation pipeline and write-protection rule, not a full reader rewrite.

## Transferable Lesson

For complex AI-assisted development, the central artifact is not the prompt. It is the project structure that makes future prompts safe.
