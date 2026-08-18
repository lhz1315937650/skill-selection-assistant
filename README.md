# Skill Selection Assistant

[![Release](https://img.shields.io/github/v/release/lhz1315937650/skill-selection-assistant)](https://github.com/lhz1315937650/skill-selection-assistant/releases)
[![Tests](https://github.com/lhz1315937650/skill-selection-assistant/actions/workflows/smoke-tests.yml/badge.svg)](https://github.com/lhz1315937650/skill-selection-assistant/actions/workflows/smoke-tests.yml)
[![License](https://img.shields.io/github/license/lhz1315937650/skill-selection-assistant)](./LICENSE)

[中文](./README.zh-CN.md) | English

A fast, local skill router for large Codex skill libraries. It narrows a request to the most relevant skills without scanning every source `SKILL.md`.

## Mechanism

1. **Classify the request** from the project context, task intent, domain, and technology signals.
2. **Route by taxonomy** through layers such as domain, specialty, task type, and tech stack.
3. **Lazy-load the route** so only the selected category is inspected; unrelated skills stay untouched.
4. **Score and rerank candidates** using tags, positive examples, and negative examples.
5. **Fallback with SQLite FTS5/BM25** when the route is weak, then rerank the recalled results.
6. **Return only the final candidates** instead of asking the user to choose from every category.

```text
Request -> context -> category route -> lazy load -> score/rerank -> BM25 fallback -> final skills
```

## Features

- SQLite lazy routing for large skill libraries.
- Project-aware classification.
- Positive and negative skill examples.
- BM25 recall and reranking fallback.
- Local-only operation; no embedding API or model download.

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

## Maintenance

```bash
python scripts/doctor.py
python scripts/doctor.py --fix
python tests/run-python-smoke-tests.py
```

Local indexes are stored in `.skill-index/` and are not included in releases.

## License

[MIT](./LICENSE)
