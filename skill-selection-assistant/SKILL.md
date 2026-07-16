---
name: skill-selection-assistant
description: Discover and classify the installing user's local Codex skills, route each new request through a token-efficient multi-level index, present a weighted shortlist in the user's language, ask which skill to activate, and protect dependency downloads and user-owned prerequisite settings behind explicit confirmation.
---

# Skill Selection Assistant

Use this skill before a normal request when no active skill has already been chosen and the user did not explicitly name or reject skill use.

## Core Objective

Treat this skill as a per-user compiler and router, not as a published catalog of the author's computer.

1. Discover the installing user's configured local skill roots.
2. Build or incrementally refresh a local multi-label index.
3. Route the request one category at a time without loading the complete catalog into model context.
4. Present the smallest useful weighted shortlist in the user's language.
5. Ask which skill to use.
6. Read only the selected `SKILL.md`.
7. Keep that skill active while the conversation stays in the same workflow.

Never assume another computer has the publisher's skill names, paths, counts, categories, or generated index.

## Trigger And Skip Rules

Run selection when:

- the current request may match installed skills
- the user has not named a skill
- no compatible skill is already active in this conversation
- or the workflow has materially changed and needs another skill

Skip selection when:

- the user explicitly names the skill to use
- the user says `直接回答`, `不使用skill`, or an equivalent instruction
- the user is installing, inspecting, debugging, organizing, or publishing skills themselves
- the current turn remains inside the already selected workflow

Do not ask again merely because the user made the task more specific.

## Normal Routing Command

Use the cross-platform compact entry point:

```bash
python scripts/recommend-skills.py --query "<user request>" --compact
```

The stable top-level response uses schema `3.0.0` and exposes:

- `mode`
- `route`
- `branches`
- `candidates`
- `index`
- `next_step`

Do not request the deprecated nested `deep_route` object unless an older consumer requires `--compat`.

Follow the returned mode:

### `choose_category`

1. Show only the returned branches.
2. Briefly explain the practical distinction in the user's language.
3. Ask the user to choose one.
4. Continue with the exact returned path:

```bash
python scripts/recommend-skills.py --query "<user request>" --path "<exact path>" --compact
```

### `choose_skill`

1. Present the returned compact candidates in their ranked order.
2. Give one short practical reason for each candidate.
3. Mention all explicit `setup_requirements` that affect the choice.
4. Ask which skill to activate.
5. Read only the chosen `SKILL.md` after the user chooses.

### `no_skills_installed`

Tell the user that no other local skills are currently available. Offer to:

- answer directly
- install a relevant skill
- or create a new skill

Never expose an internal traceback for an empty library.

### `index_stale`

Refresh the index through the recommender before selecting. Do not recommend from stale classifications.

## Recommendation Rules

- Use the dynamic returned set; never force a fixed `1-3` count.
- A strong match may return one skill; several close matches may return more.
- Prefer user-local skills, then official system skills, then installed topical skills, then linked external/community skills.
- Prefer workflow fit over keyword overlap.
- Merge identical content and keep meaningful same-name variants distinguishable.
- Do not load the full hierarchy, detailed catalog, NDJSON index, or all route cards into model context during ordinary selection.
- Do not invent candidates that were not returned by the installing user's current index.

## User-Facing Language

Use the same language as the current user request. Keep explanations concise.

Recommended Chinese pattern:

```text
我匹配到这些相关 skill：

- `技能名`：一句话说明用途。

你想使用哪一个？也可以说“直接回答”。
```

## Environment And Prerequisite Safety

`setup_requirements` may contain multiple labels:

- `local-runtime`
- `network`
- `account`
- `api-key`
- or `none`

Before a selected skill downloads or installs anything:

1. State what runtime, dependency, model, or toolchain is needed.
2. Ask whether to continue.
3. Do not download until the user clearly agrees.

Before using user-owned settings such as accounts, workspaces, API keys, browser profiles, providers, output paths, publishing destinations, or deployment targets:

1. Ask only the minimum questions needed.
2. Offer a safe default when one exists.
3. Do not silently assume settings that materially change the result.

## Local Index Lifecycle

The preferred installer is:

```bash
python scripts/install-skill.py
```

The installer requires Python 3.10 or newer. PowerShell is optional and is used only for compatibility reports and legacy routing.

On first installation:

- resolve the actual installing user's roots
- exclude this router skill from candidates
- classify every discovered `SKILL.md` in full
- preserve linked-skill logical and resolved paths
- publish the deep index under the installed router's `.skill-index/`
- run a first recommendation health check

On later refreshes, reuse unchanged classifications and read only added or modified skill files when schema, classifier, and rules fingerprints remain compatible.

Before routing, validate the required deep artifacts and schema. Rebuild missing, incomplete, corrupt, or old-schema indexes, recovering configured roots from `source-manifest.json` when possible. Use `python scripts/doctor.py --fix` for explicit cross-platform repair.

If failures exist, treat the index as `degraded`, report `failed_files`, and continue only with successfully classified skills. Use `--strict` for CI or audits that must fail on any classification error.

Generated `.skill-index/` data is local runtime state. Never commit it or include it in a release.

For installation planning, activation, and diagnostics, read [references/INSTALLATION.md](references/INSTALLATION.md) only when those operations are requested.

For the classification model and audit artifacts, read [references/CLASSIFICATION.md](references/CLASSIFICATION.md) only during classifier maintenance or an explicit taxonomy audit.

## Feedback And Conversation Continuity

After the user selects, rejects, or reports a missed match, record route-scoped feedback when useful:

```bash
python scripts/record-selection-memory.py --query "<request>" --outcome selected --selected-skill "<skill>" --route-type "<level>" --category "<category>"
```

Raw queries are not stored by default. Use `--store-query` only when the user accepts local retention.

Serialize concurrent memory appends and escape Markdown control characters in recorded fields so one malformed or simultaneous feedback event cannot corrupt later ranking.

Memory boosts must remain bounded and apply only inside compatible selected routes. They must not influence root-level routing across unrelated categories.

For self-growth reports and maintenance policy, read [references/SELF_GROWTH.md](references/SELF_GROWTH.md) only when the user requests feedback analysis, taxonomy improvement, or skill-library maintenance.

## Installation Activation Boundary

Installing the folder does not automatically authorize editing global instructions.

- Detect whether the user's global `AGENTS.md` already activates this router.
- Show the opt-in activation step after installation.
- Modify `AGENTS.md` only when the user explicitly uses `--configure-agents` or otherwise authorizes the write.
- Preserve all unrelated existing instructions inside that file.

## Failure Handling

- Return structured errors for expected installation and routing problems.
- Do not expose Python tracebacks unless debug mode is explicitly requested.
- Stage managed-file updates and roll them back on publication failure while preserving `.skill-index/`.
- Preserve the last usable index if a refresh fails.
- Serialize concurrent index publication with a cross-process lock.
- Never modify, move, or delete the skills being indexed.
