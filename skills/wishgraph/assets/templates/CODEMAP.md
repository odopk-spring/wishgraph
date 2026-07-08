# CODEMAP

Use this file as the project lookup table. A future agent should be able to locate the right feature, module, files, symbols, tests, and current state without scanning the whole repository.

Update this file after every completed execution task.

## Feature To Code Index

| Area | Feature | Files / Modules | Key Symbols / Interfaces | Status | Notes |
|---|---|---|---|---|---|
| Example | User-facing behavior | `src/example.*` | `ExampleService`, `ExampleView` | Not started / Partial / Done | Add verification or caveats |

## Contract Index

| Contract / Type / API | Defined In | Consumers | Change Risk | Validation |
|---|---|---|---|---|
| ExampleContract | `src/contracts/example.*` | `src/features/*` | Breaking changes require task spec | `npm test` |

## Runtime Debug Map

| Symptom | First Files To Inspect | Logs / Probes | Known False Leads |
|---|---|---|---|
| Example bug | `src/example.*` | `ExampleProbe`, CI test name | Do not patch UI before checking state |

## Maintenance Rule

- Add new rows when a task introduces a feature, module, public interface, persistent field, job, probe, or test surface.
- Keep rows short and operational. Link to deeper docs when details exceed one paragraph.
- Mark uncertainty explicitly. A stale code map is worse than a sparse one.
