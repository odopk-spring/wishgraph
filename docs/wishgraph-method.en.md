# The WishGraph Method: A Project Interface Between Two Black Boxes

[English](wishgraph-method.en.md) | [简体中文](wishgraph-method.md)

## 1. Why stronger models can make projects harder to understand

A coding agent can change a thousand lines in minutes. Human understanding, impact review, and project-state verification have not accelerated at the same rate.

A small request can travel from a page animation into request state, caching, navigation, and persistence. Every local edit may be reasonable while the project as a whole becomes harder to explain:

- What behavior changed?
- Did another module move with it?
- Are earlier constraints still true?
- Can a new window or model tell where the project is now?

The model is not fully predictable. Once most of a project is AI-generated, its structure, historical decisions, and implicit constraints can also become opaque to the human. Letting one hard-to-predict system directly manage another increasingly opaque system creates a structural control problem, not just an occasional model mistake.

## 2. Natural language needs a project interface

Humans speak in experiences: “make the animation feel natural,” “this color is wrong,” or “do not show a loading flash.” The agent touches a software system.

Natural language is low-bandwidth, ambiguous, and changeable. The problem is not using natural language for development. The problem is letting uncompiled natural language receive authority over an entire codebase.

WishGraph inserts a project interface:

```text
Wish → Requirements → Spec → Task → Worker → Validation → Report → Current State
```

The user does not need to become a requirements engineer. Discussion turns the wish into work that can be executed, validated, and rolled back. A Worker executes only that work. Integration writes the verified result back into current project state.

## 3. Compress project rules instead of memorizing answers

When an agent reopens the project by rereading chat, rescanning code, and guessing why earlier changes happened, it is memorizing an ever-growing answer sheet.

A better approach extracts the rules:

- What problem the project solves.
- Which modules exist and how they connect.
- Which data source is authoritative.
- What this change may and may not touch.
- What proves the work is complete.
- Which project facts must change afterward.

These rules are smaller than the complete chat and codebase but support better reasoning. The project is still complex; the agent simply no longer starts its understanding from line one every time.

WishGraph stores this compression in several views:

- **Spec Graph:** what the project should be.
- **Dependency Map:** how features, modules, files, contracts, and validation connect.
- **Task Graph:** bounded, ordered, reversible execution units.
- **Causal Log:** why the project changed, including decisions, reports, failures, and repairs.
- **Current State:** the compact snapshot a human or new agent needs first.

## 4. A closed project loop

The ordinary loop is short:

```text
Discuss → Authorize → Execute → Validate → Integrate → Present → Discuss again
```

### Discussion: make the intent clear

The user still speaks naturally. Discussion uses current project state to ask only material questions, then writes a Task with explicit scope, non-goals, and validation.

Discussion does not implement business code. Its job is to decide what should happen next, not to plan, execute, and approve its own patch in one context.

### Worker: execute inside the boundary

A Worker runs in an independent, user-visible, inspectable, and controllable Agent thread or window. It reads the exact Task, execution rules, necessary state, and in-scope source. `enforce` requires a bound Claim before changes; `warn` does not block when Claim automation is unavailable.

At closeout it leaves an immutable Run Report covering changes, validation, risk, and proposed project-state updates. A prose “done” message is not equivalent evidence.

### Integration: let the project remember

With runtime automation, Worker terminal state enters `integration_pending`; otherwise a warn-mode Worker returns its report and result commit directly. Discussion-local Integration evaluates, merges, and writes back safe results.

`reports/PROJECT_STATUS.md` remains a current snapshot while history stays in Run Reports and Git. The next window resumes from that state without copying a full prompt or retelling the project.

## 5. Humans stay responsible

WishGraph does not remove human judgment. Humans still:

- Express needs and dissatisfaction.
- Choose product direction and trade-offs.
- Authorize exact Tasks.
- Accept material risks and changes.
- Review the final result.

What changes is the translation burden. The user no longer has to expand every wish into dozens of engineering instructions or move all background between windows. The system compresses human decisions into a few concrete questions and delegates mechanical execution and evidence collection to Agents.

Review is therefore a presentation state inside Discussion, not a fourth Agent. The user should see what the system understood, what it planned, what changed, how it was checked, what remains risky, and what comes next.

## 6. Anti-black-box does not mean total explainability

WishGraph does not explain a model's internals or make a complex project instantly simple. It improves inputs, outputs, and control boundaries around both black boxes.

Every execution should answer:

- What human intent did it infer?
- What are the Task's scope and non-goals?
- Why were these files changed?
- What validation ran?
- What risk remains?
- Do product, architecture, code-map, or current-state facts need an update?

This is not documentation for its own sake. It makes the work reviewable by humans, inheritable by future agents, and traceable back to a specific assumption when something fails.

## 7. Debug causality instead of guessing familiar files

A common repair loop sees a broken page and tries a patch in a familiar View. WishGraph follows the causal chain:

```text
Error → State → Code → Spec
```

Confirm the symptom, find the earliest wrong state, locate the code that wrote or read it, then return to the spec to decide the correct behavior. If the spec is unclear, the problem returns to Discussion instead of letting a Worker hide ambiguity behind a larger patch.

The target is always the smallest verifiable and reversible change set.

## 8. WishGraph and Harness Engineering

WishGraph belongs to the broad field of Harness Engineering: it organizes agent-readable project knowledge, execution boundaries, feedback loops, and mechanical checks.

Its particular focus is **long-term project continuity**. After switching windows, models, agents, or hosts, are goals, structure, tasks, evidence, and current state still understandable? Can the human see why the project arrived here and why the next step is appropriate?

WishGraph is therefore one concrete practice, not a universal answer to Agent engineering. It does not replace version control, testing, code review, permission systems, containers, or operating-system sandboxes. It places those capabilities inside a project loop that can be handed off safely.

## 9. The larger direction

Agents are moving the computer's control surface upward toward natural language. The faster models complete local work, the more projects need clear state, durable memory, and auditable control loops.

WishGraph is a form of compression: it turns a large, messy, changing project into a structure that humans and AI can continue to understand, reason about, hand off, and validate. The project does not become small. It becomes governable again.
