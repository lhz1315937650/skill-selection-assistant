# Installation And First-Use Reference

Read this reference only for installation, update, activation, diagnostics, or removal work.

## Requirements

- Python 3.10 or newer
- write access to the selected Codex home
- optional PowerShell/pwsh for compatibility reports

## Plan Before Writing

```bash
python scripts/install-skill.py --dry-run
```

The plan should show the resolved destination, every configured skills root, discovered file count, PowerShell availability, activation target, and version.

## Install

```bash
python scripts/install-skill.py
```

Machine-readable automation:

```bash
python scripts/install-skill.py --json
```

Use `python3` on systems without a `python` alias, or `py -3` on Windows when appropriate.

## Custom Codex Home And Multiple Roots

```bash
python scripts/install-skill.py --codex-home "<codex home>"
python scripts/install-skill.py --skills-root "<root one>" --skills-root "<root two>"
```

When `--codex-home` is explicit and no roots are supplied, scan `<codex-home>/skills`. Do not fall back to another machine-default Codex home.

## Opt-In Global Activation

```bash
python scripts/install-skill.py --configure-agents
```

This appends a bounded managed block and preserves unrelated `AGENTS.md` content. Never write this block without explicit authorization.

## Update And Check

```bash
python scripts/install-skill.py --force
python scripts/install-skill.py --check
```

Managed updates use a staged, rollback-capable transaction. Preserve `.skill-index/` and unrelated local files even if managed-file publication fails.

After deleting the downloaded repository, run the installed cross-platform doctor directly:

```bash
python "<installed skill>/scripts/doctor.py"
python "<installed skill>/scripts/doctor.py" --fix
```

Use `--fix` for missing, incomplete, corrupt, stale, or old-schema deep indexes. Repeat `--skills-root` for nonstandard multi-root recovery.

Updates replace managed files (`SKILL.md`, `VERSION`, `agents/`, `rules/`, `references/`, `schemas/`, and `scripts/`) while preserving `.skill-index/`.

## Optional Modes

- `--skip-scan`: copy only; skip all indexing
- `--skip-deep-index`: run only the PowerShell compatibility scan
- `--no-health-check`: skip the first recommendation self-test
- `--debug`: include tracebacks for maintainers

## Empty Libraries

An empty library is valid. Installation health should pass with `mode=no_skills_installed`, and the user should be offered direct answering, skill installation, or skill creation.

## Removal

There is no automatic destructive uninstall. Remove the installed router directory and its managed `AGENTS.md` block only after the user explicitly requests removal. Preserve unrelated skills and global instructions.
