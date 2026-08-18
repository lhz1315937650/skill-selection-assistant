# Skill Selection Assistant

[![Release](https://img.shields.io/github/v/release/lhz1315937650/skill-selection-assistant)](https://github.com/lhz1315937650/skill-selection-assistant/releases)
[![Tests](https://github.com/lhz1315937650/skill-selection-assistant/actions/workflows/smoke-tests.yml/badge.svg)](https://github.com/lhz1315937650/skill-selection-assistant/actions/workflows/smoke-tests.yml)
[![License](https://img.shields.io/github/license/lhz1315937650/skill-selection-assistant)](./LICENSE)

[中文](./README.zh-CN.md) | English

A fast, local skill router for large Codex skill libraries.

It classifies skills during indexing, uses project context to select relevant categories, and returns only the final candidates. Normal requests never scan every source `SKILL.md`.

## Features

- Context-aware routing from project identity and technology signals.
- Positive and negative examples for clearer skill boundaries.
- SQLite lazy loading for the selected classification path.
- BM25 recall and reranking fallback for weak matches.
- Local-only operation with no embedding API or model download.

## Flow

```text
Project context
    -> layered skill profile
    -> taxonomy routing
    -> recall and rerank fallback
    -> final candidates
```

## Install

Requires Python 3.10+.

```bash
git clone https://github.com/lhz1315937650/skill-selection-assistant.git
cd skill-selection-assistant
python scripts/install-skill.py --configure-agents
```

Update an existing installation:

```bash
python scripts/install-skill.py --force
```

## Use

```bash
python scripts/recommend-skills.py \
  --query "build a modern React admin interface" \
  --compact
```

The result contains the final weighted skills, selected route, project context, and fallback status.

## Maintenance

```bash
# Diagnose the installed index
python scripts/doctor.py

# Repair or rebuild it
python scripts/doctor.py --fix

# Run tests
python tests/run-python-smoke-tests.py
powershell -ExecutionPolicy Bypass -File tests/run-smoke-tests.ps1
```

Local indexes are stored in `.skill-index/` and are never included in releases.

## License

[MIT](./LICENSE)
