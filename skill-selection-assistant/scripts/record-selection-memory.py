#!/usr/bin/env python3
"""Record route-scoped skill-selection feedback without storing raw queries by default."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


OUTCOMES = ("selected", "missed", "rejected", "setup-failed", "new-skill-needed", "overlap-note")


def short_text(value: str, limit: int = 300) -> str:
    flattened = " ".join(value.split())
    return flattened if len(flattened) <= limit else flattened[:limit].rstrip() + "..."


def main() -> int:
    parser = argparse.ArgumentParser(description="Record local skill-selection feedback.")
    parser.add_argument("--query", required=True)
    parser.add_argument("--outcome", choices=OUTCOMES, default="selected")
    parser.add_argument("--selected-skill", default="")
    parser.add_argument("--route-type", default="")
    parser.add_argument("--category", default="")
    parser.add_argument("--notes", default="")
    parser.add_argument("--index-dir", default="")
    parser.add_argument("--store-query", action="store_true", help="Store a shortened raw query; disabled by default for privacy.")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    index_dir = Path(args.index_dir).expanduser().resolve() if args.index_dir else script_dir.parent / ".skill-index"
    index_dir.mkdir(parents=True, exist_ok=True)
    memory_path = index_dir / "selection-memory.md"
    if not memory_path.exists():
        memory_path.write_text(
            "# Skill Selection Memory\n\n## Recurring Patterns\n\n## Missed Matches\n\n## Category Improvements\n\n## Selection Log\n",
            encoding="utf-8",
        )
    existing = memory_path.read_text(encoding="utf-8-sig", errors="replace")
    if "## Selection Log" not in existing:
        with memory_path.open("a", encoding="utf-8") as handle:
            handle.write("\n## Selection Log\n")
    lines = [
        "",
        f"### {datetime.now().isoformat(timespec='seconds')}",
        "",
        f"- outcome: `{args.outcome}`",
        f"- query: {short_text(args.query) if args.store_query else '[not stored]'}",
    ]
    if args.selected_skill:
        lines.append(f"- selected_skill: `{short_text(args.selected_skill)}`")
    if args.route_type or args.category:
        lines.append(f"- route: `{short_text(args.route_type)}` / `{short_text(args.category)}`")
    if args.notes:
        lines.append(f"- notes: {short_text(args.notes)}")
    with memory_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    print(json.dumps({
        "status": "recorded",
        "outcome": args.outcome,
        "selected_skill": args.selected_skill,
        "route_type": args.route_type,
        "category": args.category,
        "query_stored": args.store_query,
        "memory": str(memory_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
