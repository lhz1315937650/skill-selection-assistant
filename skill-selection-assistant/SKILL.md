---
name: skill-selection-assistant
description: Detect the most relevant local Codex skills for the current user request, introduce the best 1-3 options in simple Chinese, ask the user which skill to use, and confirm before any required environment download or installation.
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
4. Introduce the matched skills in simple Chinese.
5. Ask the user which skill they want to use.
6. If a selected skill may require downloading or installing dependencies, ask the user for confirmation before starting the setup.
7. Continue only after the user chooses a skill, explicitly says to answer directly, or explicitly says not to use a skill.

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

## Chinese Intro Format

Use short, practical Chinese. Keep each skill explanation to one sentence.

Recommended format:

```text
我先帮你匹配了一下当前本地比较适合的 skill：

1. skill-name
   作用：一句中文说明它适合拿来做什么。

2. skill-name
   作用：一句中文说明它适合拿来做什么。

你想用哪个 skill？如果你想，我也可以直接回答，不走 skill 选择。
```

## Environment Setup Confirmation

If a matched or selected skill appears likely to require extra setup, such as:

- downloading runtime dependencies
- installing Python, Node.js, browser tooling, or document-processing packages
- pulling model files or external toolchains
- installing bundled workspace dependencies

then before continuing:

1. Tell the user briefly in Chinese that this skill may need additional environment download or installation.
2. Explain the setup in one short practical sentence.
3. Ask the user whether to continue with the download or installation.
4. Do not start the download or installation unless the user clearly agrees.

Recommended wording:

```text
这个 skill 在使用前可能需要先下载或安装一些环境依赖，主要是：{一句话说明依赖类型}。
你要我现在继续下载并配置吗？
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
