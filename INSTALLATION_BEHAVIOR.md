# Installation Behavior

This document explains the portability rule for `skill-selection-assistant`.

## Core Rule

This repository is published for different Codex users.

Therefore, any install-time or update-time scan must target the user's own local Codex skill installation, not the repository author's machine.

## Portable Skills Root

The intended portable skills root is:

```text
$CODEX_HOME/skills
```

On Windows, a common local example may look like:

```text
C:\Users\<YourUser>\.codex\skills
```

That example is documentation only. It is not a hardcoded runtime default.

## Two Different Local Paths

Do not confuse these two paths:

- `SkillInstanceDir`: where this `skill-selection-assistant` skill is installed.
- `SkillsRoot`: the installing user's full local Codex skill library that should be scanned and classified.

The generated `.skill-index/` belongs to the installed router skill instance, but its contents describe the installing user's own `SkillsRoot`.

The publisher may have a large local skill library during development. A downloader may have a much smaller or completely different library. Published behavior must work for both.

## What Must Not Happen

Published behavior must not:

- scan `C:\Users\Administrator\.codex\skills` as a product default
- depend on the publisher's username or filesystem layout
- assume that all users installed the same set of skills

## Future Offline Indexing Direction

The project now includes an optional first-use / install-time scanner:

```powershell
powershell -ExecutionPolicy Bypass -File skill-selection-assistant/scripts/scan-local-skills.ps1
```

The scanner writes local runtime artifacts to:

```text
skill-selection-assistant/.skill-index/
```

Those artifacts are intentionally ignored by git because they describe the installing user's local skill library.

The intended behavior is:

1. resolve the user's local Codex home or skills root from the runtime environment
2. scan that installed local skill directory
3. build a lightweight local catalog of installed skills
4. use that catalog only as a portable per-user runtime aid

The catalog should reflect the user's actual installed skills, because every user's local skill set may be different.

## Self-Growing Direction

The local index is not only a static catalog. It should support a self-growing loop:

1. new local skills are discovered by re-running the scanner
2. recurring user intents are recorded in `selection-memory.md`
3. poor or missed matches become category-improvement notes
4. repeated unmet workflows become suggestions for new skills
5. overlapping skills become link, merge, or `needs-review` suggestions
