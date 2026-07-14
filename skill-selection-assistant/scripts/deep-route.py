#!/usr/bin/env python3
"""Traverse the exhaustive hospital-style skill hierarchy one category at a time."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


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
    haystack = f"{branch.get('name', '')} {branch.get('display_name', '')}".lower()
    score = sum(12 for token in query_tokens if token in haystack)
    descendant_names = " ".join(str(value) for value in branch.get("search_terms", [])).lower()
    if descendant_names:
        score += sum(160 for token in raw_query_tokens if token in descendant_names)
    level = str(branch.get("level") or "")
    label = str(branch.get("name") or "")
    score += direct_label_score(level, label, query, keywords)
    if level == "primary_domain":
        primary_map = keywords.get("primary_map", {})
        for detail_label, primary_label in primary_map.items():
            if str(primary_label) == label:
                score = max(score, direct_label_score("domain_detail", str(detail_label), query, keywords))
    return score


def skill_score(card: dict[str, Any], query_tokens: set[str], raw_query_tokens: set[str]) -> int:
    name = str(card.get("name") or "").lower()
    name_parts = set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", name))
    summary = str(card.get("function_summary") or "").lower()
    tags = " ".join(card.get("capability_tags") or []).lower()
    score = 0
    for token in raw_query_tokens:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Walk the deep skill hierarchy one category at a time.")
    parser.add_argument("--query", required=True)
    parser.add_argument("--path", default="")
    parser.add_argument("--index-dir", default="")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--leaf-target", type=int, default=0)
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    index_dir = Path(args.index_dir).expanduser().resolve() if args.index_dir else script_dir.parent / ".skill-index"
    deep_dir = index_dir / "deep"
    metadata = load_json(deep_dir / "metadata.json")
    tree = load_json(deep_dir / "hierarchy.json")
    keyword_path = deep_dir / "label-keywords.json"
    keywords = load_json(keyword_path) if keyword_path.exists() else {}
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
                    "origin": item["origin"],
                    "skill_md": item["skill_md"],
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
