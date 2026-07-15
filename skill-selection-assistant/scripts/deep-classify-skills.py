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
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "2.3.0"
DEFAULT_LEAF_TARGET = 24
MAX_TAGS = {
    "domain_detail": 6,
    "specialty": 8,
    "task_type": 6,
    "output_type": 6,
    "tech_stack": 10,
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
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def dump_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
        body_hits = count_matches(pattern, body)
        if body_hits:
            score += body_hits * 2
            sources.append("full_body")
        if score >= minimum:
            scored.append((label, score))
            evidence[label] = {"score": score, "sources": sources, "body_hits": body_hits}
    scored.sort(key=lambda item: (-item[1], item[0]))
    if scored:
        floor = max(minimum, int(scored[0][1] * 0.45))
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


def infer_setup(description: str, body: str) -> str:
    lowered = setup_evidence(description, body).lower()
    if re.search(r"api[- ]?key|secret key|access token|credentials?|[a-z][a-z0-9_]+_(?:api_)?key|密钥|令牌", lowered):
        return "api-key"
    if re.search(r"oauth|sign[ -]?in|log[ -]?in|account|workspace selection|账号|登录", lowered):
        return "account"
    if re.search(r"download|internet access|network access|clone |curl |wget |联网|下载", lowered):
        return "network"
    if re.search(r"npm install|pnpm install|pip install|install dependencies|docker|runtime|toolchain|安装依赖|运行环境", lowered):
        return "local-runtime"
    return "none"


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
    headings_list = [normalize_text(m.group(1)) for m in re.finditer(r"(?m)^#{1,4}\s+(.+?)\s*$", body)]
    headings_list = [value for value in headings_list if value][:20]
    headings = " ".join(headings_list)

    detail, detail_ev = score_rule_set(
        name, description, headings, body,
        compiled_rules["domain_detail"], 6, MAX_TAGS["domain_detail"]
    )
    specialty, specialty_ev = score_rule_set(
        name, description, headings, body,
        compiled_rules["specialty"], 6, MAX_TAGS["specialty"]
    )
    tasks, task_ev = score_rule_set(
        name, description, headings, body,
        compiled_rules["task_type"], 5, MAX_TAGS["task_type"]
    )
    outputs, output_ev = score_rule_set(
        name, description, headings, body,
        compiled_rules["output_type"], 5, MAX_TAGS["output_type"]
    )
    tech, tech_ev = score_rule_set(
        name, description, headings, body,
        compiled_rules["tech_stack"], 6, MAX_TAGS["tech_stack"]
    )

    if not detail:
        detail = ["coding-general" if re.search(r"code|script|software|program|代码|开发", f"{name} {description}", re.I) else "general"]
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
    setup_level = infer_setup(description, body)
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
    capability_tags = list(dict.fromkeys(detail + specialty + tasks + outputs + tech + [setup_level]))
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
        "headings": headings_list,
        "primary_domain": primary_domain,
        "primary_domains": primary_domains,
        "domain_detail": detail,
        "specialty": specialty,
        "task_type": tasks,
        "output_type": outputs,
        "tech_stack": tech,
        "setup_level": setup_level,
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
            "section_outline": headings_list,
        },
        "origin": origin,
        "relative_path": relative,
        "skill_md": str(path),
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


def infer_origin(root: Path, path: Path) -> str:
    relative_parts = {part.lower() for part in path.relative_to(root).parts}
    root_parts = {part.lower() for part in root.parts}
    if ".system" in relative_parts:
        return "official-system"
    if ".agents" in root_parts or "plugins" in root_parts:
        return "installed-topic"
    return "user-local"


def discover_files(
    skills_roots: list[Path],
    manifest: dict[str, Any],
    excluded_paths: set[str],
) -> list[tuple[Path, dict[str, Any]]]:
    by_path: dict[str, tuple[Path, dict[str, Any]]] = {}
    for entry in manifest.get("files", []):
        path = Path(str(entry.get("skill_md") or ""))
        key = os.path.normcase(str(path.resolve())) if path.is_file() else ""
        if key and key not in excluded_paths:
            by_path[key] = (path.resolve(), dict(entry))
    for root in skills_roots:
        for candidate in root.rglob("SKILL.md"):
            resolved = candidate.resolve()
            key = os.path.normcase(str(resolved))
            if key in excluded_paths:
                continue
            by_path.setdefault(key, (
                resolved,
                {
                    "relative_path": str(resolved.parent.relative_to(root)),
                    "origin": infer_origin(root, resolved),
                    "skills_root": str(root),
                },
            ))
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
        return [str(item.get("setup_level") or "none")]
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
        "primary_domains": item.get("primary_domains") or [item["primary_domain"]],
        "domain_detail": item["domain_detail"],
        "specialty": item["specialty"],
        "task_type": item["task_type"],
        "tech_stack": item["tech_stack"],
        "output_type": item["output_type"],
        "setup_level": item["setup_level"],
        "capability_tags": item["capability_tags"],
        "origin": item["origin"],
        "skill_md": item["skill_md"],
        "exact_duplicate_count": item["exact_duplicate_count"],
        "variant_count": item["variant_count"],
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
    parser.add_argument("--reuse-existing", action="store_true", help="Reuse the last full-body classification and rebuild hierarchy/output files only.")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    skill_dir = Path(args.skill_dir).expanduser().resolve() if args.skill_dir else script_dir.parent
    skills_roots = resolve_skill_roots(args.skills_root)
    skills_root = skills_roots[0]
    index_dir = Path(args.index_dir).expanduser().resolve() if args.index_dir else skill_dir / ".skill-index"
    manifest_path = index_dir / "manifest.json"
    rules_path = skill_dir / "rules" / "categories.json"
    if not rules_path.exists():
        raise FileNotFoundError(f"Missing rules: {rules_path}")

    manifest = load_json(manifest_path) if manifest_path.exists() else {"files": []}
    rules = load_json(rules_path)
    compiled_rules = {
        "domain_detail": compile_rules(rules.get("domain_detail_rules", {})),
        "specialty": compile_rules(rules.get("specialty_rules", {})),
        "task_type": compile_rules(rules.get("task_rules", {})),
        "output_type": compile_rules(rules.get("output_rules", {})),
        "tech_stack": compile_rules(TECH_RULES),
    }
    items: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    reused_generated_at = ""
    existing_deep = index_dir / "deep"
    if args.reuse_existing:
        existing_metadata = load_json(existing_deep / "metadata.json")
        reused_generated_at = str(existing_metadata.get("generated_at") or "")
        with (existing_deep / "skills-deep-index.ndjson").open("r", encoding="utf-8-sig") as handle:
            items = [json.loads(line) for line in handle if line.strip()]
        for item in items:
            if not item.get("primary_domains"):
                profile_domains = (item.get("functional_profile") or {}).get("primary_domains") or []
                route_domains = (item.get("primary_route") or {}).get("primary_domains") or []
                item["primary_domains"] = list(profile_domains or route_domains or [item.get("primary_domain") or "general"])
        failures = load_json(existing_deep / "failures.json")
        log(f"Reusing {len(items)} fully classified records from {reused_generated_at}")
        files_count = len(items)
    else:
        excluded_paths = {os.path.normcase(str((skill_dir / "SKILL.md").resolve()))}
        files = discover_files(skills_roots, manifest, excluded_paths)
        files_count = len(files)
        log(f"Discovered {len(files)} SKILL.md files; reading every file in full")
        for index, (path, entry) in enumerate(files, 1):
            try:
                text = path.read_text(encoding="utf-8-sig", errors="replace")
                items.append(classify_document(text, path, entry, rules, compiled_rules))
            except Exception as exc:  # keep a complete audit trail
                failures.append({"skill_md": str(path), "error": str(exc)})
            if index % 250 == 0 or index == len(files):
                log(f"Read and classified {index}/{len(files)} files; failures={len(failures)}")

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
    source_files = [
        {
            "skill_md": item["skill_md"],
            "file_length": item["file_length"],
            "last_write_ns": Path(item["skill_md"]).stat().st_mtime_ns,
            "content_hash": item["content_hash"],
        }
        for item in items
    ]
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
        "rules_fingerprint": hashlib.sha256(rules_path.read_bytes()).hexdigest(),
        "classifier_path": str(Path(__file__).resolve()),
        "classifier_fingerprint": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "raw_files": files_count,
        "classified_files": len(items),
        "unique_content_candidates": len(representatives),
        "failures": len(failures),
        "levels": LEVELS,
        "leaf_target": args.leaf_target,
        "full_body_read": True,
        "adaptive_catalog_shards": adaptive_shards,
        "classification_reused_from": reused_generated_at,
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
    robust_remove(backup_dir)
    moved_previous = False
    try:
        if final_dir.exists():
            final_dir.rename(backup_dir)
            moved_previous = True
        temp_dir.rename(final_dir)
    except Exception:
        if moved_previous and backup_dir.exists() and not final_dir.exists():
            backup_dir.rename(final_dir)
        raise
    else:
        robust_remove(backup_dir)
    log(f"Completed: raw={files_count}, classified={len(items)}, unique={len(representatives)}, failures={len(failures)}")
    print(json.dumps({"status": "ok", **metadata, "output_dir": str(final_dir)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
