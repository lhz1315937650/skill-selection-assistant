# Skill Selection Assistant

[![Release](https://img.shields.io/github/v/release/lhz1315937650/skill-selection-assistant)](https://github.com/lhz1315937650/skill-selection-assistant/releases)
[![License](https://img.shields.io/github/license/lhz1315937650/skill-selection-assistant)](./LICENSE)

[中文介绍](./README.zh-CN.md) | English

A Codex skill that turns a large local skill library into a cleaner, more predictable user experience.

Instead of jumping straight into execution, it checks the user's local skills first, recommends the best matching options in the user's own language, asks which one to use, keeps that choice active across the rest of the conversation when the workflow still fits, and asks before any environment setup or user-owned configuration.

## What Problem It Solves

When a Codex setup contains many local skills, the assistant can easily:

- skip skill routing entirely
- surface too many skills at once
- recommend skills without explaining why they matter
- repeatedly ask for skill selection even after the user already chose one
- begin environment setup before the user clearly agrees
- silently assume user-owned settings such as accounts, output targets, or providers

This skill adds a lightweight selection layer that makes multi-skill setups feel deliberate instead of noisy.

## Core Behavior

- inspects the user's local skill library before continuing with a normal request
- optionally scans the local skills root on install or first use
- classifies skills by origin, domain, task type, output type, setup level, and status
- recommends a weighted shortlist instead of a hardcoded number of skills
- explains each match briefly in the same language the user used
- asks the user which skill to use before continuing
- keeps the user's chosen skill active for later turns in the same conversation when the workflow still fits
- asks the user to choose again only when a later turn clearly needs a different skill
- asks for confirmation before downloading or installing dependencies required by a selected skill
- asks follow-up setup questions when the selected skill still needs user-specific prerequisite configuration
- records recurring match patterns, missed matches, and skill gaps so the local skill library can become self-growing

## Important Portability Rule

This repository is meant to be installed by different users in different Codex environments.

That means:

- the skill must reason about the user's own local skill installation, not the publisher's machine
- published behavior must not depend on a publisher-specific path such as `C:\Users\<PublisherUser>\.codex\skills`
- runtime path resolution should use the user's Codex environment, typically `$CODEX_HOME/skills`

Windows paths shown in this repository are examples only. They are not product defaults.

## Local Copy vs Published Skill

There are two different scopes:

- The installed `skill-selection-assistant` folder is only the router skill instance. It stores scripts, instructions, and that user's generated `.skill-index/`.
- The scanned skills root is the installing user's own Codex skill library. Its size and contents vary from machine to machine.
- The publisher's local copy, local benchmark counts, paths, and generated indexes are development data only. They must not be treated as defaults for downloaders.

For example, on one machine the scanned library may contain thousands of skills; on another downloader's computer it may contain only a few. The scanner must always resolve and index the current user's runtime skills root.

## Why The Conversation Continuity Matters

The key behavior introduced in `v1.3.0` is conversation continuity.

After the user chooses a skill once, Codex should not keep re-running skill selection on every later turn. It should continue under that active skill until the task clearly shifts into a different workflow.

That makes the interaction feel more like:

- "pick the tool once, then keep moving"

instead of:

- "pick the tool again every turn"

## Install-Time / First-Use Local Index

This repository includes a portable scanner that can be run during install, update, or first use:

```powershell
powershell -ExecutionPolicy Bypass -File skill-selection-assistant/scripts/scan-local-skills.ps1
```

It scans the user's own local Codex skills root and writes:

```text
skill-selection-assistant/.skill-index/
|-- skills-index.json
|-- manifest.json
|-- parsed-skills-cache.ndjson
|-- skills-categories.md
|-- route-summary.json
|-- route-summary.md
|-- routes/                 # optional; only with -IncludeFullRoutes
|   |-- primary-domain/
|   |-- domain-detail/
|   `-- task-type/
|-- shortlists/
|   |-- primary-domain/
|   |-- domain-detail/
|   `-- task-type/
`-- selection-memory.md
```

The generated index is local to the installing user and is ignored by git.

The scanner output distinguishes `SkillInstanceDir` from `SkillsRoot`: `SkillInstanceDir` is where this router skill is installed, while `SkillsRoot` is the user's skill library being classified.

For token efficiency, `skills-index.json` and full route files are treated as fallback and audit files. Normal recommendation should infer one category, read only the matching shortlist, and then inspect only the top candidate skills. Full route files are not generated by default; run the scanner with `-IncludeFullRoutes` when you need audit-sized route files.

```powershell
powershell -ExecutionPolicy Bypass -File skill-selection-assistant/scripts/scan-local-skills.ps1 -IncludeFullRoutes
```

`manifest.json` is a lightweight file fingerprint manifest. `parsed-skills-cache.ndjson` stores reusable parsed skill metadata one skill per line. Re-running the scanner can reuse unchanged `SKILL.md` files when the parser schema, rules schema, file size, and modified time match.

You can ask the one-command recommender to infer a route and return a small shortlist:

```powershell
powershell -ExecutionPolicy Bypass -File skill-selection-assistant/scripts/recommend-skills.ps1 -Query "build a frontend UI"
powershell -ExecutionPolicy Bypass -File skill-selection-assistant/scripts/infer-route.ps1 -Query "build a frontend UI"
powershell -ExecutionPolicy Bypass -File skill-selection-assistant/scripts/select-route-candidates.ps1 -Query "build a frontend UI" -RouteType domain_detail -Category frontend-web
```

By default, recommendations use a dynamic score window instead of a fixed `1-3` count. Tune `-MaxRecommendations`, `-ScoreWindow`, and `-MinRelevanceScore` when a local skill library is very large or contains many near-duplicate skills. `-MinRelevanceScore` filters dynamic recommendations that do not directly match enough useful query words, while explicit `-Limit` still works as a manual override.

## Self-Growing Skill Library

This skill is intended to make the whole local skill library self-growing:

1. build a lightweight local skill catalog during install or update
2. classify requests into a primary domain, fine-grained domain, and task type first
3. read only the matching shortlist instead of reading every skill or every route candidate
4. send only the top candidate skills into the main routing step
5. record useful and failed matches in local selection memory
6. suggest new skills when repeated workflows are not covered
7. suggest linking, merging, or reviewing overlapping skills

By itself, smarter in-model recommendation does not guarantee lower token usage if the host still injects the full skill list every turn.

The intended default is route-first selection:

1. infer category
2. run `recommend-skills.ps1`, or run `select-route-candidates.ps1` against the inferred category
3. read `route-summary` and one shortlist only if scripts are unavailable
4. recommend the weighted shortlist returned by the selector; this may be one strong candidate or several close candidates
5. read actual `SKILL.md` files only after shortlisting or user choice

After the user chooses a skill or reports a missed match, record the feedback locally:

```powershell
powershell -ExecutionPolicy Bypass -File skill-selection-assistant/scripts/record-selection-memory.ps1 -Query "build a frontend UI" -Outcome selected -SelectedSkill "frontend-design" -RouteType domain_detail -Category frontend-web
```

## Example Flow

User:

```text
Read the Markdown files in this folder.
```

Assistant:

- checks local skills first
- recommends the weighted shortlist of relevant skills
- explains them briefly in the user's language
- asks which one to use

User:

```text
Direct answer.
```

Assistant:

- continues directly

Later in the same conversation:

```text
Now summarize the file and turn it into a short checklist.
```

Assistant:

- continues in the same workflow without forcing another skill choice if the current active skill still fits

Only when the task clearly changes, for example from reading documentation to generating images, browser automation, or publishing content, should the assistant surface a fresh skill choice.

## Good Fit

This skill is especially useful if you:

- keep many local Codex skills installed
- work in more than one language
- want a cleaner skill-routing experience
- want safer handling for downloads, installs, and runtime setup
- want Codex to respect user-owned settings before executing specialized workflows

## Repository Structure

```text
skill-selection-assistant/
|-- README.md
|-- LICENSE
|-- CHANGELOG.md
|-- INSTALLATION_BEHAVIOR.md
|-- SELF_GROWTH.md
|-- scripts/
|   |-- clean-local-artifacts.ps1
|   |-- install-skill.py
|   |-- install-skill.ps1
|   `-- package-release.ps1
|-- tests/
|   |-- run-smoke-tests.ps1
|   `-- fixtures/
|-- .github/
|   `-- workflows/
|       `-- smoke-tests.yml
`-- skill-selection-assistant/
    |-- SKILL.md
    |-- scripts/
    |   |-- doctor.ps1
    |   |-- infer-route.ps1
    |   |-- record-selection-memory.ps1
    |   |-- recommend-skills.ps1
    |   |-- scan-local-skills.ps1
    |   `-- select-route-candidates.ps1
    |-- rules/
    |   `-- categories.json
    `-- agents/
        `-- openai.yaml
```

## Install

Recommended cross-platform quick install:

```bash
python scripts/install-skill.py
```

On Windows, the PowerShell installer is also supported:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install-skill.ps1
```

This copies the router skill into your local Codex skills directory and runs the first local scan. Re-run with `-Force` when updating an existing installation.

For Python installs, use `--force` when updating and `--skip-scan` if PowerShell/pwsh is not available yet:

```bash
python scripts/install-skill.py --force
python scripts/install-skill.py --skip-scan
```

After installation, you can diagnose the local setup:

```powershell
powershell -ExecutionPolicy Bypass -File skill-selection-assistant/scripts/doctor.ps1 -Fix
```

Manual install is also supported. Copy the `skill-selection-assistant/` folder from this repository into your local Codex skills directory.

Typical path:

```text
$CODEX_HOME/skills/skill-selection-assistant
```

On Windows for a common local setup:

```text
C:\Users\<YourUser>\.codex\skills\skill-selection-assistant
```

The skill should inspect the user's local Codex skills directory at runtime, not any repository author's personal path.

## Test

Run the dependency-free smoke test before publishing or changing routing logic:

```powershell
powershell -ExecutionPolicy Bypass -File tests/run-smoke-tests.ps1
```

The smoke test uses a tiny fixture skill library and verifies:

- local scanning and index generation
- manifest-backed rescanning with a separate parse cache
- shared category rules loaded from `skill-selection-assistant/rules/categories.json`
- NDJSON parse cache generation
- default shortlist-only route generation
- optional full route generation through `-IncludeFullRoutes`
- exact duplicate merging
- same-name different-content variant preservation
- default same-name variant merging in recommendations
- stale route and shortlist cleanup on rescan
- route inference for frontend and academic requests
- one-command recommendation through `recommend-skills.ps1`
- local self-growth memory recording through `record-selection-memory.ps1`
- first-time install diagnostics and optional index repair through `doctor.ps1 -Fix`

The same smoke test also runs in GitHub Actions on `main` pushes, pull requests, and manual workflow dispatch.

## Recommended AGENTS.md Rule

If you want this skill to run before normal requests, add a global instruction in your `AGENTS.md` telling Codex to:

1. inspect the local skills directory
2. use `skill-selection-assistant` first
3. recommend the weighted matching skills in the user's own language
4. ask the user to choose
5. keep using that chosen skill for later turns in the same conversation unless a new skill is clearly needed
6. ask again only when the later turn clearly needs a different skill
7. ask before any environment download or installation
8. ask follow-up prerequisite configuration questions when the selected skill still needs user choices

Example:

```md
Before answering each new normal request:

1. Inspect the local skill library.
2. Use `skill-selection-assistant` first.
3. Match the best weighted local skills.
4. Briefly explain them in the same language the user used.
5. Ask the user which skill to use before continuing.
6. After the user chooses a skill, keep using it for later turns in the same conversation unless a new skill is clearly needed.
7. Only ask the user to choose again when a later turn clearly needs a different skill.
8. If a selected skill requires downloads or environment setup, ask for confirmation first.
9. If a selected skill still needs user-specific prerequisite configuration, ask those setup questions before execution.
```

## Files To Customize

You can edit:

- `skill-selection-assistant/SKILL.md` to change the routing behavior and wording
- `skill-selection-assistant/scripts/doctor.ps1` to adjust first-time install diagnostics
- `skill-selection-assistant/scripts/infer-route.ps1` to adjust request-to-category inference
- `skill-selection-assistant/scripts/recommend-skills.ps1` to adjust the one-command recommendation wrapper
- `skill-selection-assistant/scripts/scan-local-skills.ps1` to adjust portable scanning and classification
- `skill-selection-assistant/scripts/select-route-candidates.ps1` to adjust shortlist ranking
- `skill-selection-assistant/rules/categories.json` to adjust shared scan and route-inference categories
- `skill-selection-assistant/agents/openai.yaml` to change agent metadata and default prompt behavior
- `INSTALLATION_BEHAVIOR.md` to document portable indexing or install/update behavior
- `SELF_GROWTH.md` to document self-growing library policies

To clean local repository-only build and index artifacts before review:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/clean-local-artifacts.ps1
```

This cleanup script only removes this repository's `dist/` folder and this router skill's local `.skill-index/`; it does not touch any user's real skills root.

To install the skill into a local Codex skills directory and run the first scan:

```bash
python scripts/install-skill.py
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install-skill.ps1
```

To build a release zip, use the packaging script instead of manually copying folders:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/package-release.ps1 -Version vX.Y.Z
```

The packaging script intentionally excludes local runtime artifacts such as `.skill-index/` and `dist/`, so the published zip does not include the publisher's local skill index.

## Release Notes

See [CHANGELOG.md](./CHANGELOG.md) for version history.

## License

MIT. See [LICENSE](./LICENSE).
