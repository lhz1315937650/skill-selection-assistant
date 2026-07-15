#!/usr/bin/env python3
"""Local self-growth audit for the installed skill-selection assistant."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def count_memory(memory_path: Path) -> dict[str, Any]:
    if not memory_path.exists():
        return {"exists": False, "outcomes": {}, "routes": {}, "selected_skills": {}, "recent_notes": []}

    text = memory_path.read_text(encoding="utf-8-sig", errors="ignore")
    outcomes = Counter(re.findall(r"(?m)^- outcome:\s+`?([^`\n]+)`?", text))
    routes = Counter(re.findall(r"(?m)^- route:\s+`?([^`\n]+?)`?\s*/\s*`?([^`\n]+?)`?", text))
    selected = Counter(re.findall(r"(?m)^- selected_skill:\s+`?([^`\n]+)`?", text))
    notes = re.findall(r"(?m)^- notes:\s+(.+)$", text)
    return {
        "exists": True,
        "outcomes": dict(outcomes),
        "routes": {f"{a}/{b}": n for (a, b), n in routes.items()},
        "selected_skills": dict(selected.most_common(20)),
        "recent_notes": notes[-20:],
    }


def summarize_skills(skills: list[dict[str, Any]]) -> dict[str, Any]:
    by_primary = Counter()
    by_detail = Counter()
    by_specialty = Counter()
    by_task = Counter()
    by_setup = Counter()
    by_origin = Counter()
    by_status = Counter()
    by_output = Counter()
    by_detail_setup = Counter()
    duplicates = []
    variants = []

    for skill in skills:
        for value in as_list(skill.get("primary_domain")):
            by_primary[value] += 1
        details = as_list(skill.get("domain_detail")) or ["unknown"]
        for value in details:
            by_detail[value] += 1
            by_detail_setup[(value, str(skill.get("setup_level", "unknown")))] += 1
        specialties = as_list(skill.get("specialty")) or ["unknown"]
        for value in specialties:
            by_specialty[value] += 1
        for value in as_list(skill.get("task_type")):
            by_task[value] += 1
        for value in as_list(skill.get("setup_level")):
            by_setup[value] += 1
        for value in as_list(skill.get("origin")):
            by_origin[value] += 1
        for value in as_list(skill.get("status")):
            by_status[value] += 1
        for value in as_list(skill.get("output_type")):
            by_output[value] += 1
        if int(skill.get("duplicate_name_count") or 0) >= 3:
            duplicates.append(skill)
        if int(skill.get("variant_count") or 0) >= 2:
            variants.append(skill)

    return {
        "primary_domain": by_primary,
        "domain_detail": by_detail,
        "specialty": by_specialty,
        "task_type": by_task,
        "setup_level": by_setup,
        "origin": by_origin,
        "status": by_status,
        "output_type": by_output,
        "domain_setup": by_detail_setup,
        "high_duplicate_candidates": duplicates,
        "variant_candidates": variants,
    }


def build_suggestions(summary: dict[str, Any], memory: dict[str, Any], total: int) -> list[str]:
    suggestions: list[str] = []
    details: Counter = summary["domain_detail"]
    specialties: Counter = summary.get("specialty", Counter())
    setup: Counter = summary["setup_level"]
    outcomes = memory.get("outcomes", {})

    for name, count in details.most_common():
        if total and count / total >= 0.20:
            suggestions.append(f"`{name}` 占比约 {count / total:.0%}，候选池偏大，建议继续拆分更细 shortlist。")
        elif count >= 1000:
            suggestions.append(f"`{name}` 有 {count} 个候选，建议重点观察是否出现偏题推荐。")

    for name, count in specialties.most_common(5):
        if name != "general" and count >= 800:
            suggestions.append(f"三级科室 `{name}` 仍有 {count} 个候选，建议继续拆成更具体的检查室。")

    for name, count in summary.get("adaptive_leaf", [])[:5]:
        if count >= 800:
            suggestions.append(f"自适应叶子路线 `{name}` 仍有 {count} 个候选，建议继续加入更细的分诊轴。")

    if setup.get("account", 0) + setup.get("api-key", 0) > 0:
        suggestions.append("存在需要账号或 API key 的 skill，推荐时继续保留安装/配置确认，避免误触发。")

    if int(outcomes.get("missed", 0)) or int(outcomes.get("new-skill-needed", 0)):
        suggestions.append("selection-memory 中存在 missed/new-skill-needed 记录，建议把高频缺口沉淀成新 skill 或新分类规则。")

    if int(outcomes.get("rejected", 0)) or int(outcomes.get("setup-failed", 0)):
        suggestions.append("存在 rejected/setup-failed 记录，建议降低这些 skill 在相同 route 下的权重或拆分职责。")

    if len(summary["high_duplicate_candidates"]) > 20:
        suggestions.append("同名或近似重复 skill 较多，建议定期合并、弃用或标记代表版本。")

    if not suggestions:
        suggestions.append("当前索引结构健康，建议继续记录选择反馈并按周运行 self-grow。")

    return suggestions


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate local self-growth report for skill-selection-assistant.")
    parser.add_argument("--index-dir", default="", help="Path to .skill-index. Defaults to ../.skill-index.")
    parser.add_argument("--top", type=int, default=15, help="Top rows per report section.")
    args = parser.parse_args()

    if args.index_dir:
        index_dir = Path(args.index_dir).expanduser()
    else:
        index_dir = Path(__file__).resolve().parents[1] / ".skill-index"

    skills_index_path = index_dir / "skills-index.json"
    route_summary_path = index_dir / "route-summary.json"
    deep_index_path = index_dir / "deep" / "skills-deep-index.ndjson"
    deep_metadata_path = index_dir / "deep" / "metadata.json"
    memory_path = index_dir / "selection-memory.md"
    if not skills_index_path.exists():
        raise FileNotFoundError(f"Missing skills-index.json: {skills_index_path}")
    if not route_summary_path.exists():
        raise FileNotFoundError(f"Missing route-summary.json: {route_summary_path}")

    route_summary = load_json(route_summary_path)
    index_source = "legacy"
    if deep_index_path.exists() and deep_metadata_path.exists():
        with deep_index_path.open("r", encoding="utf-8-sig") as handle:
            skills = [json.loads(line) for line in handle if line.strip()]
        deep_metadata = load_json(deep_metadata_path)
        total = int(deep_metadata.get("classified_files") or len(skills))
        index_source = "deep"
    else:
        skills_index = load_json(skills_index_path)
        skills = skills_index.get("skills", [])
        total = int(route_summary.get("total") or len(skills))

    summary = summarize_skills(skills)
    summary["adaptive_leaf"] = [
        (str(row.get("name", "")), int(row.get("count") or 0))
        for row in route_summary.get("adaptive_leaf", [])
    ][: args.top]
    memory = count_memory(memory_path)
    suggestions = build_suggestions(summary, memory, total)

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "index_dir": str(index_dir),
        "index_source": index_source,
        "output_schema_version": route_summary.get("output_schema_version"),
        "rules_schema_version": route_summary.get("rules_schema_version"),
        "raw_total": route_summary.get("raw_total"),
        "total": total,
        "duplicates_removed": route_summary.get("duplicates_removed"),
        "full_routes_generated": route_summary.get("full_routes_generated"),
        "top_primary_domain": summary["primary_domain"].most_common(args.top),
        "top_domain_detail": summary["domain_detail"].most_common(args.top),
        "top_specialty": summary["specialty"].most_common(args.top),
        "top_adaptive_leaf": summary["adaptive_leaf"],
        "top_task_type": summary["task_type"].most_common(args.top),
        "top_setup_level": summary["setup_level"].most_common(args.top),
        "top_origin": summary["origin"].most_common(args.top),
        "top_output_type": summary["output_type"].most_common(args.top),
        "memory": memory,
        "suggestions": suggestions,
        "high_duplicate_candidates": [
            {
                "name": item.get("name"),
                "duplicate_name_count": item.get("duplicate_name_count"),
                "variant_count": item.get("variant_count"),
                "relative_path": item.get("relative_path"),
            }
            for item in summary["high_duplicate_candidates"][:50]
        ],
    }

    json_path = index_dir / "self-growth-report.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines: list[str] = []
    lines.extend(
        [
            "# 本机 Skill 自增长报告",
            "",
            f"- 生成时间: `{report['generated_at']}`",
            f"- 索引目录: `{index_dir}`",
            f"- 分析来源: `{report['index_source']}`",
            f"- 输出版本: `{report['output_schema_version']}`",
            f"- 规则版本: `{report['rules_schema_version']}`",
            f"- 原始 skill: `{report['raw_total']}`",
            f"- 去重后候选: `{report['total']}`",
            f"- 移除重复项: `{report['duplicates_removed']}`",
            f"- 完整 routes: `{report['full_routes_generated']}`",
            "",
            "## 下一步建议",
            "",
        ]
    )
    for item in suggestions:
        lines.append(f"- {item}")
    lines.append("")

    sections = [
        ("一级领域", report["top_primary_domain"]),
        ("二级领域", report["top_domain_detail"]),
        ("三级具体科室", report["top_specialty"]),
        ("自适应叶子路线", report["top_adaptive_leaf"]),
        ("任务类型", report["top_task_type"]),
        ("环境需求", report["top_setup_level"]),
        ("来源", report["top_origin"]),
        ("输出类型", report["top_output_type"]),
    ]
    for title, rows in sections:
        lines.extend([f"## {title}", ""])
        for name, count in rows:
            lines.append(f"- `{name}`: {count}")
        lines.append("")

    lines.extend(["## 选择记忆", ""])
    lines.append(f"- 记忆文件存在: `{memory.get('exists')}`")
    for name, count in memory.get("outcomes", {}).items():
        lines.append(f"- `{name}`: {count}")
    if memory.get("selected_skills"):
        lines.append("")
        lines.append("### 高频选择")
        lines.append("")
        for name, count in memory["selected_skills"].items():
            lines.append(f"- `{name}`: {count}")
    lines.append("")

    lines.extend(["## 重复/重叠候选", ""])
    for item in report["high_duplicate_candidates"][: args.top]:
        lines.append(
            f"- `{item['name']}` | duplicate_name_count={item['duplicate_name_count']} | "
            f"variant_count={item['variant_count']} | `{item['relative_path']}`"
        )
    lines.append("")

    lines.extend(
        [
            "## 推荐执行节奏",
            "",
            "- 每次新增或删除本地 skill 后，先运行 `scan-local-skills.ps1 -IncludeFullRoutes`。",
            "- 每周运行一次 `self-grow.py`，查看是否有大分类需要拆分、重复 skill 需要合并、缺失 skill 需要创建。",
            "- 推荐明显不准时，先用 `record-selection-memory.ps1` 记录 `missed`、`rejected` 或 `new-skill-needed`，再运行本报告。",
            "",
        ]
    )
    markdown_path = index_dir / "self-growth-report.md"
    markdown_path.write_text("\n".join(lines), encoding="utf-8")

    print(
        json.dumps(
            {
                "status": "generated",
                "index_dir": str(index_dir),
                "index_source": index_source,
                "markdown": str(markdown_path),
                "json": str(json_path),
                "suggestion_count": len(suggestions),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
