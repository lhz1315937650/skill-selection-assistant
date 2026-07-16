#!/usr/bin/env python3
"""Record route-scoped skill-selection feedback without storing raw queries by default."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Iterator


OUTCOMES = ("selected", "missed", "rejected", "setup-failed", "new-skill-needed", "overlap-note")


def short_text(value: str, limit: int = 300) -> str:
    flattened = " ".join(value.split())
    return flattened if len(flattened) <= limit else flattened[:limit].rstrip() + "..."


def markdown_value(value: str) -> str:
    return short_text(value).replace("`", "ˋ")


@contextlib.contextmanager
def memory_lock(lock_path: Path, timeout_seconds: float) -> Iterator[None]:
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                if time.time() - lock_path.stat().st_mtime > 60:
                    lock_path.unlink()
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for selection-memory lock: {lock_path}")
            time.sleep(0.05)
            continue
        else:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(f"pid={os.getpid()}\ncreated={datetime.now().isoformat()}\n")
            break
    try:
        yield
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


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
    parser.add_argument("--lock-timeout", type=float, default=10.0)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    index_dir = Path(args.index_dir).expanduser().resolve() if args.index_dir else script_dir.parent / ".skill-index"
    index_dir.mkdir(parents=True, exist_ok=True)
    memory_path = index_dir / "selection-memory.md"
    lines = [
        "",
        f"### {datetime.now().isoformat(timespec='seconds')}",
        "",
        f"- outcome: `{args.outcome}`",
        f"- query: {markdown_value(args.query) if args.store_query else '[not stored]'}",
    ]
    if args.selected_skill:
        lines.append(f"- selected_skill: `{markdown_value(args.selected_skill)}`")
    if args.route_type or args.category:
        lines.append(f"- route: `{markdown_value(args.route_type)}` / `{markdown_value(args.category)}`")
    if args.notes:
        lines.append(f"- notes: {markdown_value(args.notes)}")
    with memory_lock(index_dir / ".selection-memory.lock", args.lock_timeout):
        if not memory_path.exists():
            memory_path.write_text(
                "# Skill Selection Memory\n\n## Recurring Patterns\n\n## Missed Matches\n\n## Category Improvements\n\n## Selection Log\n",
                encoding="utf-8",
            )
        existing = memory_path.read_text(encoding="utf-8-sig", errors="replace")
        if "## Selection Log" not in existing:
            with memory_path.open("a", encoding="utf-8") as handle:
                handle.write("\n## Selection Log\n")
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


def cli() -> int:
    try:
        return main()
    except Exception as exc:
        if "--debug" in sys.argv:
            raise
        print(json.dumps({
            "status": "error",
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(cli())
