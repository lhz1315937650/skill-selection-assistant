#!/usr/bin/env python3
"""Cross-platform entry point for hierarchical local skill recommendation."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "3.0.0"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def run_json(command: list[str], operation: str) -> dict[str, Any]:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"{operation} failed ({result.returncode}): {detail}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{operation} returned invalid JSON: {result.stdout[:500]}") from exc


def metadata_roots(metadata_path: Path) -> list[str]:
    if not metadata_path.exists():
        return []
    try:
        metadata = load_json(metadata_path)
    except (OSError, ValueError):
        return []
    return [str(value) for value in metadata.get("skills_roots", []) if value]


def main() -> int:
    parser = argparse.ArgumentParser(description="Recommend installed local skills through a deep, token-efficient hierarchy.")
    parser.add_argument("--query", required=True)
    parser.add_argument("--path", default="")
    parser.add_argument("--index-dir", default="")
    parser.add_argument("--skills-root", action="append", default=[], help="Repeat to index multiple local skill roots.")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--leaf-target", type=int, default=0)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--full-rebuild", action="store_true")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    skill_dir = script_dir.parent
    index_dir = Path(args.index_dir).expanduser().resolve() if args.index_dir else skill_dir / ".skill-index"
    builder = script_dir / "deep-classify-skills.py"
    router = script_dir / "deep-route.py"
    metadata_path = index_dir / "deep" / "metadata.json"
    if not builder.exists() or not router.exists():
        raise FileNotFoundError("The deep classifier or router is missing from the installed skill.")

    existing_roots = metadata_roots(metadata_path)
    roots = list(dict.fromkeys(args.skills_root or existing_roots))
    normalized_existing = {os.path.normcase(str(Path(value).expanduser().resolve())) for value in existing_roots}
    normalized_requested = {os.path.normcase(str(Path(value).expanduser().resolve())) for value in args.skills_root}
    roots_changed = bool(args.skills_root) and normalized_requested != normalized_existing
    build_command = [sys.executable, str(builder), "--index-dir", str(index_dir)]
    for root in roots:
        build_command.extend(["--skills-root", root])
    if args.full_rebuild:
        build_command.append("--full-rebuild")

    refreshed = False
    refresh_reason = ""
    if not metadata_path.exists() or args.full_rebuild or roots_changed:
        if not metadata_path.exists():
            refresh_reason = "index_missing"
        elif args.full_rebuild:
            refresh_reason = "full_rebuild_requested"
        else:
            refresh_reason = "skills_roots_changed"
        run_json(build_command, "deep index build")
        refreshed = True

    route_command = [
        sys.executable,
        str(router),
        "--query",
        args.query,
        "--index-dir",
        str(index_dir),
        "--limit",
        str(args.limit),
    ]
    if args.path:
        route_command.extend(["--path", args.path])
    if args.leaf_target:
        route_command.extend(["--leaf-target", str(args.leaf_target)])
    if args.verbose:
        route_command.append("--verbose")

    deep_result = run_json(route_command, "deep route selection")
    if deep_result.get("mode") == "index_stale":
        refresh_reason = str(deep_result.get("freshness", {}).get("reason") or "index_stale")
        run_json(build_command, "deep index refresh")
        refreshed = True
        deep_result = run_json(route_command, "deep route selection after refresh")

    metadata = load_json(metadata_path)
    mode = str(deep_result.get("mode") or "")
    next_step = {
        "choose_category": "Present only the returned branches, ask the user to choose one, then call this script again with its exact --path.",
        "choose_skill": "Present the compact candidates and ask which skill to activate. Read only the chosen SKILL.md.",
    }.get(mode, str(deep_result.get("instruction") or ""))
    output = {
        "schema_version": SCHEMA_VERSION,
        "query": args.query,
        "engine": "deep_hospital",
        "mode": mode,
        "index": {
            "refreshed": refreshed,
            "refresh_reason": refresh_reason,
            "skills_root": (metadata.get("skills_roots") or roots or [""])[0],
            "skills_roots": metadata.get("skills_roots", roots),
            "scope": metadata.get("index_scope", "installing-user-local-skills-exhaustive"),
        },
        "route": deep_result.get("current", {}),
        "branches": deep_result.get("branches", []),
        "candidates": deep_result.get("candidates", []),
        "deep_route": deep_result,
        "next_step": next_step,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
