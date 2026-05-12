# Skill Selection Assistant

[![Release](https://img.shields.io/github/v/release/lhz1315937650/skill-selection-assistant)](https://github.com/lhz1315937650/skill-selection-assistant/releases)
[![License](https://img.shields.io/github/license/lhz1315937650/skill-selection-assistant)](./LICENSE)

A Codex skill that checks the local skill library first, recommends the best matching skills in the user's own language, asks the user which one to use, and requires confirmation before any environment download, installation, or user-specific prerequisite configuration.

## Why This Skill Exists

When a Codex setup has many local skills, the model can easily:

- skip skill selection entirely
- list too many skills at once
- mix skill names with no practical explanation
- start installing dependencies without clearly asking first

This skill adds a lightweight skill-routing step before normal work begins.

## What It Does

- inspects the local skill library before continuing with a normal request
- selects the best `1-3` matching skills instead of dumping a long list
- introduces matched skills in the same language the user used
- asks the user which skill they want to use
- asks for confirmation before downloading or installing dependencies required by a selected skill
- asks follow-up setup questions when the selected skill still needs user-specific prerequisite configuration

## Repository Structure

```text
skill-selection-assistant/
├─ README.md
├─ LICENSE
├─ CHANGELOG.md
└─ skill-selection-assistant/
   ├─ SKILL.md
   └─ agents/
      └─ openai.yaml
```

## Install

Copy the `skill-selection-assistant/` folder from this repository into your local Codex skills directory.

Typical path:

```text
$CODEX_HOME/skills/skill-selection-assistant
```

On Windows for a default local setup:

```text
C:\Users\<YourUser>\.codex\skills\skill-selection-assistant
```

## Recommended AGENTS.md Rule

If you want this skill to run before normal requests, add a global instruction in your `AGENTS.md` telling Codex to:

1. inspect the local skills directory
2. use `skill-selection-assistant` first
3. recommend the best matching skills in the user's own language
4. ask the user to choose
5. ask before any environment download or installation
6. ask follow-up prerequisite configuration questions when the selected skill still needs user choices

Example:

```md
Before answering each new normal request:

1. Inspect the local skill library.
2. Use `skill-selection-assistant` first.
3. Match the best 1-3 local skills.
4. Briefly explain them in the same language the user used.
5. Ask the user which skill to use before continuing.
6. If a selected skill requires downloads or environment setup, ask for confirmation first.
7. If a selected skill still needs user-specific prerequisite configuration, ask those setup questions before execution.
```

## Behavior Summary

The skill is designed to be:

- skill-first, not keyword-spammy
- language-aware in the selection step
- conservative about environment setup
- explicit about prerequisite configuration before execution
- easy to customize for personal Codex workflows

## Customization

You can edit:

- `skill-selection-assistant/SKILL.md` to change matching logic or wording
- `skill-selection-assistant/agents/openai.yaml` to adjust display metadata

## Release Notes

See [CHANGELOG.md](./CHANGELOG.md) for version history.

## License

MIT. See [LICENSE](./LICENSE).
