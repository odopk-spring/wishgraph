# Wish-Driven Engineering: The WishGraph Method

## One Sentence

State an intent, compile it into an execution spec, execute it, report the result, then state the next intent.

WishGraph is a complex-project engineering system driven by low-bandwidth human intent. AI compiles that intent into requirements, project structure, code changes, validation, causal traces, repair steps, and review summaries for human judgment.

The human does not need to describe every implementation detail. The human gives direction, preferences, constraints, and evaluation. AI expands that low-bandwidth signal into executable specifications, while the project stores durable external memory so future agents do not depend on one chat window.

## 1. Humans Move From Implementers To Reviewers

Traditional development asks humans to know how to split requirements, which files to edit, how to debug, and how to avoid breaking the whole system.

In WishGraph, humans mainly do two things:

- Express intent: "make this page smoother", "make this chat feel more human", "do not make it too complex", "I dislike this result".
- Evaluate output: "approved", "wrong", "the direction is off", "continue optimizing", "I accept this risk".

Humans no longer manage every implementation detail. They manage direction, taste, risk, and final judgment.

## 2. AI Becomes A Project Operating Layer

A normal agent loop is:

```text
Natural language -> Do one task -> Return result
```

WishGraph is:

```text
Natural language -> Spec -> Task -> Code -> Verify -> Repair -> Log -> Report -> Human Review
```

AI acts as requirements engineer, architect, implementer, tester, debugger, documentation maintainer, and project reporter.

The point is not to ask AI to jump from one vague wish to a finished world. The point is to build a structure that lets AI move through many small, stable steps.

## 3. Replace Chat Context With External Project Structure

AI context windows are limited. A complex project should not store its memory in a chat transcript. It should store memory in project files.

WishGraph external memory includes:

- Spec Graph: what the project should be.
- Dependency Map: how modules and features depend on each other.
- Causal Log: why the project changed.
- Probe: how the project checks itself and detects regressions.
- Review Window: the compressed state humans need to see.

When the session, model, or agent changes, a new agent can continue by reading these files.

## 4. Anti-Black-Box Principle

AI is a black box, and an unfamiliar project folder can also become a black box.

The way out is to improve the inputs and outputs around the black box, and to separate planning from execution. Do not let an AI black box freely mutate a larger project black box.

A good execution spec forces the agent to understand the intent, change the right files, and avoid unrelated surfaces.

Every execution should answer:

- What human intent did it infer?
- What specs did it compile?
- Why are only these files in scope?
- What risks exist?
- How will it validate?
- Did validation pass?
- If it failed, where did the error propagate from?

This is not ceremony. It is how humans review the work and how future agents inherit it.

## 5. Debug By Causality, Not Guessing Files

Traditional debugging often becomes:

```text
The page is wrong -> Try a patch in a familiar View file
```

WishGraph requires:

```text
Error -> State -> Code -> Spec
```

Start with the symptom, find the wrong state, identify the code path that wrote or read it, then return to the spec to decide what the behavior should be.

The goal is a minimal patch set, not a broad rewrite.

## 6. The Ideal Human Review Window

The ideal product experience is not making humans copy text across many windows. The human should face one review window.

It shows:

- The AI's understanding of the request.
- The plan before execution.
- The summary after execution.
- Risks and validation results.
- Choices that need human judgment.

Many agents, tasks, logs, and code changes can exist behind it, but the human sees a compressed, understandable project state.

## 7. Larger Claim

Computer abstraction keeps moving upward:

```text
Binary -> Assembly -> C -> High-level languages -> GUI -> Natural-language agents
```

New layers do not delete old layers. They push them downward.

WishGraph is not the final form, but it describes a next engineering interface: humans express goals in natural language, while AI maintains a software world that is explainable, repairable, and able to grow.
