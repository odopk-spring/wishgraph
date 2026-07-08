# PaperChat Task Spec Excerpt

This is a generalized excerpt from the PaperChat workflow. It shows structure, not source code.

```markdown
# 015j - Reader Navigation Pipeline

Status: Completed
Spec source: Reader progress and non-linear navigation behavior.
Dependencies: Windowed rendering, persistent cache, progress save policy.

## Intent

All navigation entry points must restore or jump to the intended content anchor without polluting the user's continue-reading bookmark.

## Current State

Async chapter loading, cache misses, and fallback scroll behavior can race. A failed restore may write a temporary chapter-start position back into persistent progress.

## Change Set

| Target | Anchor | Required Change |
|---|---|---|
| Reader view | `navigate(to:reason:)` | Route all restore, chapter jump, and progress-bar jump actions through one navigation pipeline |
| Navigation state | `NavigationToken` | Ignore stale async callbacks |
| Persistence | progress save gate | Disable bookmark writes while navigation is pending |

## Do Not Do

- Do not render the entire book to avoid timing issues.
- Do not change data schema.
- Do not broaden the feature into search or bookmarks.

## Validation

- Open and close reader three times; position remains stable.
- Jump to a far chapter; continue-reading bookmark is unchanged.
- Simulate cache miss; fallback does not overwrite progress.
- Update CODEMAP.
```

The important part is the causal boundary: async navigation and persistence were specified together, so the execution agent could fix the chain without expanding scope.
