# Skill Selection Assistant

[![Release](https://img.shields.io/github/v/release/lhz1315937650/skill-selection-assistant)](https://github.com/lhz1315937650/skill-selection-assistant/releases)
[![Smoke Tests](https://github.com/lhz1315937650/skill-selection-assistant/actions/workflows/smoke-tests.yml/badge.svg)](https://github.com/lhz1315937650/skill-selection-assistant/actions/workflows/smoke-tests.yml)
[![License](https://img.shields.io/github/license/lhz1315937650/skill-selection-assistant)](./LICENSE)

[中文说明](./README.zh-CN.md) | English

A local, automatic skill router for large Codex skill libraries.

Skill Selection Assistant classifies installed skills when the index is built, stores the classification locally, and routes each request through only the relevant SQLite categories. Normal requests do not recursively reopen every `SKILL.md`, do not expose intermediate category questions, and return only the final weighted shortlist.

Selection follows four stages: lightweight Agent/project context, layered skill profiles with positive and negative examples, taxonomy routing, and bounded recall plus reranking fallback.

## Why It Exists

A flat library works for dozens of skills. It becomes slow and token-heavy when the library grows into the thousands: every request risks loading a huge catalog, inspecting unrelated skills, or asking the user to choose categories one level at a time.

This project treats skill selection like lazy loading in a frontend application:

1. Classify the complete library during installation, update, or explicit maintenance.
2. Store compact facets and candidate cards in a private local index.
3. Infer the request's route automatically.
4. Query only the active category path in SQLite.
5. Return the final matching skills and load a full `SKILL.md` only after selection.

## Key Features

- SQLite lazy routing for large local libraries.
- Automatic SQLite FTS5/BM25 recall and rerank fallback for weak taxonomy matches.
- Lightweight non-recursive project and business-context detection.
- Layered skill profiles with explicit positive and negative selection examples.
- Automatic domain, specialty, task, technology, output, and setup routing.
- No recursive source-library freshness scan during normal recommendations.
- No user-facing category-by-category questionnaire.
- Compact JSON output designed to reduce prompt and logging overhead.
- Multi-root discovery for user, system, or custom skill directories.
- Incremental reclassification during explicit index refreshes.
- Duplicate merging with meaningful same-name variants preserved.
- Local selection memory without storing raw queries by default.
- Python 3.10+ core with an optional PowerShell compatibility layer.

## Architecture

```text
Installation / update / explicit maintenance
    -> discover SKILL.md files
    -> classify and build local artifacts
    -> publish lazy-route.sqlite3

Normal request
    -> detect lightweight project and Agent context
    -> open existing SQLite index
    -> apply purpose, positive-example, and negative-example boundaries
    -> choose categories internally
    -> narrow the active candidate set
    -> read cards from the final route
    -> if confidence is weak: recall Top N cards globally and rerank
    -> return the final weighted skills
```

The default path never traverses all source skill files. A full source comparison runs only when explicitly requested or when an index must be created or repaired.

### Context And Layered Descriptions

The router inspects only bounded workspace signals: the current directory name, immediate `SKILL.md` markers, and top-level manifests such as `package.json`, `pyproject.toml`, `go.mod`, and `Cargo.toml`. It extracts project identity, recognized frameworks, and business signals, then gives exact project-to-skill identity matches higher weight.

During index construction, each skill receives a layered selection profile:

- `purpose`: the normal function summary.
- `selection_positive_examples`: explicit use cases, trigger phrases, and "when to use" examples.
- `selection_negative_examples`: explicit "when not to use" or "not suitable" examples.

Negative sections are excluded from positive capability classification. They reduce final relevance instead of accidentally adding unrelated tags.

### Recall And Rerank Fallback

The taxonomy route remains the fast primary path. Fallback activates automatically when no candidate is returned, the top score is weak, or too few candidates survive without a strong match. It performs a bounded FTS5/BM25 search over compact SQLite fields, recalls at most 30 cards by default, and reranks them with name, capability-tag, summary, origin, duplicate, and local selection-memory signals.

The fallback is local and deterministic. It does not reopen source `SKILL.md` files, call an embedding API, download a model, or scan the full filesystem.

## Performance

Verified on a Windows installation containing 11,595 skills:

| Entry point | Cold freshness-cache test | Storage | Full source scan |
|---|---:|---|---|
| Python | 2.408 s | `sqlite_lazy` | No |
| PowerShell | 3.345 s | `sqlite_lazy` | No |

The freshness cache was deleted before both requests and was not recreated, confirming that normal routing did not enumerate the source library.

## Install

Requirements: Python 3.10 or newer. PowerShell is optional.

```bash
git clone https://github.com/lhz1315937650/skill-selection-assistant.git
cd skill-selection-assistant
python scripts/install-skill.py
```

The installer copies the managed skill, discovers the configured skill roots, builds the private index, and runs a health check.

Enable automatic selection in Codex with a managed `AGENTS.md` block:

```bash
python scripts/install-skill.py --configure-agents
```

Useful installation commands:

```bash
# Preview without changing files
python scripts/install-skill.py --dry-run

# Update managed files while preserving the local index
python scripts/install-skill.py --force

# Check an existing installation
python scripts/install-skill.py --check

# Index more than one skill root
python scripts/install-skill.py --skills-root "<root-a>" --skills-root "<root-b>"
```

## Use

```bash
python scripts/recommend-skills.py \
  --query "build a modern React admin interface" \
  --compact
```

Normal output reaches the final shortlist directly:

```json
{
  "mode": "choose_skill",
  "storage_model": "sqlite_lazy",
  "selection_model": "multi_label_facet_intersection",
  "selection_pipeline": [
    "agent_context",
    "layered_skill_profile",
    "taxonomy_route",
    "recall_rerank_fallback"
  ],
  "context": {
    "project_name": "example-project",
    "technologies": ["react", "typescript"]
  },
  "index": {
    "freshness_policy": "explicit"
  },
  "branches": [],
  "fallback": {
    "triggered": false
  },
  "candidates": [
    {
      "name": "example-skill",
      "function_summary": "...",
      "score": 108
    }
  ]
}
```

PowerShell compatibility entry point:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/recommend-skills.ps1 `
  -Query "build a modern React admin interface"
```

Intermediate category branches are available only for taxonomy debugging:

```bash
python scripts/recommend-skills.py --query "frontend interface" --show-branches
```

## Index Maintenance

Normal selection uses the existing index. Rebuild or verify the source library only when the installed skills actually change or when diagnosing the index.

```bash
# Verify all configured roots before routing
python scripts/recommend-skills.py --query "health check" --strict-freshness

# Ignore a previous strict-check cache
python scripts/recommend-skills.py --query "health check" --force-freshness-check

# Diagnose the installed index
python scripts/doctor.py

# Repair missing, corrupt, incomplete, or outdated artifacts
python scripts/doctor.py --fix

# Force complete reclassification
python scripts/recommend-skills.py --query "health check" --full-rebuild
```

PowerShell uses `-StrictFreshness` for an explicit whole-library verification.

## Local Data

Runtime data lives under the installed skill's `.skill-index/` directory and is never included in releases:

- `deep/lazy-route.sqlite3`: default lazy-routing database.
- `deep/metadata.json`: schema, roots, counts, and build status.
- `deep/source-manifest.json`: source fingerprints and classification results.
- `deep/facets.json`: portable inverted classification facets.
- `deep/route-cards.json`: compact candidate metadata.
- `selection-memory.md`: privacy-first local ranking feedback.

## Development

```bash
python tests/run-python-smoke-tests.py
powershell -ExecutionPolicy Bypass -File tests/run-smoke-tests.ps1
powershell -ExecutionPolicy Bypass -File scripts/clean-local-artifacts.ps1
powershell -ExecutionPolicy Bypass -File scripts/package-release.ps1 -Version v1.10.0
```

Repository layout:

```text
skill-selection-assistant/
|-- scripts/                         installer, cleanup, and packaging tools
|-- skill-selection-assistant/       installable Codex skill
|   |-- scripts/                     classifier, router, doctor, and memory tools
|   |-- rules/                       shared classification rules
|   |-- schemas/                     recommendation output schema
|   `-- references/                  focused maintenance documentation
|-- tests/                           Python and PowerShell smoke tests
|-- INSTALLATION_BEHAVIOR.md         installation and portability contract
`-- SELF_GROWTH.md                   ranking and taxonomy improvement design
```

## Documentation

- [Installation and portability](./INSTALLATION_BEHAVIOR.md)
- [Self-growth design](./SELF_GROWTH.md)
- [Changelog](./CHANGELOG.md)
- [License](./LICENSE)
