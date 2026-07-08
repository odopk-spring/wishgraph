# Intent Compiler

Intent Compiler is the engineering side of WishGraph.

It converts vague human wishes into structured artifacts that can be implemented, tested, reviewed, and resumed.

## Input

Human input is low bandwidth:

- Natural language.
- Voice.
- Screenshots.
- Video.
- Screen state.
- Behavior traces.
- "This feels wrong."

The compiler should not expect the human to provide full specs. It should extract intent, ask targeted questions, and turn ambiguity into explicit assumptions.

## Compilation Stages

```text
Wish
-> Intent
-> Acceptance criteria
-> Spec Graph update
-> Task Graph update
-> Execution task
-> Patch
-> Probe result
-> Review summary
```

## Required Artifacts

### Intent Record

What the user wants, in plain language.

### Spec Delta

What project truth changes, if any.

### Task Spec

The executable unit for an implementation agent.

### Probe Plan

The validation surface: tests, builds, screenshots, logs, metrics, or manual checks.

### Review Report

The compressed result for the human.

## Compiler Failure Modes

- Treating vague intent as permission to invent scope.
- Writing implementation before clarifying success criteria.
- Depending on chat context instead of task files.
- Omitting validation.
- Hiding uncertainty.
- Failing to update project maps after execution.

## Principle

The compiler is successful when another agent can continue the project without the original conversation.
