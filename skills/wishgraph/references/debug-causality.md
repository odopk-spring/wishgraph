# Causal Debugging

WishGraph debugging traces failure backward:

```text
Error -> State -> Code -> Spec
```

## 1. Error

Capture the observable symptom:

- What did the user see?
- What command failed?
- What assertion broke?
- Is it deterministic?

## 2. State

Find the state that produced the error:

- Runtime state.
- Persisted data.
- Cache entries.
- Feature flags.
- Derived data.
- Navigation or job state.

## 3. Code

Map the state transition to code:

- Which module writes the state?
- Which module reads it?
- Is there a stale callback, race, cache invalidation issue, or fallback path?
- Does `CODEMAP.md` list the dependency?

## 4. Spec

Find whether the code violated the spec or the spec was incomplete:

- Was the behavior specified?
- Did two specs conflict?
- Did a task omit a validation case?
- Was a "do not do" boundary missing?

## Minimal Patch Set

Fix the earliest polluted link. Avoid broad rewrites unless the causal chain shows the abstraction itself is broken.

## Report

State:

- Root cause.
- Minimal fix.
- Validation.
- Why the patch does not expand behavior.
