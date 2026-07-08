# ARCHITECTURE

Use this file to describe the dependency boundaries that agents must preserve.

## System Shape

```text
project/
├── app-or-entrypoints/
├── features/
├── core/
├── services/
├── contracts/
├── tests/
└── docs/
```

Replace this sketch with the target project's real modules.

## Dependency Rules

| Layer | May Depend On | Must Not Depend On |
|---|---|---|
| Entry points | Features, services, configuration | Business logic inline |
| Features | Core contracts, services, UI/design system | Storage internals, unrelated features |
| Core | Contracts, pure models | UI, network, filesystem side effects |
| Services | Models, external APIs, storage | Feature-specific UI |
| Contracts | Nothing or pure shared types | Concrete implementations |

## Ownership Boundaries

| Boundary | Owner / Source Of Truth | Notes |
|---|---|---|
| Product behavior | Product spec / task files | Keep requirements out of execution chat memory |
| Public APIs | Contracts / schema docs | Breaking changes need an explicit task |
| Persistence | Schema / migration docs | Record compatibility and rollback |
| Validation | Tests / probes / CI | Every risky change needs a check |

## Architecture Review Checklist

- Does the change preserve dependency direction?
- Does it introduce a new public contract?
- Does it require migration or rollback notes?
- Does it add hidden state that future agents will miss?
- Is the validation surface recorded in `CODEMAP.md`?
