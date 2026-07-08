# Bilingual Operation

Use this reference when the user asks for Chinese, English, bilingual output, mixed-language handoff, or language rules for generated project memory.

## Language Mode

Set a project language mode in `prompts/DISCUSSION_AI.md` and keep it current:

- Primary language: Chinese / English / user-selected language.
- Bilingual output: Yes / No.
- Rule: follow the user's language by default. If bilingual output is requested, write key user-facing prompts, summaries, decisions, and task explanations in Chinese first, then English.

Do not translate:

- file paths
- commands
- code identifiers
- symbols
- routes
- package names
- environment variables
- literal API names

## First Idea Question

Chinese:

```text
你现在有什么想法？可以很粗糙，只要说你想做什么、给谁用、解决什么问题。
```

English:

```text
What idea do you have right now? It can be rough: what do you want to build, who is it for, and what problem should it solve?
```

Bilingual:

```text
你现在有什么想法？可以很粗糙，只要说你想做什么、给谁用、解决什么问题。
What idea do you have right now? It can be rough: what do you want to build, who is it for, and what problem should it solve?
```

## Grill Question Format

Chinese:

```text
问题 N：<one concrete decision>

我建议先选：<recommended default>。
原因：<one sentence>.
如果你不同意，可以直接改成你的版本。
```

English:

```text
Question N: <one concrete decision>

Recommended default: <recommended default>.
Reason: <one sentence>.
If you disagree, replace it with your version.
```

Bilingual:

```text
问题 N / Question N: <one concrete decision>

我建议先选 / Recommended default: <recommended default>.
原因 / Reason: <one sentence>.
如果你不同意，可以直接改成你的版本。 / If you disagree, replace it with your version.
```

## Task Specs

For bilingual task specs, keep the task compact:

- Write section headings in one language unless the user explicitly wants bilingual headings.
- Make `Intent`, `Current State`, `Do Not Do`, `Validation`, and `Execution Report Requirements` bilingual when they are read by humans.
- Keep `Change Set` anchors exact and untranslated.
- Keep commands exact and untranslated.
- Avoid repeating long context twice; write short Chinese + English summaries instead.
