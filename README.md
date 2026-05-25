# Skill Selection Assistant

[![Release](https://img.shields.io/github/v/release/lhz1315937650/skill-selection-assistant)](https://github.com/lhz1315937650/skill-selection-assistant/releases)
[![License](https://img.shields.io/github/license/lhz1315937650/skill-selection-assistant)](./LICENSE)

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
- recommends only the best `1-3` matching skills
- explains each match briefly in the same language the user used
- asks the user which skill to use before continuing
- keeps the user's chosen skill active for later turns in the same conversation when the workflow still fits
- asks the user to choose again only when a later turn clearly needs a different skill
- asks for confirmation before downloading or installing dependencies required by a selected skill
- asks follow-up setup questions when the selected skill still needs user-specific prerequisite configuration

## Important Portability Rule

This repository is meant to be installed by different users in different Codex environments.

That means:

- the skill must reason about the user's own local skill installation, not the publisher's machine
- published behavior must not depend on a hardcoded path such as `C:\Users\Administrator\.codex\skills`
- runtime path resolution should use the user's Codex environment, typically `$CODEX_HOME/skills`

Windows paths shown in this repository are examples only. They are not product defaults.

## Why The Conversation Continuity Matters

The key behavior introduced in `v1.3.0` is conversation continuity.

After the user chooses a skill once, Codex should not keep re-running skill selection on every later turn. It should continue under that active skill until the task clearly shifts into a different workflow.

That makes the interaction feel more like:

- "pick the tool once, then keep moving"

instead of:

- "pick the tool again every turn"

## Future Direction For Lower Token Usage

This skill can become more token-efficient only if the host environment allows prefiltering before the main model sees the full skill universe.

The intended future direction is:

1. build a lightweight local skill catalog during install or update
2. classify requests against that catalog first
3. send only the top candidate skills into the main routing step

By itself, smarter in-model recommendation does not guarantee lower token usage if the host still injects the full skill list every turn.

## Example Flow

User:

```text
Read the Markdown files in this folder.
```

Assistant:

- checks local skills first
- recommends the most relevant `1-3` skills
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
`-- skill-selection-assistant/
    |-- SKILL.md
    `-- agents/
        `-- openai.yaml
```

## Install

Copy the `skill-selection-assistant/` folder from this repository into your local Codex skills directory.

Typical path:

```text
$CODEX_HOME/skills/skill-selection-assistant
```

On Windows for a common local setup:

```text
C:\Users\<YourUser>\.codex\skills\skill-selection-assistant
```

The skill should inspect the user's local Codex skills directory at runtime, not any repository author's personal path.

## Recommended AGENTS.md Rule

If you want this skill to run before normal requests, add a global instruction in your `AGENTS.md` telling Codex to:

1. inspect the local skills directory
2. use `skill-selection-assistant` first
3. recommend the best matching skills in the user's own language
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
3. Match the best 1-3 local skills.
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
- `skill-selection-assistant/agents/openai.yaml` to change agent metadata and default prompt behavior
- `INSTALLATION_BEHAVIOR.md` to document portable indexing or install/update behavior

## Release Notes

See [CHANGELOG.md](./CHANGELOG.md) for version history.

## License

MIT. See [LICENSE](./LICENSE).
