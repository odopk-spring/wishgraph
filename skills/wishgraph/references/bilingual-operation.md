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

## First Intake Prompt

Chinese:

```text
先不用写完整 PRD。请用几句话告诉我：
1. 你想做一个什么项目？
2. 最先服务谁？
3. 他们第一次打开时最应该完成什么动作？
4. 你会用什么结果判断 v0 做对了？
如果还不确定，可以只回答第 1 点，我会继续一问一问补齐。
```

English:

```text
You do not need a full PRD yet. In a few sentences, tell me:
1. What are you trying to build?
2. Who should it serve first?
3. What should they be able to do on the first successful use?
4. What result would make you say v0 is working?
If you are not sure, answer only item 1 and I will fill the rest one decision at a time.
```

Bilingual:

```text
先不用写完整 PRD。请用几句话告诉我：
1. 你想做一个什么项目？
2. 最先服务谁？
3. 他们第一次打开时最应该完成什么动作？
4. 你会用什么结果判断 v0 做对了？
如果还不确定，可以只回答第 1 点，我会继续一问一问补齐。

You do not need a full PRD yet. In a few sentences, tell me:
1. What are you trying to build?
2. Who should it serve first?
3. What should they be able to do on the first successful use?
4. What result would make you say v0 is working?
If you are not sure, answer only item 1 and I will fill the rest one decision at a time.
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
