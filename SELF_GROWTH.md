# Self-Growing Skill Library

`skill-selection-assistant` is intended to make a user's local Codex skill library self-growing.

## What self-growing means

The skill library should not stay as a static list of folders. It should continuously improve through:

- install-time or first-use local scanning
- multi-level classification
- concise skill recommendations in the user's language
- local selection memory
- missed-match notes
- new skill suggestions for repeated workflows
- review suggestions for overlapping or stale skills

## Generated local files

The scanner writes local runtime artifacts to:

```text
skill-selection-assistant/.skill-index/
|-- skills-index.json
|-- skills-categories.md
`-- selection-memory.md
```

These files describe the installing user's local skill library and should not be committed by default.

## Growth loop

1. Scan the user's local skills root.
2. Build or refresh the classified skill index.
3. Use the index to recommend the best `1-3` skills.
4. Record useful matches and missed matches.
5. Suggest new skills when repeated workflows are not covered.
6. Suggest link, merge, or review actions when skills overlap.
7. Re-scan after new skills are installed.

## Safety rules

- Do not delete local skills automatically.
- Do not overwrite another skill's `SKILL.md` without explicit user permission.
- Do not hardcode the publisher's filesystem path.
- Treat the user's local installation as the source of truth.
