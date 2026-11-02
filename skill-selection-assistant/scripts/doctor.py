#!/usr/bin/env python3
"""Cross-platform diagnosis and repair for skill-selection-assistant."""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any


DEEP_SCHEMA_VERSION = "2.6.0"
REQUIRED_ROUTING_FILES = ("metadata.json", "source-manifest.json", "hierarchy.json", "facets.json", "route-cards.json", "label-keywords.json")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def inspect_index(index_dir: Path) -> tuple[bool, str, dict[str, Any]]:
    deep_dir = index_dir / "deep"
    database = deep_dir / "lazy-route.sqlite3"
    metadata: dict[str, Any] = {}
    metadata_corrupt = False
    metadata_path = deep_dir / "metadata.json"
    if metadata_path.exists():
        try:
            loaded = load_json(metadata_path)
            if isinstance(loaded, dict):
                metadata = loaded
        except (OSError, ValueError, json.JSONDecodeError):
            metadata = {}
            metadata_corrupt = True
    if database.exists():
        if metadata_corrupt:
            return False, "corrupt:metadata.json", metadata
        connection = None
        try:
            connection = sqlite3.connect(database)
            tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            values = dict(connection.execute("SELECT key, value FROM metadata"))
            if "cards" not in tables:
                return False, "missing:cards", metadata
            metadata.setdefault("schema_version", DEEP_SCHEMA_VERSION)
            metadata["unique_content_candidates"] = int(values.get("skill_count") or metadata.get("unique_content_candidates") or 0)
            return True, "", metadata
        except (OSError, sqlite3.Error, TypeError, ValueError):
            return False, "corrupt:lazy-route.sqlite3", metadata
        finally:
            if connection is not None:
                connection.close()
    for name in REQUIRED_ROUTING_FILES:
        path = deep_dir / name
        if not path.exists():
            return False, f"missing:{name}", metadata
        try:
            payload = load_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            return False, f"corrupt:{name}", metadata
        if not isinstance(payload, dict):
            return False, f"corrupt:{name}", metadata
    if metadata.get("schema_version") != DEEP_SCHEMA_VERSION:
        return False, "schema-mismatch:metadata.json", metadata
    return True, "", metadata


def emit(payload: dict[str, Any], compact: bool) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=None if compact else 2, separators=(",", ":") if compact else None))


def main() -> int:
    parser = argparse.ArgumentParser(description="Check or repair the installed router and its local deep index.")
    parser.add_argument("--index-dir", default="")
    parser.add_argument("--skills-root", action="append", default=[], help="Repeat to repair an index that uses multiple roots.")
    parser.add_argument("--fix", action="store_true", help="Rebuild a missing, incomplete, corrupt, stale, or old-schema index.")
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    skill_dir = script_dir.parent
    index_dir = Path(args.index_dir).expanduser().resolve() if args.index_dir else skill_dir / ".skill-index"
    version_path = skill_dir / "VERSION"
    valid_before, problem_before, metadata = inspect_index(index_dir)
    result: dict[str, Any] = {
        "status": "needs-attention",
        "version": version_path.read_text(encoding="utf-8-sig").strip() if version_path.exists() else "development",
        "skill_dir": str(skill_dir),
        "index_dir": str(index_dir),
        "index_valid_before": valid_before,
        "problem_before": problem_before,
        "fix_requested": args.fix,
        "fixed": False,
    }
    if not valid_before and not args.fix:
        result["reason"] = "The deep index is not usable. Re-run this doctor with --fix."
        result["next_step"] = f'python "{Path(__file__).resolve()}" --fix'
        emit(result, args.compact)
        return 1

    recommender = script_dir / "recommend-skills.py"
    command = [
        sys.executable,
        str(recommender),
        "--query",
        "health check local skill routing",
        "--index-dir",
        str(index_dir),
        "--compact",
    ]
    for root in args.skills_root:
        command.extend(["--skills-root", root])
    checked = subprocess.run(command, text=True, capture_output=True, check=False)
    result["recommendation_exit_code"] = checked.returncode
    if checked.returncode != 0:
        result["reason"] = (checked.stderr or checked.stdout).strip()[-1000:]
        emit(result, args.compact)
        return 1

    recommendation = json.loads(checked.stdout)
    valid_after, problem_after, metadata = inspect_index(index_dir)
    result.update({
        "index_valid_after": valid_after,
        "problem_after": problem_after,
        "fixed": bool((not valid_before and valid_after) or recommendation.get("index", {}).get("refreshed")),
        "raw_files": int(metadata.get("raw_files") or 0),
        "classified_files": int(metadata.get("classified_files") or 0),
        "failed_files": int(metadata.get("failed_files") or 0),
        "skills_roots": metadata.get("skills_roots", []),
        "recommendation_mode": recommendation.get("mode", ""),
        "storage_model": recommendation.get("storage_model", "unknown"),
    })
    if valid_after:
        result["status"] = "degraded" if result["failed_files"] else "ok"
    else:
        result["reason"] = "The recommendation ran, but required index artifacts are still unusable."
    emit(result, args.compact)
    return 0 if result["status"] in {"ok", "degraded"} else 1


def cli() -> int:
    try:
        return main()
    except Exception as exc:
        if "--debug" in sys.argv:
            raise
        payload = {
            "status": "error",
            "error": {"type": type(exc).__name__, "message": str(exc)},
            "next_step": "Re-run with --debug only for maintenance, or pass explicit --skills-root values with --fix.",
        }
        emit(payload, "--compact" in sys.argv)
        return 1


if __name__ == "__main__":
    raise SystemExit(cli())
