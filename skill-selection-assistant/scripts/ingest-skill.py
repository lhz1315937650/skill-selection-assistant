#!/usr/bin/env python3
"""Insert one local skill into the existing index without scanning the library."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


def emit(payload: dict, compact: bool) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=None if compact else 2, separators=(",", ":") if compact else None))


def run_classifier(command: list[str], compact: bool) -> int:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        emit({
            "status": "error",
            "mode": "ingest_skill",
            "error": detail,
            "full_library_scan": False,
            "scanned_files": 0,
        }, compact)
        return 1
    emit(json.loads(result.stdout), compact)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify one SKILL.md and insert it into the existing SQLite tag index.")
    parser.add_argument("--skill-md", default="", help="Path to the SKILL.md file to ingest or delete.")
    parser.add_argument("--delete", action="store_true", help="Delete this skill from the SQLite index instead of inserting it.")
    parser.add_argument("--refresh-profiles", action="store_true", help="Rebuild can-do / cannot-do profiles from the classified index without rereading SKILL.md files.")
    parser.add_argument("--list-pending", action="store_true", help="List new SKILL.md paths by directory name without reading bodies.")
    parser.add_argument("--ingest-pending", action="store_true", help="Ingest each pending SKILL.md one at a time.")
    parser.add_argument("--skills-root", action="append", default=[], help="Skill root used with --list-pending or --ingest-pending.")
    parser.add_argument("--skill-dir", default="")
    parser.add_argument("--index-dir", default="")
    parser.add_argument("--lock-timeout", type=float, default=120.0)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    skill_dir = Path(args.skill_dir).expanduser().resolve() if args.skill_dir else script_dir.parent
    index_dir = Path(args.index_dir).expanduser().resolve() if args.index_dir else skill_dir / ".skill-index"

    if args.refresh_profiles:
        command = [
            sys.executable,
            str(script_dir / "deep-classify-skills.py"),
            "--refresh-profiles",
            "--lock-timeout",
            str(args.lock_timeout),
            "--skill-dir",
            str(skill_dir),
            "--index-dir",
            str(index_dir),
        ]
        return run_classifier(command, args.compact)
    if args.list_pending or args.ingest_pending:
        spec = importlib.util.spec_from_file_location("skill_lazy_index_pending", script_dir / "lazy-index.py")
        if spec is None or spec.loader is None:
            raise RuntimeError("Cannot load lazy-index.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        roots = list(args.skills_root)
        if not roots:
            metadata_path = index_dir / "deep" / "metadata.json"
            if metadata_path.exists():
                metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
                roots = [str(value) for value in metadata.get("skills_roots", []) if value]
        pending = module.list_pending_skills(index_dir / "deep" / "lazy-route.sqlite3", roots)
        if args.list_pending and not args.ingest_pending:
            emit(pending, args.compact)
            return 0
        ingested = []
        for item in pending.get("pending") or []:
            command = [
                sys.executable,
                str(script_dir / "deep-classify-skills.py"),
                "--ingest-skill",
                str(item["skill_md"]),
                "--lock-timeout",
                str(args.lock_timeout),
                "--skill-dir",
                str(skill_dir),
                "--index-dir",
                str(index_dir),
            ]
            result = subprocess.run(command, text=True, capture_output=True, check=False)
            if result.returncode != 0:
                ingested.append({"skill_md": item["skill_md"], "status": "error", "error": (result.stderr or result.stdout).strip()})
            else:
                ingested.append(json.loads(result.stdout))
        emit({
            "status": "ok",
            "mode": "ingest_pending",
            "full_library_scan": False,
            "pending_count": pending.get("pending_count", 0),
            "ingested": ingested,
        }, args.compact)
        return 0

    if not args.skill_md:
        parser.error("--skill-md is required unless --list-pending or --ingest-pending is used")

    command = [
        sys.executable,
        str(script_dir / "deep-classify-skills.py"),
        "--delete-skill" if args.delete else "--ingest-skill",
        str(Path(args.skill_md).expanduser()),
        "--lock-timeout",
        str(args.lock_timeout),
    ]
    if args.skill_dir:
        command.extend(["--skill-dir", args.skill_dir])
    if args.index_dir:
        command.extend(["--index-dir", args.index_dir])
    return run_classifier(command, args.compact)


if __name__ == "__main__":
    raise SystemExit(main())
