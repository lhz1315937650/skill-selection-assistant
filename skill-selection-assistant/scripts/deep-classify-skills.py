#!/usr/bin/env python3
"""Build an exhaustive, multi-label, hospital-style index for every local SKILL.md."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import sys
import time
import importlib.util
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "2.6.0"
DEFAULT_LEAF_TARGET = 24
OVERLAY_FILE = "tag-overlay.json"
GENERIC_FUNCTION_LABELS = {"general", "coding-general", "workflow"}
TAG_STOPWORDS = {
    "skill", "helper", "assistant", "the", "and", "for", "with", "this", "that", "from",
    "using", "use", "into", "local", "your", "you", "when", "then", "into", "about",
}
MAX_TAGS = {
    "domain_detail": 4,
    "specialty": 5,
    "task_type": 4,
    "output_type": 3,
    "tech_stack": 6,
}

TECH_RULES = {
    "html-css": r"\bhtml5?\b|\bcss3?\b|scss|sass|less|web layout",
    "javascript": r"javascript|\bjs\b|ecmascript",
    "typescript": r"typescript|\btsx?\b",
    "react": r"\breact(?:\.js|js)?\b|\bjsx\b",
    "nextjs": r"next\.js|\bnextjs\b",
    "vue": r"\bvue(?:\.js|js)?\b|nuxt",
    "angular": r"\bangular\b",
    "svelte": r"\bsvelte(?:kit)?\b",
    "tailwind": r"tailwind(?:css)?",
    "nodejs": r"node\.js|\bnodejs\b|\bnpm\b|\bpnpm\b|\byarn\b",
    "python": r"\bpython\b|\bpip\b|\bpoetry\b|\buv\b",
    "django": r"\bdjango\b",
    "fastapi": r"\bfastapi\b",
    "flask": r"\bflask\b",
    "java": r"\bjava\b|spring boot|\bspring\b",
    "golang": r"\bgolang\b|\bgo language\b",
    "rust": r"\brust\b|\bcargo\b",
    "dotnet": r"\.net\b|\bdotnet\b|c#|asp\.net",
    "php": r"\bphp\b|laravel|symfony",
    "ruby": r"\bruby\b|rails",
    "sql": r"\bsql\b|relational database",
    "postgresql": r"postgres(?:ql)?|\bpsql\b",
    "mysql": r"\bmysql\b|mariadb",
    "sqlite": r"\bsqlite\b",
    "mongodb": r"\bmongodb\b|\bmongo\b",
    "redis": r"\bredis\b",
    "bigquery": r"\bbigquery\b",
    "snowflake": r"\bsnowflake\b",
    "pandas": r"\bpandas\b",
    "numpy": r"\bnumpy\b",
    "spark": r"\bapache spark\b|\bpyspark\b",
    "excel": r"\bexcel\b|\bxlsx\b|spreadsheet",
    "power-bi": r"power\s*bi",
    "tableau": r"\btableau\b",
    "pytorch": r"\bpytorch\b|\btorch\b",
    "tensorflow": r"\btensorflow\b|\bkeras\b",
    "scikit-learn": r"scikit-learn|\bsklearn\b",
    "hugging-face": r"hugging\s*face|transformers library",
    "openai": r"\bopenai\b|chatgpt",
    "anthropic": r"\banthropic\b|\bclaude\b",
    "langchain": r"\blangchain\b|langgraph",
    "rag-vector-db": r"\brag\b|vector database|embedding|pinecone|weaviate|milvus|chroma",
    "docker": r"\bdocker\b|dockerfile|docker compose",
    "kubernetes": r"kubernetes|\bk8s\b|\bhelm\b",
    "terraform": r"\bterraform\b|opentofu",
    "github-actions": r"github actions|\.github/workflows",
    "aws": r"\baws\b|amazon web services",
    "azure": r"\bazure\b",
    "gcp": r"\bgcp\b|google cloud",
    "cloudflare": r"\bcloudflare\b",
    "vercel": r"\bvercel\b",
    "playwright": r"\bplaywright\b",
    "selenium": r"\bselenium\b",
    "git-github": r"\bgit\b|\bgithub\b|pull request",
    "pdf": r"\bpdf\b|ocr",
    "docx": r"\bdocx\b|microsoft word|word document",
    "latex": r"\blatex\b|\btex\b|bibtex",
    "pptx": r"\bpptx\b|powerpoint|slide deck",
    "svg": r"\bsvg\b|vector graphic",
    "canvas-webgl": r"html canvas|\bwebgl\b|\bwebgpu\b|three\.js",
    "figma": r"\bfigma\b",
    "animejs-motion": r"anime\.js|animejs|web animation api|\bwaapi\b",
    "mcp": r"model context protocol|\bmcp\b",
    "rest-graphql": r"rest(?:ful)? api|\bgraphql\b|openapi|swagger",
}

ZH_LABELS = {
    "coding": "软件开发",
    "research": "研究科研",
    "data": "数据分析",
    "documents": "文档处理",
    "design": "视觉设计",
    "writing": "写作编辑",
    "publishing": "内容发布",
    "safety": "安全合规",
    "general": "综合门诊",
    "generate": "生成创建",
    "review": "评审检查",
    "analyze": "分析研究",
    "transform": "转换改写",
    "test-debug": "测试调试",
    "extract": "提取解析",
    "publish": "发布部署",
    "plan": "规划设计",
    "summarize": "总结归纳",
    "workflow": "流程自动化",
    "none": "无需额外配置",
    "local-runtime": "本地运行环境",
    "network": "需要联网",
    "account": "需要账号",
    "api-key": "需要密钥",
    "unknown": "待确认",
}


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", file=sys.stderr, flush=True)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def dump_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def empty_overlay() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "domain_detail_rules": {},
        "specialty_rules": {},
        "task_type_rules": {},
        "primary_map": {},
    }


def load_tag_overlay(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_overlay()
    try:
        payload = load_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return empty_overlay()
    overlay = empty_overlay()
    if isinstance(payload, dict):
        for key in ("domain_detail_rules", "specialty_rules", "task_type_rules", "primary_map"):
            values = payload.get(key)
            if isinstance(values, dict):
                overlay[key] = {str(name): str(pattern) for name, pattern in values.items() if name}
    return overlay


def merge_overlay_into_rules(rules: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(rules)
    merged["domain_detail_rules"] = {**dict(rules.get("domain_detail_rules") or {}), **overlay.get("domain_detail_rules", {})}
    merged["specialty_rules"] = {**dict(rules.get("specialty_rules") or {}), **overlay.get("specialty_rules", {})}
    merged["task_rules"] = {**dict(rules.get("task_rules") or {}), **overlay.get("task_type_rules", {})}
    merged["primary_map"] = {**dict(rules.get("primary_map") or {}), **overlay.get("primary_map", {})}
    return merged


def distinctive_tokens(text: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9]{2,}|[\u4e00-\u9fff]{2,}", str(text or "").lower())
    return [token for token in dict.fromkeys(tokens) if token not in TAG_STOPWORDS][:12]


def keyword_pattern(tokens: list[str]) -> str:
    useful = [re.escape(token) for token in tokens if token and token not in TAG_STOPWORDS][:8]
    return "|".join(useful) if useful else "general"


def infer_primary_domain(text: str, rules: dict[str, Any]) -> str:
    lowered = text.lower()
    if re.search(r"code|script|software|program|api|app|repo|python|typescript", lowered):
        return "coding"
    if re.search(r"paper|research|academic|literature|citation", lowered):
        return "research"
    if re.search(r"data|chart|statistics|csv|excel", lowered):
        return "data"
    if re.search(r"write|article|blog|copy|translate", lowered):
        return "writing"
    return str((rules.get("primary_map") or {}).get("general") or "general")


def propose_function_label(item: dict[str, Any], level: str, existing: set[str]) -> str:
    tokens = distinctive_tokens(f"{item.get('name') or ''} {item.get('function_summary') or ''}")
    name_slug = safe_slug(str(item.get("canonical_name") or item.get("name") or "new-skill"))
    if level == "specialty":
        label = name_slug[:48]
    else:
        label = safe_slug("-".join(tokens[:3]) or name_slug)[:48]
    if not label or label in GENERIC_FUNCTION_LABELS:
        label = name_slug[:48] or "new-domain"
    if label in existing and label not in GENERIC_FUNCTION_LABELS:
        return label
    if label in existing:
        label = f"{label}-domain" if level == "domain_detail" else f"{label}-specialty"
    return label or "new-domain"


def first_sentence(text: str) -> str:
    value = normalize_text(text)
    if not value:
        return ""
    parts = re.split(r"(?<=[。！？.!?])\s+", value, maxsplit=1)
    return parts[0][:220]


def humanize_label(value: str) -> str:
    return re.sub(r"[-_]+", " ", str(value or "")).strip()


def capability_bullet(value: str) -> str:
    cleaned = clean_selection_example(value)
    cleaned = re.sub(r"^(?:use this skill (?:for|when|to)|use for|this skill (?:is for|helps)|适用于)\s+", "", cleaned, flags=re.I)
    return cleaned[:180].rstrip(" .")


def is_noise_capability(value: str) -> bool:
    lowered = str(value or "").lower()
    if not lowered or len(lowered) < 8:
        return True
    noise_bits = (
        "activates automatically",
        "in your request",
        "this skill activates",
        "help me with",
        "how do i implement",
    )
    return any(bit in lowered for bit in noise_bits) or lowered.startswith("mention ")


def enrich_function_profile(item: dict[str, Any], body: str = "") -> dict[str, Any]:
    purpose = first_sentence(item.get("function_summary") or "")
    if not purpose:
        purpose = first_sentence(body) or str(item.get("name") or "")
    source_text = f"{item.get('function_summary') or ''}\n{body or item.get('function_detail') or ''}"
    does: list[str] = []
    does_not: list[str] = []
    if purpose:
        does.append(purpose)
    for value in item.get("selection_positive_examples") or []:
        bullet = capability_bullet(str(value))
        if bullet and not is_noise_capability(bullet):
            does.append(bullet)
    heading_skip = re.compile(
        r"^(?:step\s+\d|phase\s+\d|prerequisites?|setup|purpose|overview|instructions|usage|introduction|intro|readme|notes?|examples?|references?|assets|core workflow|tool discovery|when to use|when not to use)$",
        re.I,
    )
    for heading in item.get("headings") or []:
        value = str(heading).strip()
        lowered = value.lower()
        if not value or heading_skip.match(lowered):
            continue
        if re.search(r"when not|do not|not to use|out of scope|limitations?|cannot|不适用|不能|禁止", lowered):
            continue
        if len(value.split()) < 4:
            continue
        if re.search(r"\b(build|create|write|analy|repair|design|test|review|generate|draft|clean|classif|recommend|debug|deploy)\b", lowered) and len(does) < 8:
            bullet = capability_bullet(value)
            if bullet and not is_noise_capability(bullet):
                does.append(bullet)
    for value in item.get("selection_negative_examples") or []:
        bullet = capability_bullet(str(value))
        if bullet:
            does_not.append(bullet)
    for match in re.finditer(
        r"(?im)^.*(?:do not use|not suitable for|avoid using|out of scope|不适用于|不要使用|不能用于|并非用于).*$",
        source_text,
    ):
        bullet = capability_bullet(match.group(0))
        if bullet and "cannot finish" not in bullet.lower():
            does_not.append(bullet)
    unique_does: list[str] = []
    for value in does:
        if any(value.lower() in existing.lower() or existing.lower() in value.lower() for existing in unique_does):
            continue
        unique_does.append(value)
    does = unique_does
    if not does_not:
        focus = ", ".join(
            str(value)
            for value in list(dict.fromkeys([*(item.get("specialty") or []), *(item.get("domain_detail") or [])]))[:4]
            if value and value not in GENERIC_FUNCTION_LABELS
        )
        if purpose:
            does_not.append("Do not use for work outside this function: " + purpose[:120])
        if focus:
            does_not.append("Not a substitute for unrelated domains; stay on: " + focus)
        requirements = item.get("setup_requirements") or [item.get("setup_level") or "unknown"]
        if "api-key" in requirements:
            does_not.append("Cannot finish the task without the required API key")
        if "account" in requirements:
            does_not.append("Cannot finish the task without the required account login")
        if "network" in requirements:
            does_not.append("Cannot run fully offline; network access is required")
    aliases = distinctive_tokens(f"{item.get('name') or ''} {purpose} {item.get('function_summary') or ''} {source_text[:1200]}")
    item["function_purpose"] = purpose
    item["function_summary"] = purpose or str(item.get("function_summary") or "")[:220]
    item["aliases"] = aliases
    item["does"] = list(dict.fromkeys(value for value in does if value))[:8]
    item["does_not"] = list(dict.fromkeys(value for value in does_not if value))[:8]
    item["can_do"] = item["does"]
    item["cannot_do"] = item["does_not"]
    item["function_weight"] = int(item.get("function_weight") or 100)
    profile = dict(item.get("functional_profile") or {})
    profile["purpose"] = purpose
    profile["aliases"] = aliases
    profile["does"] = item["does"]
    profile["does_not"] = item["does_not"]
    profile["can_do"] = item["does"]
    profile["cannot_do"] = item["does_not"]
    item["functional_profile"] = profile
    return item


def similar_existing_label(tokens: list[str], existing: set[str], keyword_map: dict[str, str]) -> str:
    token_set = {token.lower() for token in tokens if token and token not in GENERIC_FUNCTION_LABELS}
    if not token_set:
        return ""
    best_label = ""
    best_score = 0.0
    for label in existing:
        if label in GENERIC_FUNCTION_LABELS:
            continue
        parts = {part for part in re.split(r"[-_]+", label.lower()) if part}
        keyword_parts = set(distinctive_tokens(keyword_map.get(label, "")))
        overlap = token_set.intersection(parts.union(keyword_parts).union({label.lower()}))
        score = len(overlap) / max(1, min(len(token_set), max(1, len(parts) or 1)))
        if label.lower() in token_set or any(token in label.lower() for token in token_set if len(token) >= 4):
            score = max(score, 0.6)
        if score > best_score:
            best_label, best_score = label, score
    return best_label if best_score >= 0.45 else ""


def apply_new_domain_tags(
    item: dict[str, Any],
    existing_labels: dict[str, set[str]],
    overlay: dict[str, Any],
    rules: dict[str, Any],
) -> list[dict[str, str]]:
    created: list[dict[str, str]] = []
    text = f"{item.get('name') or ''} {item.get('function_summary') or ''} {' '.join(item.get('aliases') or [])}"
    tokens = list(dict.fromkeys([*(item.get('aliases') or []), *distinctive_tokens(text)]))
    pattern = keyword_pattern(tokens + [str(item.get("canonical_name") or "")])
    level_to_overlay = {"domain_detail": "domain_detail_rules", "specialty": "specialty_rules"}
    for level, overlay_key in level_to_overlay.items():
        values = [str(value) for value in (item.get(level) or []) if value]
        specific = [value for value in values if value not in GENERIC_FUNCTION_LABELS]
        if specific:
            continue
        existing = existing_labels.get(level) or set()
        keyword_map = overlay.get(overlay_key) or {}
        merged = similar_existing_label(tokens, existing, keyword_map)
        label = merged or propose_function_label(item, level, existing)
        is_new = not merged and label not in existing
        item[level] = [label, *[value for value in values if value != "general" and value != label]]
        if is_new:
            overlay.setdefault(overlay_key, {})[label] = pattern
            created.append({
                "level": level,
                "label": label,
                "origin": "overlay",
                "keywords": pattern,
                "aliases": tokens,
                "canonical_label": label,
            })
            existing.add(label)
        else:
            current = str(overlay.setdefault(overlay_key, {}).get(label) or "")
            merged_pattern = "|".join(part for part in dict.fromkeys([current, pattern] + tokens) if part)
            overlay[overlay_key][label] = merged_pattern
            created.append({
                "level": level,
                "label": label,
                "origin": "overlay",
                "keywords": merged_pattern,
                "aliases": tokens,
                "canonical_label": label,
                "merged": True,
            })
        if level == "domain_detail":
            primary = str((rules.get("primary_map") or {}).get(label) or overlay.get("primary_map", {}).get(label) or "")
            if not primary:
                primary = infer_primary_domain(text, rules)
                overlay.setdefault("primary_map", {})[label] = primary
            item["primary_domain"] = primary
            item["primary_domains"] = list(dict.fromkeys([primary, *(item.get("primary_domains") or [])]))
    route = dict(item.get("primary_route") or {})
    route["primary_domain"] = item.get("primary_domain") or route.get("primary_domain") or "general"
    route["primary_domains"] = item.get("primary_domains") or [route["primary_domain"]]
    route["domain_detail"] = (item.get("domain_detail") or ["general"])[0]
    route["specialty"] = (item.get("specialty") or ["general"])[0]
    item["primary_route"] = route
    item["capability_tags"] = list(dict.fromkeys(
        list(item.get("domain_detail") or [])
        + list(item.get("specialty") or [])
        + list(item.get("task_type") or [])
        + list(item.get("output_type") or [])
        + list(item.get("tech_stack") or [])
        + list(item.get("setup_requirements") or [])
        + list(item.get("capability_tags") or [])
    ))
    profile = dict(item.get("functional_profile") or {})
    profile["primary_domains"] = item.get("primary_domains")
    profile["domain_labels"] = item.get("domain_detail")
    profile["specialty_labels"] = item.get("specialty")
    item["functional_profile"] = profile
    return created


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def canonical_name(name: str) -> str:
    value = re.sub(r"[^\w\u4e00-\u9fff]+", "-", name.lower(), flags=re.UNICODE).strip("-")
    return value or "unnamed-skill"


def safe_slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-").lower()
    return value or "general"


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), -1)
    if end < 0:
        return {}, text
    meta: dict[str, str] = {}
    i = 1
    while i < end:
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", lines[i])
        if not match:
            i += 1
            continue
        key, value = match.group(1), match.group(2).strip()
        if value in {"|", ">", "|-", ">-", "|+", ">+"}:
            block: list[str] = []
            i += 1
            while i < end and (lines[i].startswith(" ") or not lines[i].strip()):
                block.append(lines[i].strip())
                i += 1
            meta[key] = normalize_text(" ".join(block))
            continue
        meta[key] = value.strip("\"'")
        i += 1
    return meta, "\n".join(lines[end + 1 :])


def first_body_summary(body: str) -> str:
    paragraphs = re.split(r"\n\s*\n", body)
    for paragraph in paragraphs:
        value = normalize_text(re.sub(r"^#+\s*", "", paragraph.strip()))
        if value and not value.startswith("```") and len(value) >= 30:
            return value[:600]
    return ""


def clean_selection_example(value: str) -> str:
    value = re.sub(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", "", value)
    value = re.sub(r"[`*_>#]", "", value)
    return normalize_text(value)[:260]


def extract_selection_examples(description: str, body: str) -> tuple[list[str], list[str]]:
    positive: list[str] = []
    negative: list[str] = []
    positive_heading = re.compile(r"when to use|use cases?|triggers?|capabilities|can do|适用|使用场景|触发|能做|可以做", re.I)
    negative_heading = re.compile(r"when not to use|do not use|not suitable|avoid using|out of scope|limitations?|cannot|不适用|不要使用|禁用场景|不能做|不可以做", re.I)
    current = ""
    for raw_line in body.splitlines():
        heading = re.match(r"^#{1,5}\s+(.+?)\s*$", raw_line)
        if heading:
            title = normalize_text(heading.group(1))
            current = "negative" if negative_heading.search(title) else "positive" if positive_heading.search(title) else ""
            continue
        cleaned = clean_selection_example(raw_line)
        if not cleaned or len(cleaned) < 8:
            continue
        if current == "positive" and len(positive) < 8:
            positive.append(cleaned)
        elif current == "negative" and len(negative) < 8:
            negative.append(cleaned)

    combined = f"{description}\n{body}"
    for match in re.finditer(
        r"(?im)^(.*?(?:use this skill when|use when|trigger(?:ed)? (?:with|by)|适用于|使用场景|触发词).*?)$",
        combined,
    ):
        cleaned = clean_selection_example(match.group(1))
        if cleaned:
            positive.append(cleaned)
    for match in re.finditer(
        r"(?im)^(.*?(?:do not use this skill|not suitable for|avoid using this skill|本 skill 不适用|不适用于|不要使用此 skill).*?)$",
        combined,
    ):
        cleaned = clean_selection_example(match.group(1))
        if cleaned:
            negative.append(cleaned)

    quoted = re.findall(r"[\"“]([^\"”]{4,120})[\"”]", description)
    positive.extend(clean_selection_example(value) for value in quoted)
    return list(dict.fromkeys(value for value in positive if value))[:8], list(dict.fromkeys(value for value in negative if value))[:8]


def body_without_negative_examples(body: str) -> str:
    negative_heading = re.compile(r"when not to use|do not use|not suitable|avoid using|不适用|不要使用|禁用场景", re.I)
    explicit_negative = re.compile(
        r"do not use this skill|not suitable for|avoid using this skill|本 skill 不适用|不适用于|不要使用此 skill",
        re.I,
    )
    kept: list[str] = []
    skip_level = 0
    for line in body.splitlines():
        heading = re.match(r"^#{1,5}\s+(.+?)\s*$", line)
        if heading:
            level = len(line) - len(line.lstrip("#"))
            if skip_level and level > skip_level:
                continue
            if negative_heading.search(normalize_text(heading.group(1))):
                skip_level = level
                continue
            skip_level = 0
            if not skip_level:
                kept.append(line)
            continue
        if skip_level or explicit_negative.search(line):
            continue
        kept.append(line)
    return "\n".join(kept)


def description_without_negative_examples(description: str) -> str:
    return normalize_text(re.sub(
        r"(?i)(?:do not use this skill|not suitable for|avoid using this skill|本 skill 不适用|不适用于|不要使用此 skill).*$",
        "",
        description,
    ))


def compile_rules(raw: dict[str, Any]) -> dict[str, re.Pattern[str]]:
    result: dict[str, re.Pattern[str]] = {}
    for key, pattern in raw.items():
        try:
            result[str(key)] = re.compile(str(pattern), re.IGNORECASE)
        except re.error:
            continue
    return result


def count_matches(pattern: re.Pattern[str], text: str, limit: int = 4) -> int:
    """Count only the first few matches so huge SKILL.md files do not allocate large lists."""
    count = 0
    for _ in pattern.finditer(text):
        count += 1
        if count >= limit:
            break
    return count


def score_rule_set(
    name: str,
    description: str,
    headings: str,
    body: str,
    compiled: dict[str, re.Pattern[str]],
    minimum: int,
    maximum: int,
    require_identity: bool = False,
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    scored: list[tuple[str, int]] = []
    evidence: dict[str, dict[str, Any]] = {}
    for label, pattern in compiled.items():
        score = 0
        sources: list[str] = []
        if pattern.search(name):
            score += 16
            sources.append("name")
        if pattern.search(description):
            score += 10
            sources.append("description")
        if pattern.search(headings):
            score += 6
            sources.append("headings")
        body_hits = count_matches(pattern, body, limit=8)
        if body_hits:
            score += min(body_hits, 6)
            sources.append("full_body")
        identity = any(source in {"name", "description"} for source in sources)
        heading_hit = "headings" in sources
        if require_identity and not identity and not heading_hit and body_hits < 6:
            continue
        if not require_identity and not identity and not heading_hit and body_hits < 3:
            continue
        if score >= minimum:
            scored.append((label, score))
            evidence[label] = {"score": score, "sources": sources, "body_hits": body_hits, "identity": identity}
    scored.sort(key=lambda item: (-item[1], item[0]))
    if scored:
        floor = max(minimum, int(scored[0][1] * 0.58))
        scored = [item for item in scored if item[1] >= floor][:maximum]
    return [name for name, _ in scored], {name: evidence[name] for name, _ in scored}


def setup_evidence(description: str, body: str) -> str:
    """Keep explicit prerequisite sections and executable setup commands, not incidental mentions."""
    selected: list[str] = []
    active_section = False
    for line in body.splitlines():
        heading = re.match(r"^#{2,6}\s+(.+?)\s*$", line)
        if heading:
            active_section = bool(re.search(
                r"requirements?|prerequisites?|installation|setup|configuration|dependencies|"
                r"安装|配置|前置条件|环境要求|依赖",
                heading.group(1),
                re.IGNORECASE,
            ))
            continue
        if active_section or re.search(
            r"^\s*(?:\$\s*)?(?:npm|pnpm|yarn|pip|pipx|uv|poetry|cargo|go|curl|wget|git clone|docker)\s+",
            line,
            re.IGNORECASE,
        ):
            selected.append(line)
    explicit_description = description if re.search(
        r"\b(?:requires?|prerequisites?|must (?:have|set|provide|configure)|needs? an? )\b|"
        r"需要(?:提供|配置|安装|登录|联网)|前置条件",
        description,
        re.IGNORECASE,
    ) else ""
    return f"{explicit_description}\n" + "\n".join(selected)


def infer_setup_requirements(description: str, body: str) -> list[str]:
    lowered = setup_evidence(description, body).lower()
    requirements: list[str] = []
    if re.search(r"api[- ]?key|secret key|access token|credentials?|[a-z][a-z0-9_]+_(?:api_)?key|密钥|令牌", lowered):
        requirements.append("api-key")
    if re.search(r"oauth|sign[ -]?in|log[ -]?in|account|workspace selection|账号|登录", lowered):
        requirements.append("account")
    if re.search(r"download|internet access|network access|clone |curl |wget |联网|下载", lowered):
        requirements.append("network")
    if re.search(r"npm install|pnpm install|pip install|install dependencies|docker|runtime|toolchain|安装依赖|运行环境", lowered):
        requirements.append("local-runtime")
    return requirements or ["none"]


def classify_document(
    text: str,
    path: Path,
    manifest_entry: dict[str, Any],
    rules: dict[str, Any],
    compiled_rules: dict[str, dict[str, re.Pattern[str]]],
) -> dict[str, Any]:
    meta, body = parse_frontmatter(text)
    fallback_name = path.parent.name
    name = normalize_text(meta.get("name") or manifest_entry.get("canonical_name") or fallback_name)
    description = normalize_text(meta.get("description") or meta.get("short-description") or first_body_summary(body))
    positive_examples, negative_examples = extract_selection_examples(description, body)
    classification_description = description_without_negative_examples(description)
    classification_body = body_without_negative_examples(body)
    headings_list = [normalize_text(m.group(1)) for m in re.finditer(r"(?m)^#{1,4}\s+(.+?)\s*$", body)]
    headings_list = [value for value in headings_list if value][:20]
    headings = " ".join(headings_list)

    detail, detail_ev = score_rule_set(
        name, classification_description, headings, classification_body,
        compiled_rules["domain_detail"], 8, MAX_TAGS["domain_detail"], require_identity=True,
    )
    specialty, specialty_ev = score_rule_set(
        name, classification_description, headings, classification_body,
        compiled_rules["specialty"], 8, MAX_TAGS["specialty"], require_identity=True,
    )
    tasks, task_ev = score_rule_set(
        name, classification_description, headings, classification_body,
        compiled_rules["task_type"], 6, MAX_TAGS["task_type"], require_identity=True,
    )
    outputs, output_ev = score_rule_set(
        name, classification_description, headings, classification_body,
        compiled_rules["output_type"], 6, MAX_TAGS["output_type"], require_identity=False,
    )
    tech, tech_ev = score_rule_set(
        name, classification_description, headings, classification_body,
        compiled_rules["tech_stack"], 6, MAX_TAGS["tech_stack"], require_identity=False,
    )

    if not detail:
        detail = ["coding-general" if re.search(r"code|script|software|program|代码|开发", f"{name} {classification_description}", re.I) else "general"]
    if not specialty:
        specialty = ["general"]
    if not tasks:
        tasks = ["workflow"]
    if not outputs:
        outputs = ["workflow"]
    if not tech:
        tech = ["general"]

    primary_map = rules.get("primary_map", {})
    primary_domains = list(dict.fromkeys(str(primary_map.get(value) or "general") for value in detail))
    primary_domain = primary_domains[0]
    setup_requirements = infer_setup_requirements(classification_description, classification_body)
    setup_level = setup_requirements[0]
    route = {
        "primary_domain": primary_domain,
        "primary_domains": primary_domains,
        "domain_detail": detail[0],
        "specialty": specialty[0],
        "task_type": tasks[0],
        "tech_stack": tech[0],
        "output_type": outputs[0],
        "setup_level": setup_level,
    }
    capability_tags = list(dict.fromkeys(detail + specialty + tasks + outputs + tech + setup_requirements))
    stat = path.stat()
    relative = str(manifest_entry.get("relative_path") or path.parent.name)
    origin = str(manifest_entry.get("origin") or "user-local")
    # Always hash the bytes classified in this run. The legacy manifest may be stale
    # when a skill was edited after its last compact scan.
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    skill_id = hashlib.sha1(str(path).lower().encode("utf-8")).hexdigest()[:16]
    return {
        "skill_id": skill_id,
        "name": name,
        "canonical_name": canonical_name(name),
        "function_summary": description[:600],
        "function_detail": normalize_text(f"{description}\n{body}")[:1500],
        "selection_positive_examples": positive_examples,
        "selection_negative_examples": negative_examples,
        "headings": headings_list,
        "primary_domain": primary_domain,
        "primary_domains": primary_domains,
        "domain_detail": detail,
        "specialty": specialty,
        "task_type": tasks,
        "output_type": outputs,
        "tech_stack": tech,
        "setup_level": setup_level,
        "setup_requirements": setup_requirements,
        "capability_tags": capability_tags,
        "primary_route": route,
        "classification_evidence": {
            "domain_detail": detail_ev,
            "specialty": specialty_ev,
            "task_type": task_ev,
            "output_type": output_ev,
            "tech_stack": tech_ev,
        },
        "functional_profile": {
            "purpose": description[:1500],
            "primary_domains": primary_domains,
            "domain_labels": detail,
            "specialty_labels": specialty,
            "typical_tasks": tasks,
            "technology_labels": tech,
            "output_labels": outputs,
            "setup_requirement": setup_level,
            "setup_requirements": setup_requirements,
            "section_outline": headings_list,
        },
        "origin": origin,
        "relative_path": relative,
        "skill_md": str(path),
        "logical_skill_md": str(manifest_entry.get("logical_skill_md") or path),
        "content_hash": content_hash,
        "file_length": stat.st_size,
        "last_write_time": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "word_count": len(re.findall(r"\b\w+\b", text, re.UNICODE)),
    }


def resolve_skill_roots(values: list[str]) -> list[Path]:
    candidates: list[Path] = []
    if values:
        candidates.extend(Path(value).expanduser() for value in values if value)
    else:
        codex_home = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex")).expanduser()
        candidates.append(codex_home / "skills")
        agents_root = Path.home() / ".agents" / "skills"
        if agents_root.is_dir():
            candidates.append(agents_root)

    roots: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        key = os.path.normcase(str(resolved))
        if key in seen:
            continue
        if not resolved.is_dir():
            raise FileNotFoundError(f"Skills root does not exist: {resolved}")
        seen.add(key)
        roots.append(resolved)
    if not roots:
        raise FileNotFoundError("No local skill roots were found. Pass --skills-root explicitly.")
    return roots


def infer_origin(root: Path, path: Path, linked_external: bool = False) -> str:
    if linked_external:
        return "linked-external"
    relative_parts = {part.lower() for part in path.relative_to(root).parts}
    root_parts = {part.lower() for part in root.parts}
    if ".system" in relative_parts:
        return "official-system"
    if ".agents" in root_parts or "plugins" in root_parts:
        return "installed-topic"
    return "user-local"


def path_uses_link(root: Path, path: Path) -> bool:
    current = path
    while current != root and current.is_relative_to(root):
        try:
            details = current.lstat()
        except OSError:
            return False
        if current.is_symlink() or int(getattr(details, "st_file_attributes", 0)) & 0x400:
            return True
        current = current.parent
    return False


def discover_files(
    skills_roots: list[Path],
    manifest: dict[str, Any],
    excluded_paths: set[str],
) -> list[tuple[Path, dict[str, Any]]]:
    by_path: dict[str, tuple[Path, dict[str, Any]]] = {}
    manifest_by_path: dict[str, dict[str, Any]] = {}
    for entry in manifest.get("files", []):
        path = Path(str(entry.get("skill_md") or ""))
        key = os.path.normcase(str(path.resolve())) if path.is_file() else ""
        if not key or key in excluded_paths:
            continue
        if any(path.resolve().is_relative_to(root) for root in skills_roots):
            manifest_by_path[key] = dict(entry)
    for root in skills_roots:
        for candidate in root.rglob("SKILL.md"):
            logical = candidate.absolute()
            resolved = candidate.resolve()
            key = os.path.normcase(str(resolved))
            if key in excluded_paths:
                continue
            entry = manifest_by_path.get(key) or {
                    "relative_path": str(logical.parent.relative_to(root)),
                    "origin": infer_origin(root, logical, path_uses_link(root, logical)),
                    "skills_root": str(root),
                    "logical_skill_md": str(logical),
                }
            by_path[key] = (resolved, entry)
    return sorted(by_path.values(), key=lambda item: str(item[0]).lower())


def representative_priority(item: dict[str, Any]) -> tuple[int, int, str]:
    origin_rank = {"user-local": 5, "official-system": 4, "installed-topic": 3, "linked-external": 2}.get(item.get("origin"), 1)
    return (-origin_rank, -len(item.get("function_summary") or ""), str(item.get("relative_path") or ""))


def annotate_duplicates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        by_hash[item["content_hash"]].append(item)
        by_name[item["canonical_name"]].append(item)
    for item in items:
        exact = by_hash[item["content_hash"]]
        same_name = by_name[item["canonical_name"]]
        variants = {entry["content_hash"] for entry in same_name}
        item["exact_duplicate_count"] = len(exact)
        item["duplicate_name_count"] = len(same_name)
        item["variant_count"] = len(variants)
    representatives = [sorted(group, key=representative_priority)[0] for group in by_hash.values()]
    return sorted(representatives, key=lambda item: (item["primary_domain"], item["canonical_name"], item["skill_id"]))


LEVELS = ["primary_domain", "domain_detail", "specialty", "task_type", "tech_stack", "output_type", "setup_level"]


def facet_values(item: dict[str, Any], level: str) -> list[str]:
    if level == "primary_domain":
        return list(item.get("primary_domains") or [item.get("primary_domain") or "general"])
    if level == "setup_level":
        return list(item.get("setup_requirements") or [str(item.get("setup_level") or "none")])
    values = item.get(level) or []
    if isinstance(values, str):
        values = [values]
    return list(dict.fromkeys(str(value) for value in values if value)) or ["general"]


def build_facets(items: list[dict[str, Any]]) -> dict[str, Any]:
    facets: dict[str, dict[str, list[str]]] = {level: defaultdict(list) for level in LEVELS}
    for item in items:
        for level in LEVELS:
            for value in facet_values(item, level):
                facets[level][value].append(item["skill_id"])
    return {
        "schema_version": SCHEMA_VERSION,
        "selection_model": "multi-label-facet-intersection",
        "levels": LEVELS,
        "all_skill_ids": [item["skill_id"] for item in items],
        "facets": {
            level: {label: sorted(skill_ids) for label, skill_ids in sorted(labels.items())}
            for level, labels in facets.items()
        },
    }


def compact_route_card(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "skill_id": item["skill_id"],
        "name": item["name"],
        "canonical_name": item["canonical_name"],
        "function_summary": item["function_summary"],
        "selection_positive_examples": item.get("selection_positive_examples") or [],
        "selection_negative_examples": item.get("selection_negative_examples") or [],
        "primary_domains": item.get("primary_domains") or [item["primary_domain"]],
        "domain_detail": item["domain_detail"],
        "specialty": item["specialty"],
        "task_type": item["task_type"],
        "tech_stack": item["tech_stack"],
        "output_type": item["output_type"],
        "setup_level": item["setup_level"],
        "setup_requirements": item.get("setup_requirements") or [item["setup_level"]],
        "capability_tags": item["capability_tags"],
        "origin": item["origin"],
        "skill_md": item["skill_md"],
        "logical_skill_md": item.get("logical_skill_md") or item["skill_md"],
        "exact_duplicate_count": int(item.get("exact_duplicate_count") or 1),
        "variant_count": int(item.get("variant_count") or 1),
        "function_purpose": item.get("function_purpose") or item.get("function_summary") or "",
        "function_weight": int(item.get("function_weight") or 100),
        "aliases": item.get("aliases") or [],
        "does": item.get("does") or item.get("can_do") or item.get("selection_positive_examples") or [],
        "does_not": item.get("does_not") or item.get("cannot_do") or item.get("selection_negative_examples") or [],
        "can_do": item.get("can_do") or item.get("does") or item.get("selection_positive_examples") or [],
        "cannot_do": item.get("cannot_do") or item.get("does_not") or item.get("selection_negative_examples") or [],
    }


def build_tree(items: list[dict[str, Any]]) -> dict[str, Any]:
    root: dict[str, Any] = {"level": "root", "name": "all-skills", "display_name": "总前台", "count": len(items), "children": {}}
    for item in items:
        node = root
        for level in LEVELS:
            value = str(item["primary_route"].get(level) or "general")
            children = node.setdefault("children", {})
            child = children.setdefault(value, {
                "level": level,
                "name": value,
                "display_name": ZH_LABELS.get(value, value),
                "count": 0,
                "search_terms": [],
                "children": {},
            })
            child["count"] += 1
            child["search_terms"].append(item["canonical_name"])
            node = child
        node.setdefault("skill_ids", []).append(item["skill_id"])
    return root


def add_adaptive_catalog_shards(root: dict[str, Any], cards: dict[str, dict[str, Any]], leaf_target: int) -> int:
    """Split semantically identical oversized leaves into small, navigable name ranges."""
    shard_count = 0

    def split_leaf(node: dict[str, Any], depth: int) -> None:
        nonlocal shard_count
        skill_ids = list(node.get("skill_ids", []))
        if len(skill_ids) <= leaf_target:
            return
        ordered = sorted(skill_ids, key=lambda skill_id: (cards[skill_id]["canonical_name"], skill_id))
        chunk_size = max(leaf_target, math.ceil(len(ordered) / 8))
        node.pop("skill_ids", None)
        children = node.setdefault("children", {})
        for index, start in enumerate(range(0, len(ordered), chunk_size), 1):
            group = ordered[start : start + chunk_size]
            first_name = cards[group[0]]["canonical_name"]
            last_name = cards[group[-1]]["canonical_name"]
            name = f"shard-{depth}-{index}-{safe_slug(first_name)[:24]}-{safe_slug(last_name)[:24]}"
            display_name = f"名称索引 {first_name} ～ {last_name}"
            child = {
                "level": f"catalog_shard_{depth}",
                "name": name,
                "display_name": display_name,
                "count": len(group),
                "search_terms": [cards[skill_id]["canonical_name"] for skill_id in group],
                "children": {},
                "skill_ids": group,
            }
            children[name] = child
            shard_count += 1
            split_leaf(child, depth + 1)

    def walk(node: dict[str, Any]) -> None:
        original_children = list(node.get("children", {}).values())
        for child in original_children:
            walk(child)
        if node.get("skill_ids"):
            split_leaf(node, 1)

    walk(root)
    return shard_count


def serialize_tree(node: dict[str, Any], path: list[str] | None = None) -> dict[str, Any]:
    path = path or []
    current_path = path
    if node.get("level") != "root":
        current_path = path + [f"{node['level']}={node['name']}"]
    result = {k: v for k, v in node.items() if k != "children"}
    result["path"] = "|".join(current_path)
    result["children"] = [
        serialize_tree(child, current_path)
        for child in sorted(node.get("children", {}).values(), key=lambda item: (-item["count"], item["name"]))
    ]
    return result


def write_hierarchy_markdown(path: Path, tree: dict[str, Any], cards: dict[str, dict[str, Any]], leaf_target: int) -> None:
    lines = [
        "# 本机 Skill 医院式分诊目录",
        "",
        f"- 生成时间: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- 唯一内容候选: `{tree['count']}`",
        f"- 建议进入医生列表的候选阈值: `{leaf_target}`",
        "- 路径: 总前台 → 一级领域 → 二级领域 → 专科 → 任务 → 技术栈 → 输出 → 环境 → skill",
        "",
    ]

    def walk(node: dict[str, Any], depth: int) -> None:
        for child in node.get("children", []):
            indent = "  " * depth
            lines.append(f"{indent}- **{child['display_name']}** (`{child['name']}`, {child['count']})")
            walk(child, depth + 1)
            if child.get("skill_ids"):
                for skill_id in child["skill_ids"]:
                    card = cards[skill_id]
                    lines.append(f"{'  ' * (depth + 1)}- `{card['name']}` — {card['function_summary'][:180]}")

    walk(tree, 0)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_catalog(path: Path, items: Iterable[dict[str, Any]]) -> None:
    lines = [
        "# 全量 Skill 详细功能标注目录",
        "",
        "本文件用于人工审计。普通 skill 选择不得把本文件整体载入模型上下文。",
        "",
    ]
    for item in items:
        route = " → ".join(item["primary_route"][level] for level in LEVELS)
        lines.extend([
            f"## {item['name']}",
            "",
            f"- 安装位置: `{item['relative_path']}`",
            f"- 功能说明: {item.get('function_detail') or item['function_summary']}",
            f"- 主分诊路径: {route}",
            f"- 一级领域: {', '.join(item.get('primary_domains') or [item['primary_domain']])}",
            f"- 二级领域标签: {', '.join(item['domain_detail'])}",
            f"- 专科标签: {', '.join(item['specialty'])}",
            f"- 任务标签: {', '.join(item['task_type'])}",
            f"- 技术栈标签: {', '.join(item['tech_stack'])}",
            f"- 输出标签: {', '.join(item['output_type'])}",
            f"- 环境要求: {item['setup_level']}",
            f"- 文档章节: {', '.join(item.get('headings') or []) or '未提供明确章节'}",
            f"- 重复与版本: exact={item['exact_duplicate_count']}, same-name={item['duplicate_name_count']}, variants={item['variant_count']}",
            f"- 文件统计: {item['word_count']} words, {item['file_length']} bytes, modified={item['last_write_time']}",
            "",
        ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def robust_remove(path: Path) -> None:
    if not path.exists():
        return
    for attempt in range(8):
        try:
            shutil.rmtree(path)
            return
        except OSError:
            time.sleep(0.4 * (attempt + 1))
    shutil.rmtree(path)


@contextmanager
def exclusive_publish_lock(lock_path: Path, timeout_seconds: float):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    descriptor: int | None = None
    while descriptor is None:
        try:
            descriptor = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
                if age > max(300.0, timeout_seconds * 2):
                    lock_path.unlink()
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() - started >= timeout_seconds:
                raise TimeoutError(f"Timed out waiting for deep-index publish lock: {lock_path}")
            time.sleep(0.1)
    os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
    try:
        yield
    finally:
        os.close(descriptor)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def load_lazy_index():
    path = Path(__file__).resolve().parent / "lazy-index.py"
    spec = importlib.util.spec_from_file_location("skill_lazy_index", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def existing_facet_labels(facets: dict[str, Any]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {level: set() for level in LEVELS}
    for level, labels in (facets.get("facets") or {}).items():
        result.setdefault(str(level), set()).update(str(label) for label in labels)
    return result


def replace_ndjson_item(path: Path, item: dict[str, Any]) -> None:
    lines: list[str] = []
    replaced = False
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip():
                continue
            current = json.loads(line)
            if current.get("skill_id") == item["skill_id"] or os.path.normcase(str(current.get("skill_md") or "")) == os.path.normcase(str(item.get("skill_md") or "")):
                lines.append(json.dumps(item, ensure_ascii=False, separators=(",", ":")))
                replaced = True
            else:
                lines.append(line)
    if not replaced:
        lines.append(json.dumps(item, ensure_ascii=False, separators=(",", ":")))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def existing_labels_from_store(lazy, database: Path, facets: dict[str, Any]) -> dict[str, set[str]]:
    labels = {level: set() for level in LEVELS}
    for tag in lazy.list_tags(database):
        labels.setdefault(str(tag.get("level") or ""), set()).add(str(tag.get("label") or ""))
    if any(labels.values()):
        return labels
    return existing_facet_labels(facets)


def patch_source_manifest(source: dict[str, Any], path: Path, item: dict[str, Any] | None, delete: bool = False) -> dict[str, Any]:
    files = list(source.get("files") or [])
    remaining = []
    for entry in files:
        if os.path.normcase(str(entry.get("skill_md") or "")) == os.path.normcase(str(path)):
            continue
        remaining.append(entry)
    if not delete and item is not None:
        remaining.append({
            "skill_md": str(path),
            "logical_skill_md": str(path),
            "file_length": item["file_length"],
            "last_write_ns": path.stat().st_mtime_ns,
            "content_hash": item["content_hash"],
            "classification_status": "success",
        })
    source["files"] = remaining
    source["source_snapshot"] = hashlib.sha256(
        "\n".join(
            f"{entry['skill_md']}|{entry['file_length']}|{entry.get('last_write_ns', 0)}"
            for entry in sorted(remaining, key=lambda value: os.path.normcase(str(value.get("skill_md") or "")))
        ).encode("utf-8")
    ).hexdigest()
    return source


def ingest_one_skill(skill_md: Path, skill_dir: Path, index_dir: Path, lock_timeout: float) -> dict[str, Any]:
    deep_dir = index_dir / "deep"
    metadata_path = deep_dir / "metadata.json"
    database_path = deep_dir / "lazy-route.sqlite3"
    if not metadata_path.exists() and not database_path.exists():
        raise FileNotFoundError("Deep index is missing. Run a first full classification before ingesting a single skill.")
    path = skill_md.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Skill file does not exist: {path}")

    rules_path = skill_dir / "rules" / "categories.json"
    rules = load_json(rules_path)
    overlay_path = deep_dir / OVERLAY_FILE
    overlay = load_tag_overlay(overlay_path)
    rules = merge_overlay_into_rules(rules, overlay)
    compiled_rules = {
        "domain_detail": compile_rules(rules.get("domain_detail_rules", {})),
        "specialty": compile_rules(rules.get("specialty_rules", {})),
        "task_type": compile_rules(rules.get("task_rules", {})),
        "output_type": compile_rules(rules.get("output_rules", {})),
        "tech_stack": compile_rules(TECH_RULES),
    }
    lazy = load_lazy_index()
    database = deep_dir / "lazy-route.sqlite3"
    if database.exists():
        lazy.migrate_database(database)
    facets = {"facets": {}}
    keywords = load_json(deep_dir / "label-keywords.json") if (deep_dir / "label-keywords.json").exists() else {}
    metadata = load_json(metadata_path) if metadata_path.exists() else {"schema_version": SCHEMA_VERSION}
    source = load_json(deep_dir / "source-manifest.json") if (deep_dir / "source-manifest.json").exists() else {"files": []}
    existing_labels = existing_labels_from_store(lazy, database, facets)

    document = path.read_text(encoding="utf-8-sig", errors="replace")
    entry = {
        "relative_path": path.parent.name,
        "origin": "user-local",
        "logical_skill_md": str(path),
    }
    item = classify_document(document, path, entry, rules, compiled_rules)
    _, body = parse_frontmatter(document)
    enrich_function_profile(item, body)
    created_tags = apply_new_domain_tags(item, existing_labels, overlay, rules)
    item["exact_duplicate_count"] = int(item.get("exact_duplicate_count") or 1)
    item["duplicate_name_count"] = int(item.get("duplicate_name_count") or 1)
    item["variant_count"] = int(item.get("variant_count") or 1)
    card = compact_route_card(item)
    memberships = [
        (level, label, item["skill_id"])
        for level in LEVELS
        for label in facet_values(item, level)
    ]

    with exclusive_publish_lock(index_dir / ".deep-publish.lock", lock_timeout):
        if (deep_dir / "source-manifest.json").exists() or source.get("files"):
            source = patch_source_manifest(source, path, item, delete=False)
            dump_json(deep_dir / "source-manifest.json", source)
        sqlite_result = lazy.upsert_skill(database, deep_dir, card, memberships, created_tags)
        metadata["raw_files"] = len(source.get("files") or [])
        metadata["classified_files"] = metadata["raw_files"]
        metadata["unique_content_candidates"] = int(sqlite_result.get("skills") or metadata.get("unique_content_candidates") or 0)
        metadata["generated_at"] = datetime.now().isoformat(timespec="seconds")
        metadata["source_snapshot"] = source["source_snapshot"]
        metadata["full_body_read"] = False
        metadata["incremental_reuse_enabled"] = True
        metadata["reclassified_files"] = 1
        metadata["reused_files"] = max(0, int(metadata["raw_files"]) - 1)
        metadata["ingest_mode"] = "sqlite_upsert"
        dump_json(metadata_path, metadata)
        if (deep_dir / "label-keywords.json").exists():
            keywords.setdefault("domain_detail", {})
            keywords.setdefault("specialty", {})
            keywords.setdefault("primary_map", {})
            for tag in created_tags:
                keywords[tag["level"]][tag["label"]] = tag["keywords"]
                if tag.get("aliases"):
                    alias_key = "query_cn_specialty_words" if tag["level"] == "specialty" else "query_cn_detail_words"
                    current = list(keywords.setdefault(alias_key, {}).get(tag["label"]) or [])
                    keywords[alias_key][tag["label"]] = list(dict.fromkeys([*current, *list(tag.get("aliases") or [])]))
            keywords["primary_map"].update(overlay.get("primary_map") or {})
            dump_json(deep_dir / "label-keywords.json", keywords)
        dump_json(overlay_path, overlay)

    return {
        "status": "ok",
        "mode": "ingest_skill",
        "scanned_files": 1,
        "full_library_scan": False,
        "json_cards_rewritten": False,
        "skill_name": item["name"],
        "skill_id": item["skill_id"],
        "skill_md": str(path),
        "function_summary": item["function_summary"],
        "function_purpose": item.get("function_purpose") or "",
        "created_tags": [tag for tag in created_tags if not tag.get("merged")],
        "merged_tags": [tag for tag in created_tags if tag.get("merged")],
        "capability_tags": item["capability_tags"],
        "sqlite": sqlite_result,
        "index_dir": str(index_dir),
    }


def delete_one_skill(skill_md: Path, index_dir: Path, lock_timeout: float) -> dict[str, Any]:
    deep_dir = index_dir / "deep"
    path = skill_md.expanduser().resolve()
    lazy = load_lazy_index()
    database = deep_dir / "lazy-route.sqlite3"
    metadata_path = deep_dir / "metadata.json"
    source = load_json(deep_dir / "source-manifest.json") if (deep_dir / "source-manifest.json").exists() else {"files": []}
    with exclusive_publish_lock(index_dir / ".deep-publish.lock", lock_timeout):
        sqlite_result = lazy.delete_skill(database, skill_md=str(path))
        source = patch_source_manifest(source, path, None, delete=True)
        dump_json(deep_dir / "source-manifest.json", source)
        if metadata_path.exists():
            metadata = load_json(metadata_path)
            metadata["raw_files"] = len(source.get("files") or [])
            metadata["classified_files"] = metadata["raw_files"]
            metadata["unique_content_candidates"] = int(sqlite_result.get("skills") or 0)
            metadata["ingest_mode"] = "sqlite_delete"
            dump_json(metadata_path, metadata)
    return {
        "status": sqlite_result.get("status") or "ok",
        "mode": "delete_skill",
        "scanned_files": 0,
        "full_library_scan": False,
        "json_cards_rewritten": False,
        "skill_md": str(path),
        "sqlite": sqlite_result,
        "index_dir": str(index_dir),
    }



def refresh_function_profiles(index_dir: Path, lock_timeout: float = 120.0) -> dict[str, Any]:
    """Rebuild can-do / cannot-do fields from classified records without reading source skills."""
    deep_dir = index_dir / "deep"
    ndjson_path = deep_dir / "skills-deep-index.ndjson"
    if not ndjson_path.exists():
        raise FileNotFoundError("Classified index is missing. Run a full classification first.")
    items: list[dict[str, Any]] = []
    with ndjson_path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            if not line.strip():
                continue
            item = json.loads(line)
            enrich_function_profile(item, str(item.get("function_detail") or item.get("function_summary") or ""))
            items.append(item)
    for item in items:
        item["exact_duplicate_count"] = int(item.get("exact_duplicate_count") or 1)
        item["variant_count"] = int(item.get("variant_count") or 1)
    representatives = annotate_duplicates(items) if items else []
    cards = {item["skill_id"]: compact_route_card(item) for item in representatives}
    lazy = load_lazy_index()
    database = deep_dir / "lazy-route.sqlite3"
    with exclusive_publish_lock(index_dir / ".deep-publish.lock", lock_timeout):
        dump_json(deep_dir / "route-cards.json", cards)
        with ndjson_path.open("w", encoding="utf-8", newline="\n") as handle:
            for item in items:
                handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
        if database.exists():
            try:
                database.unlink()
            except OSError:
                pass
        sqlite_result = lazy.build_database(deep_dir, database)
        metadata_path = deep_dir / "metadata.json"
        if metadata_path.exists():
            metadata = load_json(metadata_path)
            metadata["function_profiles_refreshed"] = True
            metadata["sqlite"] = sqlite_result
            dump_json(metadata_path, metadata)
    return {
        "status": "ok",
        "mode": "refresh_profiles",
        "full_library_scan": False,
        "read_skill_bodies": False,
        "refreshed": len(cards),
        "sqlite": sqlite_result,
        "index_dir": str(index_dir),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Exhaustively classify every local SKILL.md into a deep hospital-style hierarchy.")
    parser.add_argument(
        "--skills-root",
        action="append",
        default=[],
        help="A local skills root to discover recursively. Repeat for multiple roots.",
    )
    parser.add_argument("--skill-dir", default="")
    parser.add_argument("--index-dir", default="")
    parser.add_argument("--leaf-target", type=int, default=DEFAULT_LEAF_TARGET)
    parser.add_argument(
        "--reuse-existing",
        action="store_true",
        help="Deprecated compatibility flag. Incremental reuse is now enabled by default.",
    )
    parser.add_argument("--full-rebuild", action="store_true", help="Disable incremental reuse and classify every discovered file again.")
    parser.add_argument("--strict", action="store_true", help="Return a non-zero exit code when any source fails classification.")
    parser.add_argument("--lock-timeout", type=float, default=120.0, help="Seconds to wait for another process publishing the same deep index.")
    parser.add_argument(
        "--ingest-skill",
        default="",
        help="Classify and insert one SKILL.md into the existing index without scanning the rest of the library.",
    )
    parser.add_argument(
        "--delete-skill",
        default="",
        help="Remove one SKILL.md from the SQLite index without scanning the rest of the library.",
    )
    parser.add_argument(
        "--refresh-profiles",
        action="store_true",
        help="Rebuild can-do / cannot-do profiles from the existing classified index without rereading SKILL.md files.",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    skill_dir = Path(args.skill_dir).expanduser().resolve() if args.skill_dir else script_dir.parent
    index_dir = Path(args.index_dir).expanduser().resolve() if args.index_dir else skill_dir / ".skill-index"
    if args.delete_skill:
        result = delete_one_skill(Path(args.delete_skill), index_dir, args.lock_timeout)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.ingest_skill:
        result = ingest_one_skill(Path(args.ingest_skill), skill_dir, index_dir, args.lock_timeout)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.refresh_profiles:
        result = refresh_function_profiles(index_dir, lock_timeout=args.lock_timeout)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("status") == "ok" else 1
    skills_roots = resolve_skill_roots(args.skills_root)
    skills_root = skills_roots[0]
    manifest_path = index_dir / "manifest.json"
    rules_path = skill_dir / "rules" / "categories.json"
    if not rules_path.exists():
        raise FileNotFoundError(f"Missing rules: {rules_path}")

    manifest = load_json(manifest_path) if manifest_path.exists() else {"files": []}
    rules = load_json(rules_path)
    existing_deep = index_dir / "deep"
    overlay = load_tag_overlay(existing_deep / OVERLAY_FILE)
    rules = merge_overlay_into_rules(rules, overlay)
    compiled_rules = {
        "domain_detail": compile_rules(rules.get("domain_detail_rules", {})),
        "specialty": compile_rules(rules.get("specialty_rules", {})),
        "task_type": compile_rules(rules.get("task_rules", {})),
        "output_type": compile_rules(rules.get("output_rules", {})),
        "tech_stack": compile_rules(TECH_RULES),
    }
    items: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    source_files: list[dict[str, Any]] = []
    reused_generated_at = ""
    reused_count = 0
    reclassified_count = 0
    rules_fingerprint = hashlib.sha256(rules_path.read_bytes()).hexdigest()
    classifier_fingerprint = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    existing_metadata: dict[str, Any] = {}
    existing_items: dict[str, dict[str, Any]] = {}
    existing_sources: dict[str, dict[str, Any]] = {}

    def path_key(value: str | Path) -> str:
        return os.path.normcase(str(Path(value).expanduser().resolve()))

    incremental_compatible = False
    required_existing = [
        existing_deep / "metadata.json",
        existing_deep / "source-manifest.json",
        existing_deep / "skills-deep-index.ndjson",
    ]
    if not args.full_rebuild and all(path.exists() for path in required_existing):
        try:
            existing_metadata = load_json(required_existing[0])
            existing_manifest = load_json(required_existing[1])
            with required_existing[2].open("r", encoding="utf-8-sig") as handle:
                old_items = [json.loads(line) for line in handle if line.strip()]
            existing_items = {path_key(item["skill_md"]): item for item in old_items if item.get("skill_md")}
            existing_sources = {
                path_key(entry["skill_md"]): entry
                for entry in existing_manifest.get("files", [])
                if entry.get("skill_md")
            }
            incremental_compatible = (
                existing_metadata.get("schema_version") == SCHEMA_VERSION
                and existing_metadata.get("rules_fingerprint") == rules_fingerprint
                and existing_metadata.get("classifier_fingerprint") == classifier_fingerprint
            )
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            incremental_compatible = False

    excluded_paths = {os.path.normcase(str((skill_dir / "SKILL.md").resolve()))}
    files = discover_files(skills_roots, manifest, excluded_paths)
    files_count = len(files)
    current_keys = {path_key(path) for path, _ in files}
    previous_keys = set(existing_sources) | set(existing_items)
    removed_count = len(previous_keys - current_keys)
    log(
        f"Discovered {files_count} SKILL.md files; "
        f"incremental_reuse={'enabled' if incremental_compatible else 'disabled'}"
    )
    for index, (path, entry) in enumerate(files, 1):
        key = path_key(path)
        stat = path.stat()
        old_source = existing_sources.get(key, {})
        old_item = existing_items.get(key)
        unchanged = (
            incremental_compatible
            and old_item is not None
            and old_source.get("classification_status", "success") == "success"
            and int(old_source.get("file_length", -1)) == stat.st_size
            and int(old_source.get("last_write_ns", -1)) == stat.st_mtime_ns
        )
        if unchanged:
            if not old_item.get("primary_domains"):
                profile_domains = (old_item.get("functional_profile") or {}).get("primary_domains") or []
                route_domains = (old_item.get("primary_route") or {}).get("primary_domains") or []
                old_item["primary_domains"] = list(profile_domains or route_domains or [old_item.get("primary_domain") or "general"])
            items.append(old_item)
            source_files.append({
                "skill_md": str(path),
                "logical_skill_md": str(entry.get("logical_skill_md") or path),
                "file_length": stat.st_size,
                "last_write_ns": stat.st_mtime_ns,
                "content_hash": old_source.get("content_hash") or old_item.get("content_hash", ""),
                "classification_status": "success",
            })
            reused_count += 1
        else:
            reclassified_count += 1
            document: str | None = None
            try:
                document = path.read_text(encoding="utf-8-sig", errors="replace")
                item = classify_document(document, path, entry, rules, compiled_rules)
                _, body = parse_frontmatter(document)
                enrich_function_profile(item, body)
                items.append(item)
                source_files.append({
                    "skill_md": str(path),
                    "logical_skill_md": str(entry.get("logical_skill_md") or path),
                    "file_length": stat.st_size,
                    "last_write_ns": stat.st_mtime_ns,
                    "content_hash": item["content_hash"],
                    "classification_status": "success",
                })
            except Exception as exc:  # keep every discovered source in the audit trail
                failure = {"skill_md": str(path), "error": str(exc)}
                failures.append(failure)
                source_files.append({
                    "skill_md": str(path),
                    "logical_skill_md": str(entry.get("logical_skill_md") or path),
                    "file_length": stat.st_size,
                    "last_write_ns": stat.st_mtime_ns,
                    "content_hash": hashlib.sha256(document.encode("utf-8")).hexdigest() if document is not None else "",
                    "classification_status": "failed",
                    "classification_error": str(exc),
                })
        if index % 250 == 0 or index == files_count:
            log(
                f"Processed {index}/{files_count}; reused={reused_count}, "
                f"reclassified={reclassified_count}, failures={len(failures)}"
            )
    if reused_count:
        reused_generated_at = str(existing_metadata.get("generated_at") or "")

    representatives = annotate_duplicates(items)
    cards = {item["skill_id"]: item for item in representatives}
    facets = build_facets(representatives)
    raw_tree = build_tree(representatives)
    adaptive_shards = add_adaptive_catalog_shards(raw_tree, cards, args.leaf_target)
    tree = serialize_tree(raw_tree)
    route_counts = Counter()
    def collect_route_counts(node: dict[str, Any]) -> None:
        if node.get("level") != "root":
            route_counts[node["path"]] = int(node.get("count") or 0)
        for child in node.get("children", []):
            collect_route_counts(child)
    collect_route_counts(tree)

    temp_dir = index_dir / f"deep-build-{os.getpid()}"
    final_dir = index_dir / "deep"
    backup_dir = index_dir / "deep-backup"
    robust_remove(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().isoformat(timespec="seconds")
    source_snapshot = hashlib.sha256(
        "\n".join(
            f"{entry['skill_md']}|{entry['file_length']}|{entry['last_write_ns']}"
            for entry in sorted(source_files, key=lambda value: os.path.normcase(value["skill_md"]))
        ).encode("utf-8")
    ).hexdigest()
    metadata = {
        "generated_at": generated_at,
        "schema_version": SCHEMA_VERSION,
        "index_scope": "installing-user-local-skills-exhaustive",
        "skills_root": str(skills_root),
        "skills_roots": [str(root) for root in skills_roots],
        "skill_instance_dir": str(skill_dir),
        "source_snapshot": source_snapshot,
        "rules_path": str(rules_path.resolve()),
        "rules_fingerprint": rules_fingerprint,
        "classifier_path": str(Path(__file__).resolve()),
        "classifier_fingerprint": classifier_fingerprint,
        "raw_files": files_count,
        "classified_files": len(items),
        "unique_content_candidates": len(representatives),
        "failures": len(failures),
        "levels": LEVELS,
        "leaf_target": args.leaf_target,
        "full_body_read": reclassified_count == files_count,
        "all_records_derived_from_full_body": True,
        "adaptive_catalog_shards": adaptive_shards,
        "classification_reused_from": reused_generated_at,
        "incremental_reuse_enabled": incremental_compatible,
        "reused_files": reused_count,
        "reclassified_files": reclassified_count,
        "removed_files": removed_count,
        "failed_files": len(failures),
        "multi_label_facets": True,
        "detailed_function_profiles": True,
    }
    dump_json(temp_dir / "metadata.json", metadata)
    dump_json(temp_dir / "source-manifest.json", {
        "schema_version": SCHEMA_VERSION,
        "skills_roots": [str(root) for root in skills_roots],
        "excluded_paths": [str((skill_dir / "SKILL.md").resolve())],
        "source_snapshot": source_snapshot,
        "files": source_files,
    })
    dump_json(temp_dir / "hierarchy.json", tree)
    dump_json(temp_dir / "route-counts.json", dict(sorted(route_counts.items())))
    dump_json(temp_dir / "failures.json", failures)
    dump_json(temp_dir / "facets.json", facets)
    dump_json(temp_dir / "route-cards.json", {
        item["skill_id"]: compact_route_card(item) for item in representatives
    })
    dump_json(temp_dir / "label-keywords.json", {
        "primary_map": rules.get("primary_map", {}),
        "domain_detail": rules.get("domain_detail_rules", {}),
        "specialty": rules.get("specialty_rules", {}),
        "task_type": rules.get("task_rules", {}),
        "output_type": rules.get("output_rules", {}),
        "tech_stack": TECH_RULES,
        "query_cn_detail_words": rules.get("query_cn_detail_words", {}),
        "query_cn_specialty_words": rules.get("query_cn_specialty_words", {}),
        "query_cn_task_words": rules.get("query_cn_task_words", {}),
    })
    dump_json(temp_dir / OVERLAY_FILE, overlay)
    with (temp_dir / "skills-deep-index.ndjson").open("w", encoding="utf-8", newline="\n") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
    with (temp_dir / "skills-deep-index.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["name", "relative_path", "function_summary", *LEVELS, "all_tags", "skill_md"])
        for item in items:
            writer.writerow([
                item["name"], item["relative_path"], item["function_summary"],
                *[item["primary_route"][level] for level in LEVELS],
                ";".join(item["capability_tags"]), item["skill_md"],
            ])
    write_hierarchy_markdown(temp_dir / "HOSPITAL_DIRECTORY.md", tree, cards, args.leaf_target)
    write_catalog(temp_dir / "DETAILED_SKILL_CATALOG.md", items)
    log("Deep files written; atomically replacing the previous deep index")
    with exclusive_publish_lock(index_dir / ".deep-publish.lock", args.lock_timeout):
        robust_remove(backup_dir)
        moved_previous = False
        try:
            if final_dir.exists():
                last_error: OSError | None = None
                for attempt in range(8):
                    try:
                        final_dir.rename(backup_dir)
                        last_error = None
                        break
                    except OSError as exc:
                        last_error = exc
                        time.sleep(0.25 * (attempt + 1))
                if last_error is not None:
                    # Windows can keep a generated SQLite file handle open briefly;
                    # the index is disposable, so fall back to replacing it in place.
                    robust_remove(final_dir)
                    last_error = None
                    moved_previous = False
                else:
                    moved_previous = True
            last_error = None
            for attempt in range(8):
                try:
                    temp_dir.rename(final_dir)
                    last_error = None
                    break
                except OSError as exc:
                    last_error = exc
                    time.sleep(0.25 * (attempt + 1))
            if last_error is not None:
                raise last_error
        except Exception:
            if moved_previous and backup_dir.exists() and not final_dir.exists():
                backup_dir.rename(final_dir)
            raise
        else:
            robust_remove(backup_dir)
    log(f"Completed: raw={files_count}, classified={len(items)}, unique={len(representatives)}, failures={len(failures)}")
    try:
        lazy = load_lazy_index()
        database = final_dir / "lazy-route.sqlite3"
        if database.exists():
            try:
                database.unlink()
            except OSError:
                stale = database.with_suffix(".sqlite3.stale")
                try:
                    stale.unlink()
                except FileNotFoundError:
                    pass
                database.replace(stale)
        sqlite_result = lazy.build_database(final_dir, database)
        log(f"SQLite rebuilt: {sqlite_result.get('status')} skills={sqlite_result.get('skills')}")
        metadata["sqlite"] = sqlite_result
        dump_json(final_dir / "metadata.json", metadata)
    except Exception as exc:
        log(f"SQLite rebuild failed: {exc}")
        metadata["sqlite_error"] = str(exc)
        dump_json(final_dir / "metadata.json", metadata)
    build_status = "degraded" if failures else "ok"
    print(json.dumps({"status": build_status, **metadata, "output_dir": str(final_dir)}, ensure_ascii=False, indent=2))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
