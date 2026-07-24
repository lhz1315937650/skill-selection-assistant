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
DEEP_SCHEMA_VERSION = "2.5.0"
REQUIRED_ROUTING_FILES = ("source-manifest.json", "hierarchy.json", "facets.json", "route-cards.json", "label-keywords.json")


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


def inspect_index(index_dir: Path) -> tuple[bool, str, list[str]]:
    deep_dir = index_dir / "deep"
    metadata_path = deep_dir / "metadata.json"
    source_path = deep_dir / "source-manifest.json"
    recovered_roots: list[str] = []
    source: dict[str, Any] = {}
    if source_path.exists():
        try:
            loaded_source = load_json(source_path)
            if isinstance(loaded_source, dict):
                source = loaded_source
                recovered_roots = [str(value) for value in source.get("skills_roots", []) if value]
        except (OSError, ValueError, json.JSONDecodeError):
            source = {}
    if not metadata_path.exists():
        return False, "index_missing", recovered_roots
    try:
        metadata = load_json(metadata_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False, "index_corrupt", recovered_roots
    if not isinstance(metadata, dict):
        return False, "index_corrupt", recovered_roots
    metadata_values = [str(value) for value in metadata.get("skills_roots", []) if value]
    if metadata_values:
        recovered_roots = metadata_values
    if metadata.get("schema_version") != DEEP_SCHEMA_VERSION:
        return False, "index_schema_changed", recovered_roots
    for name in REQUIRED_ROUTING_FILES:
        path = deep_dir / name
        if not path.exists():
            return False, "index_incomplete", recovered_roots
        try:
            payload = load_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            return False, "index_corrupt", recovered_roots
        if not isinstance(payload, dict):
            return False, "index_corrupt", recovered_roots
    return True, "", recovered_roots


def main() -> int:
    parser = argparse.ArgumentParser(description="Recommend installed local skills through a deep, token-efficient hierarchy.")
    parser.add_argument("--query", required=True)
    parser.add_argument("--path", default="")
    parser.add_argument("--index-dir", default="")
    parser.add_argument("--skills-root", action="append", default=[], help="Repeat to index multiple local skill roots.")
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--leaf-target", type=int, default=0)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--full-rebuild", action="store_true")
    parser.add_argument("--compat", action="store_true", help="Include the deprecated nested deep_route object.")
    parser.add_argument("--compact", action="store_true", help="Emit compact JSON for lower token and logging overhead.")
    parser.add_argument(
        "--show-branches",
        action="store_true",
        help="Stop at category branches for taxonomy debugging instead of routing them automatically.",
    )
    parser.add_argument("--debug", action="store_true", help="Show Python tracebacks for unexpected failures.")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    skill_dir = script_dir.parent
    index_dir = Path(args.index_dir).expanduser().resolve() if args.index_dir else skill_dir / ".skill-index"
    builder = script_dir / "deep-classify-skills.py"
    router = script_dir / "deep-route.py"
    metadata_path = index_dir / "deep" / "metadata.json"
    if not builder.exists() or not router.exists():
        raise FileNotFoundError("The deep classifier or router is missing from the installed skill.")

    index_valid, index_problem, existing_roots = inspect_index(index_dir)
    roots = list(dict.fromkeys(args.skills_root or existing_roots))
    if not roots and skill_dir.parent.name.lower() == "skills":
        roots = [str(skill_dir.parent.resolve())]
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
    if not index_valid or args.full_rebuild or roots_changed:
        if not index_valid:
            refresh_reason = index_problem
        elif args.full_rebuild:
            refresh_reason = "full_rebuild_requested"
        else:
            refresh_reason = "skills_roots_changed"
        run_json(build_command, "deep index build")
        refreshed = True

    index_valid, remaining_problem, _ = inspect_index(index_dir)
    if not index_valid:
        raise RuntimeError(f"Deep index remains unusable after refresh: {remaining_problem}")

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

    # Category branches are an AI-internal routing surface. In normal use, walk
    # the best-scoring branch automatically until the final skill shortlist is
    # reached. --show-branches preserves the branch view for taxonomy audits.
    route_trace: list[dict[str, Any]] = []
    visited_paths = {args.path}
    while not args.show_branches and deep_result.get("mode") == "choose_category":
        branches = list(deep_result.get("branches") or [])
        if not branches:
            break
        selected_branch = max(
            branches,
            key=lambda item: (int(item.get("query_score") or 0), -int(item.get("count") or 0)),
        )
        selected_path = str(selected_branch.get("path") or "")
        if not selected_path or selected_path in visited_paths:
            break
        route_trace.append({
            "level": deep_result.get("next_level", ""),
            "selected": selected_branch.get("name", ""),
            "path": selected_path,
            "score": int(selected_branch.get("query_score") or 0),
        })
        visited_paths.add(selected_path)
        next_command = list(route_command)
        if "--path" in next_command:
            path_index = next_command.index("--path")
            next_command[path_index + 1] = selected_path
        else:
            next_command.extend(["--path", selected_path])
        deep_result = run_json(next_command, "automatic deep route selection")

    metadata = load_json(metadata_path)
    mode = str(deep_result.get("mode") or "")
    next_step = {
        "choose_category": "Internal routing is ambiguous. Keep branch details AI-facing; do not show them to the user.",
            "choose_skill": (
                "Present only candidate name, description, and weight; ask which skill "
                "to activate. Read only the chosen SKILL.md, then read linked files only "
                "when the active task needs them."
            ),
        "no_skills_installed": "No local skills are installed yet. Offer to answer directly, install a skill, or create a new skill.",
    }.get(mode, str(deep_result.get("instruction") or ""))
    output = {
        "schema_version": SCHEMA_VERSION,
        "query": args.query,
        "engine": "deep_hospital",
        "mode": mode,
        "index": {
            "refreshed": refreshed,
            "refresh_reason": refresh_reason,
            "status": "degraded" if int(metadata.get("failed_files") or 0) else "ok",
            "failed_files": int(metadata.get("failed_files") or 0),
            "skills_root": (metadata.get("skills_roots") or roots or [""])[0],
            "skills_roots": metadata.get("skills_roots", roots),
            "scope": metadata.get("index_scope", "installing-user-local-skills-exhaustive"),
        },
        "route": deep_result.get("current", {}),
        "route_trace": route_trace,
        "branches": deep_result.get("branches", []),
        "candidates": deep_result.get("candidates", []),
        "next_step": next_step,
    }
    if args.compat:
        output["deep_route"] = deep_result
    print(json.dumps(
        output,
        ensure_ascii=False,
        indent=None if args.compact else 2,
        separators=(",", ":") if args.compact else None,
    ))
    return 0


def cli() -> int:
    try:
        return main()
    except Exception as exc:
        if "--debug" in sys.argv:
            raise
        compact = "--compact" in sys.argv
        query = ""
        if "--query" in sys.argv:
            index = sys.argv.index("--query")
            if index + 1 < len(sys.argv):
                query = sys.argv[index + 1]
        output = {
            "schema_version": SCHEMA_VERSION,
            "query": query,
            "engine": "deep_hospital",
            "mode": "error",
            "index": {},
            "route": {},
            "branches": [],
            "candidates": [],
            "error": {"type": type(exc).__name__, "message": str(exc)},
            "next_step": "Check the configured roots, index directory, and route path. Re-run with --debug only for maintenance.",
        }
        print(json.dumps(output, ensure_ascii=False, indent=None if compact else 2, separators=(",", ":") if compact else None))
        return 1


if __name__ == "__main__":
    raise SystemExit(cli())
