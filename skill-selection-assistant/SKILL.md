---
name: skill-selection-assistant
description: Detect the most relevant local Codex skills for the current user request, introduce the best 1-3 options in the same language the user used, ask the user which skill to use, and confirm before any required environment download, installation, or user-specific prerequisite configuration.
metadata:
  short-description: Match local skills and ask the user to choose
---

# Skill Selection Assistant

Use this skill at the beginning of a request when Codex should decide which local skills are most relevant before continuing.

## Goal

Before solving the user's request:

1. Inspect local skills under the user's Codex skills directory.
2. Find the smallest useful set of relevant skills.
3. Prefer the best `1-3` skills instead of dumping a long list.
4. Introduce the matched skills in the same language the user used for the request.
5. Ask the user which skill they want to use.
6. If a selected skill may require downloading or installing dependencies, ask the user for confirmation before starting the setup.
7. If a selected skill needs user-specific prerequisite configuration, ask the required setup questions before execution.
8. Continue only after the user chooses a skill, explicitly says to answer directly, or explicitly says not to use a skill.

## When To Use

Use this skill when:

- the request may match one or more local skills
- the user did not explicitly name which skill to use
- the conversation should stay skill-first

Skip this skill when:

- the user explicitly names the skill to use
- the user says `直接回答`
- the user says `不使用skill`
- the user is asking to install, rename, inspect, organize, debug, or publish skills themselves

## Matching Rules

Select only the smallest useful set.

- Prefer `1-3` skills.
- If the user explicitly names a skill, include it first.
- If nothing is clearly relevant, say that no strong skill match was found and ask whether to answer directly.
- Prefer practical fit over theoretical fit.
- Prefer skills that can directly help with the next step of the task.

## Priority Order

When multiple skills match, prefer this order:

1. User-customized local skills
2. Official core local skills
3. Explicitly installed topical skills such as `baoyu-*`
4. Larger research or community libraries only if they are clearly a better fit

## Selection Reply Language

Use the same language the user used in their current request.

- If the user asks in Chinese, reply in Chinese.
- If the user asks in English, reply in English.
- If the user asks in Japanese, reply in Japanese.
- If the user clearly mixes languages, follow the dominant language of the request.

Keep each skill explanation short and practical, ideally one sentence per skill.

Recommended pattern:

1. Briefly say you matched the most relevant local skills.
2. List the best `1-3` skills.
3. Give one short practical explanation for each skill.
4. Ask which skill the user wants to use.
5. Optionally mention that you can also answer directly without using the selection step.

## Environment Setup Confirmation

If a matched or selected skill appears likely to require extra setup, such as:

- downloading runtime dependencies
- installing Python, Node.js, browser tooling, or document-processing packages
- pulling model files or external toolchains
- installing bundled workspace dependencies

then before continuing:

1. Tell the user briefly in the same language they used that this skill may need additional environment download or installation.
2. Explain the setup in one short practical sentence.
3. Ask the user whether to continue with the download or installation.
4. Do not start the download or installation unless the user clearly agrees.

Recommended wording:

- Chinese example:

```text
这个 skill 在使用前可能需要先下载或安装一些环境依赖，主要是：{一句话说明依赖类型}。
你要我现在继续下载并配置吗？
```

- English example:

```text
This skill may need some extra environment setup before use, mainly: {one short description of the dependency type}.
Do you want me to continue with the download and setup now?
```

## Prerequisite Configuration Questions

If the selected skill does not need downloads but still depends on user-specific setup choices, ask a short question flow before execution.

Typical cases include:

- account or workspace selection
- API key or connector source choice
- browser profile or target app selection
- output path, publishing target, or destination selection
- provider, model, format, or mode selection

Rules:

1. Use the same language the user used in the request.
2. Ask only the minimum number of questions needed to unblock the selected skill.
3. Prefer short, practical setup questions over long explanations.
4. Do not silently choose user-owned settings when they may change the result in an important way.
5. If a safe obvious default exists, offer it clearly and let the user confirm it.

Recommended wording:

- Chinese example:

```text
这个 skill 在继续之前还需要先确认几个前置配置，比如：{一句话说明配置类型}。
我先问你这几个设置，再继续执行，可以吗？
```

- English example:

```text
Before this skill can continue, I still need to confirm a few prerequisite settings, mainly: {one short description of the configuration type}.
I’ll ask you those setup questions first, then continue. Is that okay?
```

## Continue Conditions

You may continue without asking again only when one of these is true:

- the user explicitly picked a skill
- the user said `直接回答`
- the user said `不使用skill`
- the user is asking a pure skill-management question and the answer itself is about skills

## Notes

- Do not dump a huge list of skills.
- Do not explain internal implementation details unless the user asks.
- Keep the selection step lightweight and easy to answer.
- Prefer real task fit, not keyword over-matching.
