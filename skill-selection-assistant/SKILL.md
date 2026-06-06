---
name: skill-selection-assistant
description: Detect the most relevant local Codex skills for the current user request, introduce a weighted shortlist in the same language the user used, ask the user which skill to use, and confirm before any required environment download, installation, or user-specific prerequisite configuration.
metadata:
  short-description: Match local skills and ask the user to choose
---

# Skill Selection Assistant

Use this skill at the beginning of a request when Codex should decide which local skills are most relevant before continuing.

## Goal

Before solving the user's request:

1. Inspect local skills under the user's Codex skills directory.
2. On install, update, or first use, scan and classify local skills into a lightweight multi-level index.
3. Find the smallest useful set of relevant skills.
4. Prefer a weighted shortlist instead of dumping a long list.
5. Introduce the matched skills in the same language the user used for the request.
6. Ask the user which skill they want to use.
7. If a selected skill may require downloading or installing dependencies, ask the user for confirmation before starting the setup.
8. If a selected skill needs user-specific prerequisite configuration, ask the required setup questions before execution.
9. Continue only after the user chooses a skill, explicitly says to answer directly, or explicitly says not to use a skill.
10. After the user chooses a skill for the current conversation, keep using that active skill on later turns unless the work clearly needs a different skill.
11. Ask the user to choose again only when a later turn clearly introduces a different skill with a meaningfully different workflow, setup, or output.
12. Maintain a self-growing local skill library by recording recurring intents, missed matches, overlapping skills, and new skill opportunities.

## Portability Rule

This skill must work for any user who installs it.

Therefore:

- inspect the user's own local Codex skills directory
- do not depend on the publisher's personal filesystem path
- treat `$CODEX_HOME/skills` as the typical portable skills root
- treat platform-specific paths only as examples for documentation

Never define published behavior in a way that requires a hardcoded machine-specific path such as `C:\Users\<PublisherUser>\.codex\skills`.

## Scope Boundary

Distinguish the router skill from the skill library it scans:

- `SkillInstanceDir` is the installed `skill-selection-assistant` folder that contains this `SKILL.md`, scripts, and generated `.skill-index/`.
- `SkillsRoot` is the current user's own local Codex skills directory.
- The generated `.skill-index/` is stored beside this router skill, but it describes `SkillsRoot`, not the publisher's development machine.

Never assume the downloader has the same number, names, categories, or paths of skills as the publisher. Every install must classify that user's actual local skill library.

## When To Use

Use this skill when:

- the request may match one or more local skills
- the user did not explicitly name which skill to use
- the conversation should stay skill-first
- no active skill has already been chosen for the current conversation
- or the current turn clearly needs a different skill from the active one

Skip this skill when:

- the user explicitly names the skill to use
- the user says `直接回答`
- the user says `不使用skill`
- the user is asking to install, rename, inspect, organize, debug, or publish skills themselves
- the current turn can continue naturally under the skill the user already chose earlier in the same conversation

## Conversation Continuity

Treat the user's first confirmed skill choice in a conversation as the active skill for that conversation.

On later turns:

- If the new request still fits the active skill, continue without re-running skill selection.
- If the new request clearly needs a different skill, briefly surface the best weighted options and ask the user to choose again.
- If the user explicitly switches skills, follow the new choice and treat it as the active skill from that point onward.
- If the user explicitly says to answer directly or not use a skill, do not force the prior active skill.

Use a practical standard when deciding whether a new skill is involved:

- Do not re-ask just because the user is moving to a more specific step inside the same workflow.
- Do re-ask when the next step is better handled by a different skill with a materially different workflow, setup requirement, or deliverable style.

## Matching Rules

Select only the smallest useful set.

- Prefer the returned weighted shortlist from the selector.
- Do not hardcode the visible recommendation count to `1-3`.
- If scores are close or the task naturally spans multiple workflows, it is acceptable to recommend more candidates.
- Keep a practical cap, usually no more than `8`, unless the user explicitly asks for a longer list.
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
2. List the weighted shortlist returned by the selector.
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
I'll ask you those setup questions first, then continue. Is that okay?
```

## Portable Indexing Direction

If this skill later adds install-time or update-time offline scanning, that scan must target the user's own local skill installation, not the repository author's machine.

The intended portable rule is:

1. resolve the user's skills root from the runtime environment
2. scan that local skills root
3. build a lightweight catalog from installed skills
4. use that catalog for future prefiltering

Do not describe or implement offline indexing as scanning a hardcoded personal development path.

## Install-Time And First-Use Indexing

When this skill is installed, updated, or used in a fresh environment, build a local skill index before recommending skills.

Preferred command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/scan-local-skills.ps1
```

The scanner should:

1. Locate the user's local skills root.
2. Read each `SKILL.md` frontmatter and lightweight body preview.
3. Classify each skill into weighted multi-level categories.
4. Write `.skill-index/skills-index.json`.
5. Write `.skill-index/manifest.json` as a lightweight file fingerprint manifest.
6. Write `.skill-index/parsed-skills-cache.ndjson` for unchanged-file parse reuse.
7. Write `.skill-index/skills-categories.md`.
8. Write `.skill-index/route-summary.json` and `.skill-index/route-summary.md`.
9. Write category-specific route files under `.skill-index/routes/` only when `-IncludeFullRoutes` is used for audits.
10. Write category-specific shortlist files under `.skill-index/shortlists/`.
11. Write or preserve `.skill-index/selection-memory.md`.

The scanner output should keep `SkillInstanceDir` and `SkillsRoot` separate so users can see which router skill instance produced the index and which local skill library was scanned.

The scanner and route inference should load shared classification rules from `rules/categories.json`. Do not hardcode publisher-specific skill names, local counts, or local paths into those rules.

If the index is missing, stale, or clearly incomplete, rebuild it before making recommendations.

For first-install diagnostics or a broken local index, run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/doctor.ps1 -Fix
```

The generated index is a recommendation view, not a destructive filesystem operation. It may merge duplicate names in the index while keeping all real local skill files untouched.

## Token-Saving Route-First Selection

Do not read every local skill before recommendation. Always use a route-first workflow:

1. Prefer running `scripts/recommend-skills.ps1` with the user's request; it performs route inference and candidate selection in one compact step.
2. If the one-command recommender is unavailable, run `scripts/infer-route.ps1` and then `scripts/select-route-candidates.ps1`.
3. If scripts are unavailable, read only `.skill-index/route-summary.md` or `.skill-index/route-summary.json`.
4. Choose the most relevant shortlist from `.skill-index/shortlists/primary-domain/`, `.skill-index/shortlists/domain-detail/`, or `.skill-index/shortlists/task-type/`.
5. Read full route files under `.skill-index/routes/` only when the matching shortlist is missing or clearly insufficient; they are generated only when the scanner is run with `-IncludeFullRoutes`.
6. Shortlist candidates according to selector scores and the returned `recommendation_policy`; default dynamic recommendations should also respect the relevance gate so weakly related candidates are not shown only because they scored well inside a broad route.
7. Read the actual candidate `SKILL.md` files only after shortlisting, and only when the recommendation or execution needs details.
8. Never load the full `.skill-index/skills-index.json` unless route files are missing, stale, or insufficient.

Selector command pattern:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/recommend-skills.ps1 -Query "<user request>"
powershell -ExecutionPolicy Bypass -File scripts/infer-route.ps1 -Query "<user request>"
powershell -ExecutionPolicy Bypass -File scripts/select-route-candidates.ps1 -Query "<user request>" -RouteType domain_detail -Category frontend-web
```

If multiple categories are plausible, prefer the narrowest high-confidence `domain_detail` route. If the request is broad or ambiguous, use `primary_domain` first, then refine with `task_type`.

## Multi-Level Classification

Classify each local skill using:

- `origin`: `user-local`, `official-system`, `installed-topic`, `linked-external`, or `unknown`
- `primary_domain`: best single broad area for fast selection
- `domain`: broad areas such as `writing`, `research`, `coding`, `data`, `design`, `documents`, `publishing`, `safety`, or `general`
- `domain_detail`: fine-grained weighted labels such as `frontend-web`, `backend-api`, `academic-research`, `visual-design`, `publishing-social`, `document-processing`, `automation-integration`, or `testing-debugging`
- `task_type`: practical action such as `summarize`, `review`, `generate`, `transform`, `test-debug`, `extract`, `publish`, `plan`, or `analyze`
- `output_type`: likely output such as `markdown`, `image`, `pptx`, `docx`, `xlsx`, `html`, `code`, `report`, or `workflow`
- `setup_level`: `none`, `local-runtime`, `network`, `account`, `api-key`, or `unknown`
- `status`: `active`, `needs-review`, `deprecated`, or `unknown`
- `duplicate_count`: how many same-name local entries were merged into this recommendation candidate
- `duplicate_name_count`: how many local entries shared this skill name before variant-aware deduplication
- `variant_id`, `variant_index`, and `variant_count`: preserve same-name skills with different content as separate variants
- `source_paths`: all local source paths represented by the merged candidate

For domain detection, prefer strong signals from the skill name, then frontmatter descriptions, then body previews. Use these categories internally for selection. Do not expose a long taxonomy to the user unless they ask.

When recommending skills to the user, merge same-name variants into one visible recommendation by default. Keep variant details internally and surface them only when they materially change the choice or the user asks.

## Selection Workflow In A Project Conversation

At the beginning of a normal project conversation:

1. Detect the user's language.
2. Summarize the current request internally.
3. Run `scripts/recommend-skills.ps1` when available.
4. If the one-command recommender is unavailable, run `scripts/infer-route.ps1` and `scripts/select-route-candidates.ps1`.
5. Load `.skill-index/route-summary.md` or `.skill-index/route-summary.json` only if route inference is unavailable.
6. Read only the matching shortlist file if the selector is unavailable.
7. Match compact route candidates by semantic fit, not only keywords.
8. Prefer exact workflow fit, `primary_domain`, and `domain_detail` over broad keyword overlap.
9. Recommend the weighted shortlist returned by the selector; do not force a fixed `1-3` count.
10. Use the user's language for the recommendation.
11. Keep each recommendation concise: skill name plus one short practical reason.
12. Ask which skill to use, unless a skip condition applies.

Chinese recommendation style:

```text
我匹配到 2 个最相关的 skill：

- `技能名`：一句话说明它为什么适合。
- `技能名`：一句话说明它为什么适合。

你想用哪一个？也可以说“直接回答”。
```

English recommendation style:

```text
I found 2 relevant skills:

- `skill-name`: one short reason it fits.
- `skill-name`: one short reason it fits.

Which one should I use? You can also say "answer directly".
```

## Self-Growing Skill Logic

After each selection or skill-management session:

1. Record useful match patterns in `.skill-index/selection-memory.md`.
2. Record missed or poor matches as improvement notes.
3. If a user repeatedly asks for a workflow that no skill covers, suggest creating a new skill.
4. If several skills overlap heavily, suggest linking, merging, or marking one as `needs-review`.
5. If a skill requires setup and that setup fails, record the failure pattern for future warnings.
6. If a new skill appears in the local skills root, re-run the scanner and update the category map.

Use the memory recorder after a user chooses, rejects, or reports a missed match:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/record-selection-memory.ps1 -Query "<user request>" -Outcome selected -SelectedSkill "<skill name>" -RouteType domain_detail -Category "<category>"
```

Do not directly delete or rewrite unrelated local skills. Default to producing recommendations, indexes, and draft improvements.

## Continue Conditions

You may continue without asking again only when one of these is true:

- the user explicitly picked a skill
- the user already picked a skill earlier in the same conversation and the current turn still fits that active skill
- the user said `直接回答`
- the user said `不使用skill`
- the user is asking a pure skill-management question and the answer itself is about skills

## Notes

- Do not dump a huge list of skills.
- Do not explain internal implementation details unless the user asks.
- Keep the selection step lightweight and easy to answer.
- Prefer real task fit, not keyword over-matching.
