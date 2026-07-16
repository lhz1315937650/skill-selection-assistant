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

- scan a publisher-specific path such as `C:\Users\<PublisherUser>\.codex\skills` as a product default
- depend on the publisher's username or filesystem layout
- assume that all users installed the same set of skills

## Per-User Offline Indexing

The installer copies the router skill into the user's local Codex skills directory, runs the compact compatibility scan, and builds the exhaustive deep index by default:

```bash
python scripts/install-skill.py
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install-skill.ps1
```

The Python installer is the preferred cross-platform entry point and requires Python 3.10 or newer. It copies the router, builds the deep Python index, and runs a recommendation health check. If PowerShell/pwsh is available, it also builds compatibility reports; otherwise, normal deep recommendations remain fully available.

An explicit Python `--codex-home` or PowerShell `-CodexHome` must also define the default scanned root as `<codex-home>/skills`. It must never silently fall back to another machine-default Codex home. Global `AGENTS.md` activation is opt-in through `--configure-agents` and must preserve unrelated instructions.

Managed-file updates must be staged and rollback-capable. They may replace only the published managed files while preserving `.skill-index/` and unrelated local content.

After a successful scan, installers should try to run `skill-selection-assistant/scripts/summarize-index.py` to generate `DETAILED_CLASSIFICATION.md`, `detailed-classification.json`, and `domain-task-matrix.csv`. If Python is unavailable in the PowerShell installer path, summary generation may be skipped without blocking installation.

It also includes a first-use / install-time scanner:

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
3. discover an unknown number of `SKILL.md` files across the configured skill roots
4. read each discovered skill in full and build a multi-label deep index
5. store every discovered path in a lightweight source manifest, including classification failures
6. on compatible refreshes, reclassify only added or modified sources and remove deleted sources
7. use the generated catalog only as a portable per-user runtime aid

If `recommend-skills.py` is run before an index exists, or when required routing artifacts are incomplete, corrupt, or from an old schema, it rebuilds the deep local index automatically without requiring PowerShell. It first recovers configured roots from the source manifest when possible. `recommend-skills.ps1` provides the equivalent PowerShell entry point and the legacy compact scanner fallback.

The catalog should reflect the user's actual installed skills across every configured root, because every user's local skill set may be different. Both installers accept repeated skills-root arguments.

Users can also diagnose and repair a first install with:

```powershell
powershell -ExecutionPolicy Bypass -File skill-selection-assistant/scripts/doctor.ps1 -Fix
```

With `-Fix`, doctor rebuilds a missing route summary and also attempts to regenerate the detailed classification summary when possible.

## Self-Growing Direction

The local index is not only a static catalog. It should support a self-growing loop:

1. new local skills are discovered by re-running the scanner
2. recurring user intents are recorded in `selection-memory.md`
3. poor or missed matches become category-improvement notes
4. repeated unmet workflows become suggestions for new skills
5. overlapping skills become link, merge, or `needs-review` suggestions
