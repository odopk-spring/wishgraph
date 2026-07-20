# CODEMAP

Use this file as a sparse, operational index. Every path and symbol must be real. Mark uncertain entries `Unverified`; delete stale guidance rather than preserving a misleading map.

## Feature To Code Index

| Feature | Files / Modules | Key Symbols / Interfaces | Validation Entry | Status |
|---|---|---|---|---|
| Example behavior | `src/example.*` | `ExampleService` | `tests/example.*` | Verified / Unverified |

## Maintenance Rules

- Add or update a row only when it helps locate current code, contracts, or validation.
- Verify paths and symbols against the repository before marking an entry `Verified`.
- Keep uncertainty explicit and the map sparse.
- Link to architecture or product documentation instead of copying long explanations.
