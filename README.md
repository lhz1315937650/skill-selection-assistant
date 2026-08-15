# Skill Selection Assistant

[![Release](https://img.shields.io/github/v/release/lhz1315937650/skill-selection-assistant)](https://github.com/lhz1315937650/skill-selection-assistant/releases)
[![License](https://img.shields.io/github/license/lhz1315937650/skill-selection-assistant)](./LICENSE)

[中文](./README.zh-CN.md) | English

An automatic router for large local Codex skill libraries.

It discovers the installing user's own skills, builds a private multi-level index, walks the classification hierarchy internally, and presents only the final few matching skills. Users never need to classify their request one category at a time.

## Highlights

- Discovers one or more local skill roots.
- Reads and classifies each `SKILL.md` into a local multi-label index.
- Routes across domain, specialty, task, technology, output, and setup facets automatically.
- Lazily queries only the selected classification path through a local SQLite index.
- Returns only the final weighted candidates during normal use.
- Loads a full skill body only after that skill is selected.
- Keeps the selected skill active while the conversation remains in the same workflow.
- Requires confirmation before dependency downloads or user-owned configuration.
- Incrementally reclassifies added or changed skills instead of rebuilding everything.
- Merges exact duplicates while preserving meaningful same-name variants.
- Improves local ranking through privacy-first selection memory and self-growth reports.

## How It Works

```text
User request
    |
    v
Open the prebuilt local index
    |
    v
Automatic multi-level routing (internal)
    |
    v
Final 1-4 skill candidates
    |
    v
User selects and activates a skill
```

The internal index can use these facets:

```text
primary domain -> detailed domain -> specialty -> task -> technology -> output -> setup
```

These facets narrow the candidate pool internally. Normal usage never asks the user to choose them. The `--show-branches` option exists only for taxonomy maintenance and debugging.

Routing uses a local SQLite database by default. The reception step queries only category labels and counts. Each automatic category choice narrows a temporary candidate table once, and full candidate cards are read only after the route reaches its final leaf. Unselected categories are not decoded into Python objects and are never included in the model prompt.

## Quick Install

Python 3.10 or newer is required. PowerShell is optional and is used only by Windows compatibility tooling.

```bash
git clone https://github.com/lhz1315937650/skill-selection-assistant.git
cd skill-selection-assistant
python scripts/install-skill.py
```

The installer:

1. Copies the skill to `$CODEX_HOME/skills/skill-selection-assistant`.
2. Scans the installing user's configured skill roots.
3. Builds the private `.skill-index/deep/` index.
4. Runs a first recommendation health check.
5. Preserves local indexes, selection memory, and unrelated files during updates.

Preview without writing:

```bash
python scripts/install-skill.py --dry-run
```

Update an existing installation:

```bash
python scripts/install-skill.py --force
```

Check an installation:

```bash
python scripts/install-skill.py --check
```

Use a custom Codex home:

```bash
python scripts/install-skill.py --codex-home "<codex-home>"
```

Index multiple roots by repeating the option:

```bash
python scripts/install-skill.py --skills-root "<root-a>" --skills-root "<root-b>"
```

## Enable Automatic Selection

Installing the folder does not authorize global instruction changes. To run skill selection before normal requests, opt in explicitly:

```bash
python scripts/install-skill.py --configure-agents
```

This manages only a bounded block in `AGENTS.md` and preserves unrelated instructions. The generated rule tells Codex to:

- run the local recommender first
- keep intermediate categories internal
- present only the final weighted skills
- keep the chosen skill active for the current workflow

## Usage

Use the cross-platform Python entry point:

```bash
python scripts/recommend-skills.py --query "improve the interaction design of this React project" --compact
```

The default result reaches the final candidates in one command:

```json
{
  "schema_version": "3.0.0",
  "mode": "choose_skill",
  "branches": [],
  "candidates": [
    {
      "name": "example-skill",
      "function_summary": "...",
      "score": 108
    }
  ]
}
```

`route_trace` retains the automatically selected internal path for diagnostics. It is not intended as a user-facing selection interface.

Show the first category branches only when debugging the taxonomy:

```bash
python scripts/recommend-skills.py --query "improve this React project" --show-branches
```

The Windows PowerShell wrapper has the same default behavior:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/recommend-skills.ps1 -Query "improve this React project"
```

## Local Index

The installed skill stores private runtime data in `.skill-index/`:

- `deep/metadata.json`: schema, roots, counts, and classification status.
- `deep/source-manifest.json`: source fingerprints and classification outcomes.
- `deep/skills-deep-index.ndjson`: one classified skill record per line.
- `deep/facets.json`: multi-label inverted facets.
- `deep/route-cards.json`: compact routing metadata.
- `deep/lazy-route.sqlite3`: generated lazy-routing database used by normal requests.
- `DETAILED_CLASSIFICATION.md`: a human-readable local catalog.
- `domain-task-matrix.csv`: domain and task cross-tabulation.
- `selection-memory.md`: local routing feedback.

`.skill-index/` is never included in a release and should never be committed. This repository ships portable discovery, classification, and routing logic, not the publisher's skill list, absolute paths, or private index.

`facets.json` and `route-cards.json` remain portable source and audit artifacts. On first use, `lazy-index.py` converts them to SQLite without reading the original skill bodies. Later requests open the database and query only the active route. Use `--json-router` on `deep-route.py` only when testing the compatibility fallback.

## Index Lifecycle And Recovery

Classification happens during installation, update, or an explicit maintenance command. Normal recommendations validate required index artifacts, open SQLite, and query only the selected category path. They never recursively enumerate the source skill roots, even when an old freshness-cache timestamp has expired.

Use `--strict-freshness` when a request must block until every configured root has been compared with the source manifest. `--force-freshness-check` also enables strict mode and bypasses any previous strict-check cache. The PowerShell equivalent is `-StrictFreshness`.

Inspect the installed runtime:

```bash
python scripts/doctor.py
```

Repair it:

```bash
python scripts/doctor.py --fix
```

Request a complete reclassification:

```bash
python scripts/recommend-skills.py --query "health check" --strict-freshness
python scripts/recommend-skills.py --query "health check" --full-rebuild
```

Classification failures remain in the source manifest. Normal routing can continue in a degraded state with successfully classified skills; CI and audits can use the classifier's `--strict` option.

## Selection Memory And Self-Growth

Record a selection outcome:

```bash
python scripts/record-selection-memory.py \
  --query "build a frontend page" \
  --outcome selected \
  --selected-skill "frontend-design" \
  --route-type specialty \
  --category frontend-style-ui
```

Raw requests are not stored by default. Add `--store-query` only when local retention is acceptable.

Generate a local library report:

```bash
python scripts/self-grow.py
```

The report highlights oversized routes, duplicates, recurring work, missed matches, and possible skill gaps. It never edits the indexed skills automatically.

## Safety Boundaries

- No automatic dependency, model, or toolchain downloads.
- No assumptions about accounts, API keys, browser profiles, workspaces, or publishing targets.
- No modification of indexed skills.
- No publishing or committing local indexes.
- No publisher-specific paths or skill counts as runtime defaults.
- Managed-file updates are rollback-capable and preserve `.skill-index/`.

## Development And Tests

Cross-platform Python regression suite:

```bash
python tests/run-python-smoke-tests.py
```

Windows PowerShell regression suite:

```powershell
powershell -ExecutionPolicy Bypass -File tests/run-smoke-tests.ps1
```

The suites cover automatic final-candidate routing, explicit branch debugging, incremental indexes, duplicate handling, multiple roots, privacy-first memory, installation rollback, empty libraries, and index recovery.

Build a release package:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/package-release.ps1 -Version v1.8.1
```

## Repository Layout

```text
skill-selection-assistant/
|-- scripts/                         # installation, cleanup, and release
|-- tests/                           # Python and PowerShell regression suites
|-- skill-selection-assistant/
|   |-- SKILL.md                     # Codex skill instructions
|   |-- VERSION
|   |-- agents/openai.yaml
|   |-- rules/categories.json
|   |-- schemas/recommendation-v3.schema.json
|   |-- references/                  # progressively loaded maintenance docs
|   `-- scripts/                     # classification, routing, diagnostics, memory
|-- INSTALLATION_BEHAVIOR.md
|-- SELF_GROWTH.md
`-- CHANGELOG.md
```

Additional maintenance documentation:

- [Installation and portability](./INSTALLATION_BEHAVIOR.md)
- [Self-growth design](./SELF_GROWTH.md)
- [Changelog](./CHANGELOG.md)

## License

[MIT](./LICENSE)
