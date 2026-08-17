#!/usr/bin/env python3
"""Traverse the exhaustive hospital-style skill hierarchy one category at a time."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


GENERIC_NAME_ROUTE_TOKENS = {
    "api", "app", "code", "data", "design", "file", "frontend", "help", "skill",
    "test", "tool", "web", "workflow", "ci", "css", "html", "js", "md", "ui",
}
DEFAULT_FRESHNESS_CACHE_SECONDS = 300


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


class LazyRouteStore:
    def __init__(self, database: Path):
        self.connection = sqlite3.connect(database)
        self.connection.row_factory = sqlite3.Row
        self.selected: dict[str, str] = {}
        self.connection.execute("CREATE TEMP TABLE active_candidates (skill_id TEXT PRIMARY KEY) WITHOUT ROWID")
        self.connection.execute("INSERT INTO active_candidates(skill_id) SELECT skill_id FROM cards")

    def close(self) -> None:
        self.connection.close()

    def select(self, selected: dict[str, str]) -> None:
        current_items = list(self.selected.items())
        requested_items = list(selected.items())
        common = 0
        while common < min(len(current_items), len(requested_items)) and current_items[common] == requested_items[common]:
            common += 1
        if common != len(current_items):
            self.connection.execute("DELETE FROM active_candidates")
            self.connection.execute("INSERT INTO active_candidates(skill_id) SELECT skill_id FROM cards")
            self.selected = {}
            common = 0
        for level, label in requested_items[common:]:
            exists = self.connection.execute(
                "SELECT 1 FROM facet_memberships WHERE level = ? AND label = ? LIMIT 1",
                (level, label),
            ).fetchone()
            if exists is None:
                raise KeyError(f"Facet not found: {level}={label}")
            self.connection.execute(
                """DELETE FROM active_candidates
                   WHERE skill_id NOT IN (
                       SELECT skill_id FROM facet_memberships WHERE level = ? AND label = ?
                   )""",
                (level, label),
            )
            self.selected[level] = label

    def levels(self) -> list[str]:
        return [str(row[0]) for row in self.connection.execute("SELECT name FROM levels ORDER BY position")]

    def candidate_count(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) FROM active_candidates").fetchone()
        return int(row[0])

    def branches(self, level: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """SELECT fm.label, COUNT(*) AS count
                FROM facet_memberships fm
                JOIN active_candidates active ON active.skill_id = fm.skill_id
                WHERE fm.level = ?
                GROUP BY fm.label""",
            (level,),
        )
        return [{"level": level, "name": str(row["label"]), "display_name": str(row["label"]), "count": int(row["count"])} for row in rows]

    def name_matching_labels(
        self,
        level: str,
        query_tokens: set[str],
    ) -> set[str]:
        useful = sorted({token.lower() for token in query_tokens if token not in GENERIC_NAME_ROUTE_TOKENS and len(token) >= 3})
        if not useful:
            return set()
        name_clauses = " OR ".join("LOWER(c.canonical_name) LIKE ?" for _ in useful)
        rows = self.connection.execute(
            f"""SELECT DISTINCT fm.label
                FROM facet_memberships fm
                JOIN cards c ON c.skill_id = fm.skill_id
                JOIN active_candidates active ON active.skill_id = c.skill_id
                WHERE fm.level = ? AND ({name_clauses})""",
            [level, *[f"%{token}%" for token in useful]],
        )
        return {str(row[0]) for row in rows}

    def cards(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT c.* FROM cards c JOIN active_candidates active ON active.skill_id = c.skill_id"
        )
        return self._decode_cards(rows)

    def recall_cards(self, query_tokens: set[str], limit: int) -> list[dict[str, Any]]:
        useful = sorted(
            {token.lower() for token in query_tokens if len(token.strip()) >= 2},
            key=lambda token: (token in GENERIC_NAME_ROUTE_TOKENS, -len(token), token),
        )[:24]
        if not useful:
            return []
        match_query = " OR ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in useful)
        try:
            rows = self.connection.execute(
                """SELECT c.*, bm25(cards_fts, 0.0, 8.0, 3.0, 5.0) AS recall_rank
                   FROM cards_fts
                   JOIN cards c ON c.skill_id = cards_fts.skill_id
                   WHERE cards_fts MATCH ?
                   ORDER BY recall_rank
                   LIMIT ?""",
                (match_query, max(1, limit)),
            )
            return self._decode_cards(rows)
        except sqlite3.OperationalError:
            clauses = " OR ".join(
                "LOWER(name) LIKE ? OR LOWER(function_summary) LIKE ? OR LOWER(capability_tags) LIKE ?"
                for _ in useful
            )
            parameters: list[Any] = []
            for token in useful:
                pattern = f"%{token}%"
                parameters.extend((pattern, pattern, pattern))
            parameters.append(max(1, limit))
            rows = self.connection.execute(
                f"SELECT * FROM cards WHERE {clauses} LIMIT ?",
                parameters,
            )
            return self._decode_cards(rows)

    @staticmethod
    def _decode_cards(rows: Any) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["capability_tags"] = json.loads(item.pop("capability_tags"))
            item["setup_requirements"] = json.loads(item.pop("setup_requirements"))
            result.append(item)
        return result


def lazy_database_is_current(database: Path, deep_dir: Path) -> bool:
    if not database.exists():
        return False
    try:
        signature_parts = []
        for name in ("facets.json", "route-cards.json"):
            stat = (deep_dir / name).stat()
            signature_parts.append(f"{name}:{stat.st_size}:{stat.st_mtime_ns}")
        signature = "|".join(signature_parts)
        with sqlite3.connect(database) as connection:
            values = dict(connection.execute("SELECT key, value FROM metadata"))
        return values.get("schema_version") == "1.1.0" and values.get("source_signature") == signature
    except (OSError, sqlite3.Error):
        return False


def ensure_lazy_database(deep_dir: Path, script_dir: Path) -> Path | None:
    database = deep_dir / "lazy-route.sqlite3"
    if lazy_database_is_current(database, deep_dir):
        return database
    builder = script_dir / "lazy-index.py"
    if not builder.exists():
        return None
    result = subprocess.run(
        [sys.executable, str(builder), "--index-dir", str(deep_dir.parent), "--compact"],
        text=True,
        capture_output=True,
        check=False,
    )
    return database if result.returncode == 0 and lazy_database_is_current(database, deep_dir) else None


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_index_freshness(
    metadata: dict[str, Any],
    deep_dir: Path,
    cache_seconds: int = DEFAULT_FRESHNESS_CACHE_SECONDS,
    force: bool = False,
) -> dict[str, Any]:
    source_path = deep_dir / "source-manifest.json"
    if not source_path.exists():
        return {"fresh": False, "reason": "source_manifest_missing"}
    cache_path = deep_dir / ".freshness-cache.json"
    source_stat = source_path.stat()
    cache_key = {
        "source_manifest_mtime_ns": source_stat.st_mtime_ns,
        "source_manifest_size": source_stat.st_size,
        "rules_fingerprint": str(metadata.get("rules_fingerprint") or ""),
        "classifier_fingerprint": str(metadata.get("classifier_fingerprint") or ""),
    }
    if not force and cache_seconds > 0 and cache_path.exists():
        try:
            cached = load_json(cache_path)
            checked_at = float(cached.get("checked_at") or 0)
            if cached.get("cache_key") == cache_key and time.time() - checked_at <= cache_seconds:
                result = dict(cached.get("result") or {})
                result["cached"] = True
                return result
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

    def finish(result: dict[str, Any]) -> dict[str, Any]:
        result["cached"] = False
        try:
            cache_path.write_text(json.dumps({
                "checked_at": time.time(),
                "cache_key": cache_key,
                "result": result,
            }, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        return result

    source = load_json(source_path)
    excluded = {os.path.normcase(str(Path(value).resolve())) for value in source.get("excluded_paths", [])}
    expected = {
        os.path.normcase(str(Path(entry["skill_md"]).resolve())): entry
        for entry in source.get("files", [])
        if entry.get("skill_md")
    }
    current: dict[str, Path] = {}
    for value in source.get("skills_roots", []):
        root = Path(value).expanduser().resolve()
        if not root.is_dir():
            return finish({"fresh": False, "reason": "skills_root_missing", "path": str(root)})
        for candidate in root.rglob("SKILL.md"):
            resolved = candidate.resolve()
            key = os.path.normcase(str(resolved))
            if key not in excluded:
                current[key] = resolved
    if set(current) != set(expected):
        return finish({
            "fresh": False,
            "reason": "skill_set_changed",
            "added": len(set(current) - set(expected)),
            "removed": len(set(expected) - set(current)),
        })
    for key, path in current.items():
        stat = path.stat()
        entry = expected[key]
        if stat.st_size != int(entry.get("file_length") or -1) or stat.st_mtime_ns != int(entry.get("last_write_ns") or -1):
            return finish({"fresh": False, "reason": "skill_file_changed", "path": str(path)})
    rules_path = Path(str(metadata.get("rules_path") or ""))
    if not rules_path.is_file() or sha256_file(rules_path) != str(metadata.get("rules_fingerprint") or ""):
        return finish({"fresh": False, "reason": "classification_rules_changed"})
    classifier_path = Path(str(metadata.get("classifier_path") or ""))
    if not classifier_path.is_file() or sha256_file(classifier_path) != str(metadata.get("classifier_fingerprint") or ""):
        return finish({"fresh": False, "reason": "classifier_changed"})
    return finish({"fresh": True, "reason": ""})


def load_selection_memory(index_dir: Path, selected: dict[str, str]) -> dict[str, int]:
    memory_path = index_dir / "selection-memory.md"
    if not memory_path.exists():
        return {}
    selected_labels = set(selected.values())
    scores: dict[str, int] = {}
    for block in re.split(r"(?m)^###\s+", memory_path.read_text(encoding="utf-8-sig", errors="ignore")):
        outcome_match = re.search(r"(?m)^- outcome:\s+`?([^`\n]+)`?", block)
        skill_match = re.search(r"(?m)^- selected_skill:\s+`?([^`\n]+)`?", block)
        route_match = re.search(r"(?m)^- route:\s+`?([^`\n]+)`?\s*/\s*`?([^`\n]+)`?", block)
        if not outcome_match or not skill_match:
            continue
        category = route_match.group(2).strip() if route_match else ""
        if category:
            if not selected_labels:
                continue
            if category not in selected_labels and not any(label in category for label in selected_labels):
                continue
        amount = {"selected": 12, "missed": 4, "rejected": -12, "setup-failed": -8}.get(outcome_match.group(1).strip(), 0)
        name = re.sub(r"[^\w\u4e00-\u9fff]+", "-", skill_match.group(1).strip().lower()).strip("-")
        scores[name] = max(-30, min(30, scores.get(name, 0) + amount))
    return scores


def tokens(text: str) -> set[str]:
    values = set(re.findall(r"[a-zA-Z0-9_+.-]{2,}|[\u4e00-\u9fff]{2,}", text.lower()))
    cjk = "".join(re.findall(r"[\u4e00-\u9fff]", text))
    values.update(cjk[i : i + 2] for i in range(max(0, len(cjk) - 1)))
    return values


def find_node(root: dict[str, Any], path: str) -> dict[str, Any]:
    node = root
    if not path:
        return node
    for segment in [value for value in path.split("|") if value]:
        if "=" not in segment:
            raise ValueError(f"Invalid path segment: {segment}")
        level, name = segment.split("=", 1)
        match = next((child for child in node.get("children", []) if child.get("level") == level and child.get("name") == name), None)
        if match is None:
            raise KeyError(f"Category path not found at {segment}")
        node = match
    return node


def flatten_skill_ids(node: dict[str, Any]) -> list[str]:
    result = list(node.get("skill_ids", []))
    for child in node.get("children", []):
        result.extend(flatten_skill_ids(child))
    return result


def read_cards(path: Path) -> dict[str, dict[str, Any]]:
    cards: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            if line.strip():
                item = json.loads(line)
                cards[item["skill_id"]] = item
    return cards


def regex_matches(pattern: str, query: str) -> bool:
    try:
        return re.search(pattern, query, re.IGNORECASE) is not None
    except re.error:
        return False


def chinese_alias_score(level: str, label: str, query: str, keywords: dict[str, Any]) -> int:
    map_name = {
        "domain_detail": "query_cn_detail_words",
        "specialty": "query_cn_specialty_words",
        "task_type": "query_cn_task_words",
    }.get(level, "")
    aliases = keywords.get(map_name, {}).get(label, []) if map_name else []
    matched = {str(alias).lower() for alias in aliases if str(alias).lower() in query.lower()}
    return min(360, 120 * len(matched))


def direct_label_score(level: str, label: str, query: str, keywords: dict[str, Any]) -> int:
    score = chinese_alias_score(level, label, query, keywords)
    pattern = str(keywords.get(level, {}).get(label, ""))
    if pattern and regex_matches(pattern, query):
        score += 100
    if level == "setup_level":
        aliases = {
            "api-key": ["api key", "apikey", "密钥", "令牌"],
            "account": ["账号", "登录", "oauth", "workspace"],
            "network": ["联网", "下载", "网络"],
            "local-runtime": ["依赖", "运行环境", "安装", "runtime"],
            "none": ["本地", "无需配置"],
        }
        if any(alias in query.lower() for alias in aliases.get(label, [])):
            score += 80
    return score


def branch_score(
    branch: dict[str, Any],
    query: str,
    query_tokens: set[str],
    raw_query_tokens: set[str],
    keywords: dict[str, Any],
) -> int:
    score = semantic_label_score(branch, query, query_tokens, keywords)
    descendant_names = [str(value).lower() for value in branch.get("search_terms", [])]
    if descendant_names:
        name_parts: set[str] = set()
        for value in descendant_names:
            name_parts.update(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", value))
            name_parts.add(re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value))
        for token in raw_query_tokens:
            normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", token.lower())
            if normalized and normalized not in GENERIC_NAME_ROUTE_TOKENS and normalized in name_parts:
                score += 160
    return score


def semantic_label_score(
    branch: dict[str, Any],
    query: str,
    query_tokens: set[str],
    keywords: dict[str, Any],
) -> int:
    haystack = f"{branch.get('name', '')} {branch.get('display_name', '')}".lower()
    score = sum(12 for token in query_tokens if token not in GENERIC_NAME_ROUTE_TOKENS and token in haystack)
    level = str(branch.get("level") or "")
    label = str(branch.get("name") or "")
    score += direct_label_score(level, label, query, keywords)
    if level == "primary_domain":
        primary_map = keywords.get("primary_map", {})
        detail_scores: list[int] = []
        for detail_label, primary_label in primary_map.items():
            if str(primary_label) == label:
                detail_scores.append(direct_label_score("domain_detail", str(detail_label), query, keywords))
        if detail_scores:
            score += max(detail_scores)
    return score


def skill_score(card: dict[str, Any], query_tokens: set[str], raw_query_tokens: set[str]) -> int:
    name = str(card.get("name") or "").lower()
    name_parts = set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", name))
    summary = str(card.get("function_summary") or "").lower()
    tags = " ".join(card.get("capability_tags") or []).lower()
    score = 0
    for token in raw_query_tokens:
        if token in GENERIC_NAME_ROUTE_TOKENS:
            continue
        if token in name_parts:
            score += 60
        elif len(token) >= 4 and token in name:
            score += 30
    for token in query_tokens:
        if token in name_parts:
            score += 18
        elif token in tags:
            score += 8
        elif token in summary:
            score += 4
    score += {"user-local": 8, "official-system": 6, "installed-topic": 4, "linked-external": 2}.get(card.get("origin"), 0)
    score -= min(6, int(card.get("exact_duplicate_count") or 1) - 1)
    return score


def expand_query_tokens(query: str, keywords: dict[str, Any]) -> set[str]:
    """Translate matched Chinese routing intent into the index's internal labels."""
    result = tokens(query)
    for level in ("domain_detail", "specialty", "task_type", "output_type", "tech_stack"):
        labels = set(keywords.get(level, {}))
        alias_map = {
            "domain_detail": "query_cn_detail_words",
            "specialty": "query_cn_specialty_words",
            "task_type": "query_cn_task_words",
        }.get(level)
        if alias_map:
            labels.update(keywords.get(alias_map, {}))
        for label in labels:
            label = str(label)
            if direct_label_score(level, label, query, keywords) > 0:
                result.add(label.lower())
                result.update(part for part in re.split(r"[-_]+", label.lower()) if len(part) >= 2)
    return result


def dynamic_window(items: list[dict[str, Any]], limit: int, window: int, minimum: int, score_key: str = "query_score") -> list[dict[str, Any]]:
    if not items:
        return []
    top_score = int(items[0].get(score_key) or 0)
    if top_score <= 0:
        return items[: min(limit, max(minimum, 5))]
    selected = [item for item in items if int(item.get(score_key) or 0) >= top_score - window][:limit]
    if len(selected) < minimum:
        selected = items[: min(limit, minimum)]
    return selected


def partition_catalog(skill_ids: set[str], cards: dict[str, dict[str, Any]], leaf_target: int) -> list[list[str]]:
    ordered = sorted(skill_ids, key=lambda skill_id: (cards[skill_id].get("canonical_name", ""), skill_id))
    if len(ordered) <= leaf_target:
        return [ordered]
    chunk_size = max(leaf_target, math.ceil(len(ordered) / 8))
    return [ordered[start : start + chunk_size] for start in range(0, len(ordered), chunk_size)]


def parse_facet_path(
    path: str,
    facets: dict[str, Any],
    cards: dict[str, dict[str, Any]],
    leaf_target: int,
) -> tuple[set[str], dict[str, str], list[tuple[int, int]]]:
    selected: dict[str, str] = {}
    shards: list[tuple[int, int]] = []
    candidate_ids = set(facets.get("all_skill_ids", []))
    shard_started = False
    for segment in [value for value in path.split("|") if value]:
        if "=" not in segment:
            raise ValueError(f"Invalid path segment: {segment}")
        level, label = segment.split("=", 1)
        shard_match = re.fullmatch(r"catalog_shard_(\d+)", level)
        if shard_match:
            shard_started = True
            depth = int(shard_match.group(1))
            index = int(label)
            expected_depth = len(shards) + 1
            if depth != expected_depth:
                raise ValueError(f"Expected catalog_shard_{expected_depth}, got {level}")
            groups = partition_catalog(candidate_ids, cards, leaf_target)
            if index < 1 or index > len(groups):
                raise KeyError(f"Catalog shard not found: {segment}")
            candidate_ids = set(groups[index - 1])
            shards.append((depth, index))
            continue
        if shard_started:
            raise ValueError("Semantic facet segments cannot follow catalog shards")
        if level in selected:
            raise ValueError(f"Facet level selected more than once: {level}")
        label_ids = facets.get("facets", {}).get(level, {}).get(label)
        if label_ids is None:
            raise KeyError(f"Facet not found: {segment}")
        candidate_ids.intersection_update(label_ids)
        selected[level] = label
    return candidate_ids, selected, shards


def matched_tags(card: dict[str, Any], query_tokens: set[str], selected: dict[str, str]) -> list[str]:
    result = list(dict.fromkeys(selected.values()))
    for tag in card.get("capability_tags") or []:
        lowered = str(tag).lower()
        parts = {value for value in re.split(r"[-_]+", lowered) if len(value) >= 2}
        if lowered in query_tokens or parts.intersection(query_tokens):
            result.append(str(tag))
    return list(dict.fromkeys(result))[:8]


def parse_selected_facets(path: str) -> dict[str, str]:
    selected: dict[str, str] = {}
    for segment in [value for value in path.split("|") if value]:
        if "=" not in segment:
            raise ValueError(f"Invalid path segment: {segment}")
        level, label = segment.split("=", 1)
        if level.startswith("catalog_shard_"):
            raise ValueError("Catalog shards require the JSON compatibility router")
        if level in selected:
            raise ValueError(f"Facet level selected more than once: {level}")
        selected[level] = label
    return selected


def rank_final_cards(
    args: argparse.Namespace,
    cards: list[dict[str, Any]],
    query_tokens: set[str],
    raw_query_tokens: set[str],
    selected: dict[str, str],
    index_dir: Path,
) -> tuple[list[dict[str, Any]], int, int]:
    memory_scores = load_selection_memory(index_dir, selected)
    cards.sort(key=lambda item: (
        -(skill_score(item, query_tokens, raw_query_tokens) + memory_scores.get(str(item.get("canonical_name") or ""), 0)),
        item.get("name", ""),
    ))
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in cards:
        grouped.setdefault(str(item.get("canonical_name") or item.get("name") or ""), []).append(item)
    visible = [variants[0] for variants in grouped.values()]
    scored_visible = []
    for item in visible:
        memory_score = memory_scores.get(str(item.get("canonical_name") or ""), 0)
        scored_visible.append({
            "card": item,
            "score": skill_score(item, query_tokens, raw_query_tokens) + memory_score,
            "memory_score": memory_score,
        })
    if scored_visible:
        top_score = scored_visible[0]["score"]
        if top_score > 0:
            returned = [item for item in scored_visible if item["score"] >= top_score - args.candidate_score_window][: args.limit]
            target_minimum = min(3, args.limit, len(scored_visible))
            if len(returned) < target_minimum:
                returned_ids = {str(item["card"].get("skill_id") or "") for item in returned}
                for item in scored_visible:
                    skill_id = str(item["card"].get("skill_id") or "")
                    if skill_id in returned_ids:
                        continue
                    returned.append(item)
                    returned_ids.add(skill_id)
                    if len(returned) >= target_minimum:
                        break
        else:
            returned = scored_visible[: args.limit]
    else:
        returned = []
    result_candidates: list[dict[str, Any]] = []
    for entry in returned:
        item = entry["card"]
        tags = list(item.get("capability_tags") or [])
        candidate = {
            "name": item["name"],
            "function_summary": item.get("function_summary", "") if args.verbose else item.get("function_summary", "")[:220],
            "matched_tags": matched_tags(item, query_tokens, selected),
            "tag_count": len(tags),
            "setup_level": item.get("setup_level", "unknown"),
            "setup_requirements": item.get("setup_requirements") or [item.get("setup_level", "unknown")],
            "origin": item.get("origin", "unknown"),
            "skill_md": item.get("skill_md", ""),
            "logical_skill_md": item.get("logical_skill_md") or item.get("skill_md", ""),
            "visible_variant_count": len(grouped[str(item.get("canonical_name") or item.get("name") or "")]),
            "score": entry["score"],
        }
        if entry["memory_score"]:
            candidate["memory_score"] = entry["memory_score"]
        if args.verbose:
            candidate["capability_tags"] = tags
        result_candidates.append(candidate)
    return result_candidates, len(visible), len(cards)


def fallback_trigger_reason(args: argparse.Namespace, result: dict[str, Any]) -> str:
    if args.disable_fallback:
        return ""
    if args.force_fallback:
        return "forced"
    if result.get("mode") not in {"choose_skill", "no_skills_installed"}:
        return ""
    candidates = list(result.get("candidates") or [])
    if not candidates:
        return "no_candidates"
    top_score = max(int(item.get("score") or 0) for item in candidates)
    if top_score < args.fallback_min_score:
        return "low_top_score"
    if len(candidates) < args.fallback_min_candidates and top_score < args.fallback_strong_score:
        return "insufficient_candidates"
    return ""


def apply_recall_fallback(
    args: argparse.Namespace,
    result: dict[str, Any],
    store: LazyRouteStore,
    keywords: dict[str, Any],
    index_dir: Path,
) -> dict[str, Any]:
    reason = fallback_trigger_reason(args, result)
    if not reason:
        result["fallback"] = {"triggered": False}
        return result

    raw_query_tokens = tokens(args.query)
    query_tokens = expand_query_tokens(args.query, keywords)
    recalled = store.recall_cards(query_tokens.union(raw_query_tokens), args.fallback_recall_limit)
    original_candidates = list(result.get("candidates") or [])
    fallback_info = {
        "triggered": True,
        "applied": bool(recalled),
        "reason": reason,
        "recall_model": "sqlite_fts5_bm25",
        "rerank_model": "query_name_tag_summary_memory",
        "recall_limit": args.fallback_recall_limit,
        "recalled_candidates": len(recalled),
        "original_returned_candidates": len(original_candidates),
        "original_top_score": max((int(item.get("score") or 0) for item in original_candidates), default=0),
    }
    if not recalled:
        result["fallback"] = fallback_info
        return result

    candidates, candidate_pool, content_variant_pool = rank_final_cards(
        args,
        recalled,
        query_tokens,
        raw_query_tokens,
        {},
        index_dir,
    )
    combined_by_name: dict[str, dict[str, Any]] = {}
    for candidate in [*original_candidates, *candidates]:
        name = str(candidate.get("name") or "")
        existing = combined_by_name.get(name)
        if existing is None or int(candidate.get("score") or 0) > int(existing.get("score") or 0):
            combined_by_name[name] = candidate
    combined_pool = len(combined_by_name)
    candidates = sorted(
        combined_by_name.values(),
        key=lambda item: (-int(item.get("score") or 0), str(item.get("name") or "")),
    )[: args.limit]
    original_names = {str(value.get("name") or "") for value in original_candidates}
    fallback_info["retained_routed_candidates"] = sum(
        1 for item in candidates if str(item.get("name") or "") in original_names
    )
    fallback_info["reranked_candidates"] = combined_pool
    result.update({
        "mode": "choose_skill",
        "selection_model": "taxonomy_then_recall_rerank",
        "candidate_pool": combined_pool,
        "content_variant_pool": content_variant_pool,
        "returned_candidates": len(candidates),
        "candidates": candidates,
        "fallback": fallback_info,
        "instruction": (
            "The taxonomy route had weak coverage, so a compact SQLite recall and rerank fallback was applied. "
            "Present only each final candidate's name, function_summary, and score."
        ),
    })
    return result


def run_lazy_facet_route(
    args: argparse.Namespace,
    metadata: dict[str, Any],
    store: LazyRouteStore,
    keywords: dict[str, Any],
    index_dir: Path,
) -> dict[str, Any]:
    selected = parse_selected_facets(args.path)
    store.select(selected)
    candidate_count = store.candidate_count()
    if not candidate_count:
        return {
            "mode": "no_skills_installed",
            "selection_model": "multi_label_facet_intersection",
            "storage_model": "sqlite_lazy",
            "query": args.query,
            "current": {"candidate_count": 0, "selected_facets": selected, "catalog_shards": [], "path": args.path},
            "candidate_pool": 0,
            "content_variant_pool": 0,
            "returned_candidates": 0,
            "candidates": [],
            "instruction": "No installed local skills are available. Offer to answer directly, install a skill, or create a new skill.",
        }

    raw_query_tokens = tokens(args.query)
    query_tokens = expand_query_tokens(args.query, keywords)
    skipped_levels: list[str] = []
    branch_level = ""
    branches: list[dict[str, Any]] = []
    leaf_target = args.leaf_target or int(metadata.get("leaf_target") or 24)
    if candidate_count > leaf_target:
        for level in store.levels():
            if level in selected:
                continue
            level_branches = store.branches(level)
            name_matches = store.name_matching_labels(level, raw_query_tokens)
            for item in level_branches:
                item["semantic_score"] = semantic_label_score(item, args.query, query_tokens, keywords)
                item["query_score"] = item["semantic_score"] + (160 if item["name"] in name_matches else 0)
                item["path"] = f"{args.path}|{level}={item['name']}" if args.path else f"{level}={item['name']}"
            full_branches = [item for item in level_branches if item["count"] == candidate_count]
            reducing = [item for item in level_branches if item["count"] < candidate_count]
            best_full = max(full_branches, key=lambda item: item["query_score"], default=None)
            best_reducing_score = max((item["query_score"] for item in reducing), default=0)
            if best_full and best_full["query_score"] > 0 and best_full["query_score"] >= best_reducing_score:
                skipped_levels.append(f"{level}={best_full['name']} (matched but non-reducing)")
                continue
            if reducing:
                reducing.sort(key=lambda item: (-item["query_score"], item["count"] if item["semantic_score"] > 0 else -item["count"], item["name"]))
                if reducing[0]["semantic_score"] <= 0 and reducing[0]["name"] not in name_matches:
                    skipped_levels.append(f"{level} (no explicit semantic evidence)")
                    break
                branch_level = level
                branches = dynamic_window(reducing, args.limit, args.branch_score_window, minimum=2)
                break
            skipped_levels.append(level)

    if branches:
        return {
            "mode": "choose_category",
            "selection_model": "multi_label_facet_intersection",
            "storage_model": "sqlite_lazy",
            "query": args.query,
            "current": {"candidate_count": candidate_count, "selected_facets": selected, "catalog_shards": [], "path": args.path},
            "auto_skipped_non_reducing_levels": skipped_levels,
            "next_level": branch_level,
            "branches": [{key: item[key] for key in ("name", "display_name", "count", "path", "query_score")} for item in branches],
            "returned_branches": len(branches),
            "instruction": "Present only these compact branches. Ask the user to choose one, then continue with its exact path.",
        }

    cards = store.cards()
    candidates, candidate_pool, content_variant_pool = rank_final_cards(
        args, cards, query_tokens, raw_query_tokens, selected, index_dir
    )
    return {
        "mode": "choose_skill",
        "selection_model": "multi_label_facet_intersection",
        "storage_model": "sqlite_lazy",
        "query": args.query,
        "current": {"candidate_count": candidate_count, "selected_facets": selected, "catalog_shards": [], "path": args.path},
        "candidate_pool": candidate_pool,
        "content_variant_pool": content_variant_pool,
        "returned_candidates": len(candidates),
        "candidates": candidates,
        "instruction": (
            "Present only each candidate's name, function_summary as its description, and score as its weight. "
            "Ask which skill to activate. Read only the chosen SKILL.md after selection."
        ),
    }


def run_facet_route(
    args: argparse.Namespace,
    metadata: dict[str, Any],
    deep_dir: Path,
    keywords: dict[str, Any],
    facets: dict[str, Any] | None = None,
    cards: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    facets = facets if facets is not None else load_json(deep_dir / "facets.json")
    cards = cards if cards is not None else load_json(deep_dir / "route-cards.json")
    leaf_target = args.leaf_target or int(metadata.get("leaf_target") or 24)
    candidate_ids, selected, shards = parse_facet_path(args.path, facets, cards, leaf_target)
    if not candidate_ids:
        return {
            "mode": "no_skills_installed",
            "selection_model": "multi_label_facet_intersection",
            "query": args.query,
            "current": {
                "candidate_count": 0,
                "selected_facets": selected,
                "catalog_shards": [],
                "path": args.path,
            },
            "candidate_pool": 0,
            "content_variant_pool": 0,
            "returned_candidates": 0,
            "candidates": [],
            "instruction": "No installed local skills are available. Offer to answer directly, install a skill, or create a new skill.",
        }

    raw_query_tokens = tokens(args.query)
    query_tokens = expand_query_tokens(args.query, keywords)
    facet_sets = {
        level: {label: set(skill_ids) for label, skill_ids in labels.items()}
        for level, labels in facets.get("facets", {}).items()
    }
    skipped_levels: list[str] = []
    branch_level = ""
    branches: list[dict[str, Any]] = []

    if len(candidate_ids) > leaf_target and not shards:
        for level in facets.get("levels", []):
            if level in selected:
                continue
            all_level_branches: list[dict[str, Any]] = []
            for label, label_ids in facet_sets.get(level, {}).items():
                subset = candidate_ids.intersection(label_ids)
                if not subset:
                    continue
                search_terms = [cards[skill_id].get("canonical_name", "") for skill_id in subset]
                item = {
                    "level": level,
                    "name": label,
                    "display_name": label,
                    "count": len(subset),
                    "search_terms": search_terms,
                }
                item["semantic_score"] = semantic_label_score(item, args.query, query_tokens, keywords)
                item["query_score"] = branch_score(item, args.query, query_tokens, raw_query_tokens, keywords)
                item["path"] = f"{args.path}|{level}={label}" if args.path else f"{level}={label}"
                all_level_branches.append(item)
            full_branches = [item for item in all_level_branches if item["count"] == len(candidate_ids)]
            level_branches = [item for item in all_level_branches if item["count"] < len(candidate_ids)]
            best_full = max(full_branches, key=lambda item: item["query_score"], default=None)
            best_reducing_score = max((item["query_score"] for item in level_branches), default=0)
            if best_full and best_full["query_score"] > 0 and best_full["query_score"] >= best_reducing_score:
                skipped_levels.append(f"{level}={best_full['name']} (matched but non-reducing)")
                continue
            if level_branches:
                level_branches.sort(key=lambda item: (
                    -item["query_score"],
                    item["count"] if item["semantic_score"] > 0 else -item["count"],
                    item["name"],
                ))
                if level_branches[0]["semantic_score"] <= 0:
                    skipped_levels.append(f"{level} (no explicit semantic evidence)")
                    break
                branch_level = level
                branches = dynamic_window(level_branches, args.limit, args.branch_score_window, minimum=2)
                break
            skipped_levels.append(level)

    if len(candidate_ids) > leaf_target and not branches and (args.catalog_shards or shards):
        groups = partition_catalog(candidate_ids, cards, leaf_target)
        depth = len(shards) + 1
        shard_branches: list[dict[str, Any]] = []
        for index, group in enumerate(groups, 1):
            first_name = cards[group[0]].get("canonical_name", "")
            last_name = cards[group[-1]].get("canonical_name", "")
            search_terms = [cards[skill_id].get("canonical_name", "") for skill_id in group]
            group_parts: set[str] = set()
            for value in search_terms:
                group_parts.update(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", value.lower()))
                group_parts.add(re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value.lower()))
            query_score = 0
            for token in raw_query_tokens:
                normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", token.lower())
                if normalized and normalized not in GENERIC_NAME_ROUTE_TOKENS and normalized in group_parts:
                    query_score += 160
            segment = f"catalog_shard_{depth}={index}"
            shard_branches.append({
                "level": f"catalog_shard_{depth}",
                "name": str(index),
                "display_name": f"名称索引 {first_name} ～ {last_name}",
                "count": len(group),
                "query_score": query_score,
                "path": f"{args.path}|{segment}" if args.path else segment,
            })
        shard_branches.sort(key=lambda item: (-item["query_score"], item["name"]))
        branch_level = f"catalog_shard_{depth}"
        branches = dynamic_window(shard_branches, args.limit, args.branch_score_window, minimum=2)

    if branches:
        return {
            "mode": "choose_category",
            "selection_model": "multi_label_facet_intersection",
            "query": args.query,
            "current": {
                "candidate_count": len(candidate_ids),
                "selected_facets": selected,
                "catalog_shards": [f"catalog_shard_{depth}={index}" for depth, index in shards],
                "path": args.path,
            },
            "auto_skipped_non_reducing_levels": skipped_levels,
            "next_level": branch_level,
            "branches": [
                {key: item[key] for key in ("name", "display_name", "count", "path", "query_score")}
                for item in branches
            ],
            "returned_branches": len(branches),
            "instruction": "Present only these compact branches. Ask the user to choose one, then continue with its exact path.",
        }

    memory_scores = load_selection_memory(deep_dir.parent, selected)
    ranked = [cards[skill_id] for skill_id in candidate_ids]
    ranked.sort(key=lambda item: (
        -(skill_score(item, query_tokens, raw_query_tokens) + memory_scores.get(str(item.get("canonical_name") or ""), 0)),
        item.get("name", ""),
    ))
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in ranked:
        grouped.setdefault(str(item.get("canonical_name") or item.get("name") or ""), []).append(item)
    visible = [variants[0] for variants in grouped.values()]
    scored_visible = []
    for item in visible:
        memory_score = memory_scores.get(str(item.get("canonical_name") or ""), 0)
        scored_visible.append({
            "card": item,
            "score": skill_score(item, query_tokens, raw_query_tokens) + memory_score,
            "memory_score": memory_score,
        })
    if scored_visible:
        top_score = scored_visible[0]["score"]
        if top_score > 0:
            returned = [
                item for item in scored_visible
                if item["score"] >= top_score - args.candidate_score_window
            ][: args.limit]
            # The final user-facing choice should normally contain 3-4 useful
            # options. Pad a narrow score window with the next-ranked skills
            # when the candidate pool is large enough.
            target_minimum = min(3, args.limit, len(scored_visible))
            if len(returned) < target_minimum:
                returned_ids = {str(item["card"].get("skill_id") or "") for item in returned}
                for item in scored_visible:
                    skill_id = str(item["card"].get("skill_id") or "")
                    if skill_id in returned_ids:
                        continue
                    returned.append(item)
                    returned_ids.add(skill_id)
                    if len(returned) >= target_minimum:
                        break
        else:
            returned = scored_visible[: args.limit]
    else:
        returned = []
    result_candidates: list[dict[str, Any]] = []
    for entry in returned:
        item = entry["card"]
        tags = list(item.get("capability_tags") or [])
        candidate = {
            "name": item["name"],
            "function_summary": item.get("function_summary", "") if args.verbose else item.get("function_summary", "")[:220],
            "matched_tags": matched_tags(item, query_tokens, selected),
            "tag_count": len(tags),
            "setup_level": item.get("setup_level", "unknown"),
            "setup_requirements": item.get("setup_requirements") or [item.get("setup_level", "unknown")],
            "origin": item.get("origin", "unknown"),
            "skill_md": item.get("skill_md", ""),
            "logical_skill_md": item.get("logical_skill_md") or item.get("skill_md", ""),
            "visible_variant_count": len(grouped[str(item.get("canonical_name") or item.get("name") or "")]),
            "score": entry["score"],
        }
        if entry["memory_score"]:
            candidate["memory_score"] = entry["memory_score"]
        if args.verbose:
            candidate["capability_tags"] = tags
        result_candidates.append(candidate)
    return {
        "mode": "choose_skill",
        "selection_model": "multi_label_facet_intersection",
        "query": args.query,
        "current": {
            "candidate_count": len(candidate_ids),
            "selected_facets": selected,
            "catalog_shards": [f"catalog_shard_{depth}={index}" for depth, index in shards],
            "path": args.path,
        },
        "candidate_pool": len(visible),
        "content_variant_pool": len(ranked),
        "returned_candidates": len(result_candidates),
        "candidates": result_candidates,
        "instruction": (
            "Present only each candidate's name, function_summary as its description, "
            "and score as its weight. Ask which skill to activate. Do not display paths, "
            "tags, provenance, setup metadata, or duplicate metadata. Read only the "
            "chosen SKILL.md after selection, and read its linked files only when needed."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Walk the deep skill hierarchy one category at a time.")
    parser.add_argument("--query", required=True)
    parser.add_argument("--path", default="")
    parser.add_argument("--index-dir", default="")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--leaf-target", type=int, default=0)
    parser.add_argument("--branch-score-window", type=int, default=60)
    parser.add_argument("--candidate-score-window", type=int, default=12)
    parser.add_argument("--fallback-min-score", type=int, default=24, help="Recall globally when the best routed candidate scores below this value.")
    parser.add_argument("--fallback-min-candidates", type=int, default=2, help="Prefer at least this many final candidates unless the routed match is strong.")
    parser.add_argument("--fallback-strong-score", type=int, default=60, help="Do not expand a small routed result when its best score reaches this value.")
    parser.add_argument("--fallback-recall-limit", type=int, default=30, help="Maximum compact SQLite cards recalled before reranking.")
    parser.add_argument("--disable-fallback", action="store_true", help="Disable automatic recall and rerank fallback.")
    parser.add_argument("--force-fallback", action="store_true", help="Force recall and rerank for diagnostics and tests.")
    parser.add_argument("--verbose", action="store_true", help="Return full summaries and all tags in the final shortlist.")
    parser.add_argument("--legacy-hierarchy", action="store_true", help="Use the canonical single-route hierarchy instead of multi-label facets.")
    parser.add_argument("--catalog-shards", action="store_true", help="Continue into alphabetical catalog shards when semantic facets are exhausted.")
    parser.add_argument("--allow-stale-index", action="store_true", help="Use an index even when its lightweight source manifest is stale.")
    parser.add_argument("--auto-route", action="store_true", help="Walk the strongest category branches internally and return the final shortlist.")
    parser.add_argument("--freshness-cache-seconds", type=int, default=DEFAULT_FRESHNESS_CACHE_SECONDS, help="Reuse a successful source freshness scan for this many seconds.")
    parser.add_argument("--force-freshness-check", action="store_true", help="Ignore the freshness cache and rescan all configured skill roots.")
    parser.add_argument("--json-router", action="store_true", help="Use the legacy whole-JSON facet router instead of SQLite lazy loading.")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    index_dir = Path(args.index_dir).expanduser().resolve() if args.index_dir else script_dir.parent / ".skill-index"
    deep_dir = index_dir / "deep"
    metadata = load_json(deep_dir / "metadata.json")
    if not args.allow_stale_index:
        freshness = check_index_freshness(
            metadata,
            deep_dir,
            cache_seconds=max(0, args.freshness_cache_seconds),
            force=args.force_freshness_check,
        )
        if not freshness["fresh"]:
            roots = list(metadata.get("skills_roots") or [metadata.get("skills_root")])
            print(json.dumps({
                "mode": "index_stale",
                "query": args.query,
                "freshness": freshness,
                "skills_roots": [value for value in roots if value],
                "instruction": "Rebuild the per-user deep index before routing. Do not use stale skill classifications.",
            }, ensure_ascii=False, indent=2))
            return 0
    keyword_path = deep_dir / "label-keywords.json"
    keywords = load_json(keyword_path) if keyword_path.exists() else {}
    if not args.legacy_hierarchy and not args.json_router:
        database = ensure_lazy_database(deep_dir, script_dir)
        if database is not None:
            store = LazyRouteStore(database)
            try:
                result = run_lazy_facet_route(args, metadata, store, keywords, index_dir)
                route_trace: list[dict[str, Any]] = []
                visited_paths = {args.path}
                while args.auto_route and result.get("mode") == "choose_category":
                    branches = list(result.get("branches") or [])
                    if not branches:
                        break
                    selected_branch = max(
                        branches,
                        key=lambda item: (int(item.get("query_score") or 0), -int(item.get("count") or 0)),
                    )
                    selected_path = str(selected_branch.get("path") or "")
                    if not selected_path or selected_path in visited_paths:
                        break
                    route_trace.append({
                        "level": result.get("next_level", ""),
                        "selected": selected_branch.get("name", ""),
                        "path": selected_path,
                        "score": int(selected_branch.get("query_score") or 0),
                    })
                    visited_paths.add(selected_path)
                    args.path = selected_path
                    result = run_lazy_facet_route(args, metadata, store, keywords, index_dir)
                result = apply_recall_fallback(args, result, store, keywords, index_dir)
                if args.auto_route:
                    result["route_trace"] = route_trace
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 0
            finally:
                store.close()
    if not args.legacy_hierarchy and (deep_dir / "facets.json").exists() and (deep_dir / "route-cards.json").exists():
        facets = load_json(deep_dir / "facets.json")
        cards = load_json(deep_dir / "route-cards.json")
        result = run_facet_route(args, metadata, deep_dir, keywords, facets, cards)
        route_trace: list[dict[str, Any]] = []
        visited_paths = {args.path}
        while args.auto_route and result.get("mode") == "choose_category":
            branches = list(result.get("branches") or [])
            if not branches:
                break
            selected_branch = max(
                branches,
                key=lambda item: (int(item.get("query_score") or 0), -int(item.get("count") or 0)),
            )
            selected_path = str(selected_branch.get("path") or "")
            if not selected_path or selected_path in visited_paths:
                break
            route_trace.append({
                "level": result.get("next_level", ""),
                "selected": selected_branch.get("name", ""),
                "path": selected_path,
                "score": int(selected_branch.get("query_score") or 0),
            })
            visited_paths.add(selected_path)
            args.path = selected_path
            result = run_facet_route(args, metadata, deep_dir, keywords, facets, cards)
        if args.auto_route:
            result["route_trace"] = route_trace
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    tree = load_json(deep_dir / "hierarchy.json")
    node = find_node(tree, args.path)
    leaf_target = args.leaf_target or int(metadata.get("leaf_target") or 24)

    skipped: list[dict[str, Any]] = []
    while int(node.get("count") or 0) > leaf_target and len(node.get("children", [])) == 1:
        node = node["children"][0]
        skipped.append({"level": node["level"], "name": node["name"], "path": node["path"]})

    raw_query_tokens = tokens(args.query)
    query_tokens = expand_query_tokens(args.query, keywords)
    children = list(node.get("children", []))
    if int(node.get("count") or 0) > leaf_target and children:
        branches = sorted(children, key=lambda item: (-branch_score(item, args.query, query_tokens, raw_query_tokens, keywords), -int(item.get("count") or 0), item.get("name", "")))
        result = {
            "mode": "choose_category",
            "query": args.query,
            "current": {k: node.get(k) for k in ("level", "name", "display_name", "count", "path")},
            "auto_skipped_single_child": skipped,
            "next_level": branches[0].get("level") if branches else "",
            "branches": [
                {
                    "name": item["name"],
                    "display_name": item.get("display_name", item["name"]),
                    "count": item["count"],
                    "path": item["path"],
                    "query_score": branch_score(item, args.query, query_tokens, raw_query_tokens, keywords),
                }
                for item in branches[: args.limit]
            ],
            "instruction": "Ask the user to choose one category, then call deep-route.py again with that branch path. Do not load all skills yet.",
        }
    else:
        cards = read_cards(deep_dir / "skills-deep-index.ndjson")
        skill_ids = list(dict.fromkeys(flatten_skill_ids(node)))
        ranked = [cards[skill_id] for skill_id in skill_ids if skill_id in cards]
        ranked.sort(key=lambda item: (-skill_score(item, query_tokens, raw_query_tokens), item.get("name", "")))
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in ranked:
            grouped.setdefault(str(item.get("canonical_name") or item.get("name") or ""), []).append(item)
        candidates = [variants[0] for variants in grouped.values()]
        result = {
            "mode": "choose_skill",
            "query": args.query,
            "current": {k: node.get(k) for k in ("level", "name", "display_name", "count", "path")},
            "auto_skipped_single_child": skipped,
            "candidate_pool": len(candidates),
            "content_variant_pool": len(ranked),
            "candidates": [
                {
                    "name": item["name"],
                    "function_summary": item["function_summary"],
                    "capability_tags": item["capability_tags"],
                    "setup_level": item["setup_level"],
                    "setup_requirements": item.get("setup_requirements") or [item["setup_level"]],
                    "origin": item["origin"],
                    "skill_md": item["skill_md"],
                    "logical_skill_md": item.get("logical_skill_md") or item["skill_md"],
                    "visible_variant_count": len(grouped[str(item.get("canonical_name") or item.get("name") or "")]),
                    "score": skill_score(item, query_tokens, raw_query_tokens),
                }
                for item in candidates[: args.limit]
            ],
            "instruction": "Present this small final shortlist and ask the user which skill to activate.",
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
