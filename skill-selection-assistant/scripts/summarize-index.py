#!/usr/bin/env python3
"""Generate human-readable summaries for a local skill-selection index."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def first_text(value: Any) -> str:
    values = as_list(value)
    return values[0] if values else ""


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize a generated .skill-index directory.")
    parser.add_argument("--index-dir", default="", help="Path to .skill-index. Defaults to ../.skill-index beside this script's skill folder.")
    parser.add_argument("--top", type=int, default=12, help="Representative candidates to show per detailed domain.")
    args = parser.parse_args()

    if args.index_dir:
        index_dir = Path(args.index_dir).expanduser()
    else:
        index_dir = Path(__file__).resolve().parents[1] / ".skill-index"

    skills_index_path = index_dir / "skills-index.json"
    route_summary_path = index_dir / "route-summary.json"
    if not skills_index_path.exists():
        raise FileNotFoundError(f"Missing skills index: {skills_index_path}")
    if not route_summary_path.exists():
        raise FileNotFoundError(f"Missing route summary: {route_summary_path}")

    skills_index = load_json(skills_index_path)
    route_summary = load_json(route_summary_path)
    skills = skills_index.get("skills", [])

    primary_domain = Counter()
    domain_detail = Counter()
    task_type = Counter()
    output_type = Counter()
    setup_level = Counter()
    origin = Counter()
    status = Counter()
    domain_task = Counter()
    domain_setup = Counter()
    domain_output = Counter()
    by_detail: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for skill in skills:
        for value in as_list(skill.get("primary_domain")):
            primary_domain[value] += 1
        details = as_list(skill.get("domain_detail")) or ["unknown"]
        tasks = as_list(skill.get("task_type")) or ["unknown"]
        outputs = as_list(skill.get("output_type")) or ["unknown"]
        setups = as_list(skill.get("setup_level")) or ["unknown"]
        for detail in details:
            domain_detail[detail] += 1
            by_detail[detail].append(skill)
            for task in tasks:
                domain_task[(detail, task)] += 1
            for setup in setups:
                domain_setup[(detail, setup)] += 1
            for output in outputs:
                domain_output[(detail, output)] += 1
        for value in tasks:
            task_type[value] += 1
        for value in outputs:
            output_type[value] += 1
        for value in setups:
            setup_level[value] += 1
        for value in as_list(skill.get("origin")):
            origin[value] += 1
        for value in as_list(skill.get("status")):
            status[value] += 1

    details_by_size = [name for name, _ in domain_detail.most_common()]
    tasks_by_size = [name for name, _ in task_type.most_common()]

    matrix_path = index_dir / "domain-task-matrix.csv"
    with matrix_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["domain_detail", "total", *tasks_by_size])
        for detail in details_by_size:
            writer.writerow([detail, domain_detail[detail], *[domain_task[(detail, task)] for task in tasks_by_size]])

    compact = {
        "generated_from": str(index_dir),
        "output_schema_version": route_summary.get("output_schema_version"),
        "rules_schema_version": route_summary.get("rules_schema_version"),
        "raw_total": route_summary.get("raw_total"),
        "total": route_summary.get("total"),
        "duplicates_removed": route_summary.get("duplicates_removed"),
        "full_routes_generated": route_summary.get("full_routes_generated"),
        "primary_domain": primary_domain.most_common(),
        "domain_detail": domain_detail.most_common(),
        "task_type": task_type.most_common(),
        "output_type": output_type.most_common(),
        "setup_level": setup_level.most_common(),
        "origin": origin.most_common(),
        "status": status.most_common(),
    }
    compact_path = index_dir / "detailed-classification.json"
    compact_path.write_text(json.dumps(compact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines: list[str] = []
    lines.extend(
        [
            "# Skill Classification Map",
            "",
            "This file summarizes the local `.skill-index` so users can understand their installed skill library without reading every `SKILL.md` or opening the full JSON index.",
            "",
            "## Overview",
            "",
            f"- Output schema: `{route_summary.get('output_schema_version')}`",
            f"- Rules schema: `{route_summary.get('rules_schema_version')}`",
            f"- Raw skills: `{route_summary.get('raw_total')}`",
            f"- Deduplicated candidates: `{route_summary.get('total')}`",
            f"- Duplicates removed: `{route_summary.get('duplicates_removed')}`",
            f"- Full routes generated: `{route_summary.get('full_routes_generated')}`",
            f"- Shortlist files: `{sum(1 for _ in (index_dir / 'shortlists').rglob('*.json'))}`",
            f"- Full route files: `{sum(1 for _ in (index_dir / 'routes').rglob('*.json'))}`",
            "",
        ]
    )

    sections = [
        ("Primary Domains", primary_domain),
        ("Detailed Domains", domain_detail),
        ("Task Types", task_type),
        ("Output Types", output_type),
        ("Setup Levels", setup_level),
        ("Origins", origin),
        ("Statuses", status),
    ]
    for title, counter in sections:
        lines.extend([f"## {title}", ""])
        for name, count in counter.most_common(40):
            lines.append(f"- `{name}`: {count}")
        lines.append("")

    lines.extend(["## Detailed Domain Breakdown", ""])
    for detail, count in domain_detail.most_common():
        lines.append(f"### {detail} ({count})")
        # The compact loops below avoid defaultdict entries for zero-count combinations.
        task_counts = Counter({name: domain_task[(detail, name)] for name in tasks_by_size if domain_task[(detail, name)]})
        setup_counts = Counter({name: domain_setup[(detail, name)] for name, _ in setup_level.most_common() if domain_setup[(detail, name)]})
        output_counts = Counter({name: domain_output[(detail, name)] for name, _ in output_type.most_common() if domain_output[(detail, name)]})
        lines.append("- Common tasks: " + (", ".join(f"{name}:{value}" for name, value in task_counts.most_common(8)) or "none"))
        lines.append("- Common setup levels: " + (", ".join(f"{name}:{value}" for name, value in setup_counts.most_common(6)) or "none"))
        lines.append("- Common outputs: " + (", ".join(f"{name}:{value}" for name, value in output_counts.most_common(6)) or "none"))
        lines.append("- Representative candidates:")
        representatives = sorted(
            by_detail[detail],
            key=lambda skill: (-(int(skill.get("duplicate_count") or 1)), str(skill.get("name", "")).lower()),
        )[: args.top]
        for skill in representatives:
            description = first_text(skill.get("short_description")) or first_text(skill.get("description"))
            if len(description) > 100:
                description = description[:97] + "..."
            lines.append(
                f"  - `{skill.get('name')}` | {skill.get('origin')} | {skill.get('setup_level')} | {description}"
            )
        lines.append("")

    lines.extend(
        [
            "## Routing Tips",
            "",
            "- Prefer `scripts/recommend-skills.ps1 -Query \"...\"` for normal use.",
            "- If recommendations are too sparse, lower `-MinRelevanceScore` or increase `-ScoreWindow`.",
            "- If recommendations are noisy, raise `-MinRelevanceScore` or lower `-ScoreWindow`.",
            "- Read shortlists first; use full routes only for audits or deep debugging.",
            "",
        ]
    )

    markdown_path = index_dir / "DETAILED_CLASSIFICATION.md"
    markdown_path.write_text("\n".join(lines), encoding="utf-8")

    print(
        json.dumps(
            {
                "status": "summarized",
                "index_dir": str(index_dir),
                "markdown": str(markdown_path),
                "json": str(compact_path),
                "matrix_csv": str(matrix_path),
                "domain_detail_count": len(domain_detail),
                "task_type_count": len(task_type),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
