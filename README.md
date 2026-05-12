# Skill Selection Assistant

A Codex skill that checks the local skill library first, recommends the best matching skills in simple Chinese, asks the user which one to use, and confirms before any required environment download or installation.

## What It Does

- inspects local skills before continuing with a normal request
- selects the best `1-3` matching skills instead of dumping a long list
- introduces matched skills in simple Chinese
- asks the user which skill to use
- asks for confirmation before downloading or installing dependencies required by a selected skill

## Repository Structure

```text
skill-selection-assistant/
├─ README.md
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

## Recommended Global Rule

If you want this skill to run before normal requests, add a global instruction in your `AGENTS.md` telling Codex to:

1. inspect the local skills directory
2. use `skill-selection-assistant` first
3. recommend the best matching skills in Chinese
4. ask the user to choose
5. ask before any environment download or installation

## Notes

- This repository contains a single reusable skill.
- The skill is optimized for Chinese-language selection prompts.
- You can customize the wording in `SKILL.md` for your own workflow.
