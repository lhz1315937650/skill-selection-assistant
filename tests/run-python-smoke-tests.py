#!/usr/bin/env python3
"""Cross-platform regression tests for the deep skill router."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO / "skill-selection-assistant"
FIXTURES = REPO / "tests" / "fixtures" / "skills"
CLASSIFIER = SKILL_DIR / "scripts" / "deep-classify-skills.py"
ROUTER = SKILL_DIR / "scripts" / "deep-route.py"
RECOMMENDER = SKILL_DIR / "scripts" / "recommend-skills.py"


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_json(command: list[str]) -> dict[str, Any]:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(f"Command failed: {command}\nstdout={result.stdout}\nstderr={result.stderr}")
    return json.loads(result.stdout)


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(root: Path, index: Path) -> dict[str, Any]:
    return run_json([
        sys.executable,
        str(CLASSIFIER),
        "--skills-root",
        str(root),
        "--skill-dir",
        str(SKILL_DIR),
        "--index-dir",
        str(index),
        "--leaf-target",
        "3",
    ])


def test_routing_and_incremental(temp: Path) -> None:
    root = temp / "skills"
    index = temp / "index"
    shutil.copytree(FIXTURES, root)
    first = build(root, index)
    assert_true(first["schema_version"] == "2.4.0", "deep schema should be 2.4.0")
    assert_true(first["reclassified_files"] == 13 and first["reused_files"] == 0, "first build should classify all files")

    explicit = next(json.loads(line) for line in (index / "deep" / "skills-deep-index.ndjson").read_text(encoding="utf-8").splitlines() if '"explicit-api-client"' in line)
    assert_true(set(explicit["setup_requirements"]) >= {"api-key", "local-runtime"}, "setup requirements should be multi-label")

    path = ""
    result: dict[str, Any] = {}
    for _ in range(12):
        command = [
            sys.executable,
            str(RECOMMENDER),
            "--query",
            "build a beautiful frontend UI",
            "--index-dir",
            str(index),
            "--skills-root",
            str(root),
            "--leaf-target",
            "3",
            "--limit",
            "12",
        ]
        if path:
            command.extend(["--path", path])
        result = run_json(command)
        if result["mode"] == "choose_skill":
            break
        path = result["branches"][0]["path"]
    assert_true(result["schema_version"] == "3.0.0", "unified recommender should expose an explicit schema")
    assert_true(result["mode"] == "choose_skill", "router should reach a skill shortlist")
    assert_true("frontend-design" in [item["name"] for item in result["candidates"]], "frontend skill should remain in the final route")

    target = root / "frontend-design" / "SKILL.md"
    target.write_text(target.read_text(encoding="utf-8") + "\nIncremental change.\n", encoding="utf-8")
    second = build(root, index)
    assert_true(second["reclassified_files"] == 1, "one changed file should cause one reclassification")
    assert_true(second["reused_files"] == 12, "unchanged classifications should be reused")
    assert_true(second["removed_files"] == 0, "no sources were removed")
    assert_true(not second["full_body_read"] and second["all_records_derived_from_full_body"], "incremental metadata should distinguish this-run reads from record provenance")

    replacement = temp / "replacement-root" / "replacement"
    replacement.mkdir(parents=True)
    (replacement / "SKILL.md").write_text("---\nname: replacement\ndescription: A replacement configured root.\n---\n", encoding="utf-8")
    switched = run_json([
        sys.executable,
        str(RECOMMENDER),
        "--query",
        "use replacement",
        "--index-dir",
        str(index),
        "--skills-root",
        str(replacement.parent),
    ])
    assert_true(switched["index"]["refresh_reason"] == "skills_roots_changed", "an explicit root-set change must refresh the index")
    assert_true(json.loads((index / "deep" / "metadata.json").read_text(encoding="utf-8"))["raw_files"] == 1, "root-set refresh must not retain sources from old roots")


def test_manifest_scope(temp: Path) -> None:
    root = temp / "scope-root"
    foreign = temp / "foreign"
    (root / "inside").mkdir(parents=True)
    (foreign / "outside").mkdir(parents=True)
    inside = root / "inside" / "SKILL.md"
    outside = foreign / "outside" / "SKILL.md"
    inside.write_text("---\nname: inside\ndescription: In configured scope.\n---\n", encoding="utf-8")
    outside.write_text("---\nname: outside\ndescription: Outside configured scope.\n---\n", encoding="utf-8")
    index = temp / "scope-index"
    index.mkdir()
    (index / "manifest.json").write_text(json.dumps({"files": [{"skill_md": str(inside)}, {"skill_md": str(outside)}]}), encoding="utf-8")
    result = build(root, index)
    assert_true(result["raw_files"] == 1, "legacy manifest entries outside configured roots must be ignored")
    source = json.loads((index / "deep" / "source-manifest.json").read_text(encoding="utf-8"))
    assert_true([Path(item["skill_md"]).name for item in source["files"]] == ["SKILL.md"], "source manifest should contain only current-root discovery")
    assert_true(Path(source["files"][0]["skill_md"]).parent.name == "inside", "foreign manifest path leaked into index")


def test_failure_manifest_and_memory_scope(temp: Path) -> None:
    root = temp / "failure-root"
    (root / "good").mkdir(parents=True)
    (root / "bad").mkdir(parents=True)
    (root / "good" / "SKILL.md").write_text("---\nname: good\ndescription: Works.\n---\n", encoding="utf-8")
    (root / "bad" / "SKILL.md").write_text("---\nname: bad\ndescription: Simulated failure.\n---\n", encoding="utf-8")
    index = temp / "failure-index"
    classifier = load_module("deep_classifier_failure_test", CLASSIFIER)
    original = classifier.classify_document

    def fail_bad(text: str, path: Path, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if path.parent.name == "bad":
            raise RuntimeError("simulated classifier failure")
        return original(text, path, *args, **kwargs)

    classifier.classify_document = fail_bad
    old_argv = sys.argv
    sys.argv = [str(CLASSIFIER), "--skills-root", str(root), "--skill-dir", str(SKILL_DIR), "--index-dir", str(index)]
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            assert_true(classifier.main() == 0, "failure-aware build should complete with an audit trail")
    finally:
        sys.argv = old_argv
    source = json.loads((index / "deep" / "source-manifest.json").read_text(encoding="utf-8"))
    statuses = {Path(item["skill_md"]).parent.name: item["classification_status"] for item in source["files"]}
    assert_true(statuses == {"bad": "failed", "good": "success"}, "failed sources must remain in the source manifest")
    router = load_module("deep_router_memory_test", ROUTER)
    metadata = json.loads((index / "deep" / "metadata.json").read_text(encoding="utf-8"))
    assert_true(router.check_index_freshness(metadata, index / "deep")["fresh"], "a completed failure-aware index should not be immediately stale")

    (index / "selection-memory.md").write_text(
        "### feedback\n- outcome: `selected`\n- selected_skill: `frontend-design`\n- route: `domain_detail` / `frontend-web`\n",
        encoding="utf-8",
    )
    assert_true(router.load_selection_memory(index, {}) == {}, "route-scoped memory must not affect root-level ranking")
    assert_true(router.load_selection_memory(index, {"domain_detail": "frontend-web"}).get("frontend-design", 0) > 0, "matching route memory should still apply")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="skill-selection-python-smoke-") as value:
        temp = Path(value)
        test_routing_and_incremental(temp / "routing")
        test_manifest_scope(temp / "scope")
        test_failure_manifest_and_memory_scope(temp / "failure")
    print(json.dumps({"status": "passed", "platform": sys.platform}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
