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
INSTALLER = REPO / "scripts" / "install-skill.py"
AGENTS_MARKER_START = "<!-- skill-selection-assistant:start -->"


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


def test_skill_contract() -> None:
    skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = skill_text.split("---", 2)[1]
    top_level_keys = {
        line.split(":", 1)[0].strip()
        for line in frontmatter.splitlines()
        if line.strip() and not line.startswith((" ", "\t")) and ":" in line
    }
    assert_true(top_level_keys == {"name", "description"}, "skill frontmatter should contain only the current name/description contract")
    agent_metadata = (SKILL_DIR / "agents" / "openai.yaml").read_text(encoding="utf-8")
    assert_true("$skill-selection-assistant" in agent_metadata, "UI default prompt should explicitly invoke the skill")
    assert_true("�" not in skill_text + agent_metadata, "published skill metadata should not contain replacement characters")


def test_routing_and_incremental(temp: Path) -> None:
    root = temp / "skills"
    index = temp / "index"
    shutil.copytree(FIXTURES, root)
    first = build(root, index)
    assert_true(first["schema_version"] == "2.5.0", "deep schema should be 2.5.0")
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
    assert_true("deep_route" not in result, "default recommendation output should not duplicate the deep route payload")
    assert_true(result["mode"] == "choose_skill", "router should reach a skill shortlist")
    assert_true("frontend-design" in [item["name"] for item in result["candidates"]], "frontend skill should remain in the final route")
    compatible = run_json(command + ["--compat"])
    assert_true("deep_route" in compatible, "legacy consumers should be able to request the nested deep route payload")
    invalid = subprocess.run(
        [sys.executable, str(RECOMMENDER), "--query", "invalid path", "--index-dir", str(index), "--path", "unknown=missing", "--compact"],
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_result = json.loads(invalid.stdout)
    assert_true(invalid.returncode == 1 and invalid_result["mode"] == "error" and not invalid.stderr, "expected routing errors should be structured without tracebacks")

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

    (index / "deep" / "route-cards.json").write_text("{broken", encoding="utf-8")
    repaired = run_json([
        sys.executable,
        str(RECOMMENDER),
        "--query",
        "use replacement",
        "--index-dir",
        str(index),
    ])
    assert_true(repaired["index"]["refreshed"] and repaired["index"]["refresh_reason"] == "index_corrupt", "a corrupt routing artifact should be rebuilt automatically")
    assert_true(json.loads((index / "deep" / "route-cards.json").read_text(encoding="utf-8")), "automatic repair should publish valid route cards")


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
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(io.StringIO()):
            assert_true(classifier.main() == 0, "failure-aware build should complete with an audit trail")
    finally:
        sys.argv = old_argv
    assert_true(json.loads(captured.getvalue())["status"] == "degraded", "partial classification should be reported as degraded")
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


def test_linked_skill_and_concurrent_publish(temp: Path) -> None:
    root = temp / "linked-root"
    external = temp / "external"
    logical = root / "linked-skill"
    logical.mkdir(parents=True)
    external.mkdir(parents=True)
    external_file = external / "external-SKILL.md"
    external_file.write_text("---\nname: linked-external\ndescription: A linked external skill.\n---\n", encoding="utf-8")
    try:
        (logical / "SKILL.md").symlink_to(external_file)
    except OSError:
        return
    index = temp / "linked-index"
    linked = build(root, index)
    assert_true(linked["raw_files"] == 1, "a linked skill file should be classified")
    item = json.loads((index / "deep" / "skills-deep-index.ndjson").read_text(encoding="utf-8").strip())
    assert_true(item["origin"] == "linked-external", "linked skills should retain explicit provenance")
    assert_true(Path(item["logical_skill_md"]).parent.name == "linked-skill", "linked skills should retain their logical entry path")

    processes = [
        subprocess.Popen(
            [
                sys.executable,
                str(CLASSIFIER),
                "--skills-root",
                str(root),
                "--skill-dir",
                str(SKILL_DIR),
                "--index-dir",
                str(index),
                "--full-rebuild",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(4)
    ]
    results = [process.communicate(timeout=60) + (process.returncode,) for process in processes]
    assert_true(all(result[2] == 0 for result in results), f"concurrent publishers should all succeed: {results}")
    assert_true(json.loads((index / "deep" / "metadata.json").read_text(encoding="utf-8"))["raw_files"] == 1, "concurrent publishing should leave a readable index")


def test_transactional_installer_copy(temp: Path) -> None:
    installer = load_module("transactional_installer_test", INSTALLER)
    source = temp / "source"
    destination = temp / "destination"
    (source / "agents").mkdir(parents=True)
    destination.mkdir(parents=True)
    (source / "SKILL.md").write_text("new skill", encoding="utf-8")
    (source / "VERSION").write_text("new version", encoding="utf-8")
    (source / "agents" / "openai.yaml").write_text("new metadata", encoding="utf-8")
    (destination / "SKILL.md").write_text("old skill", encoding="utf-8")
    (destination / "VERSION").write_text("old version", encoding="utf-8")
    (destination / ".skill-index").mkdir()
    (destination / ".skill-index" / "keep.txt").write_text("runtime state", encoding="utf-8")

    original_replace = installer.os.replace
    failure_injected = False

    def fail_during_publish(src: Any, dst: Any) -> None:
        nonlocal failure_injected
        source_path = Path(src)
        if source_path.parent.name == "staged" and source_path.name == "VERSION" and not failure_injected:
            failure_injected = True
            raise OSError("simulated managed-file publish failure")
        original_replace(src, dst)

    installer.os.replace = fail_during_publish
    try:
        try:
            installer.copy_skill(source, destination)
        except OSError:
            pass
        else:
            raise AssertionError("transaction failure injection did not run")
    finally:
        installer.os.replace = original_replace
    assert_true((destination / "SKILL.md").read_text(encoding="utf-8") == "old skill", "a failed update should restore the previous SKILL.md")
    assert_true((destination / "VERSION").read_text(encoding="utf-8") == "old version", "a failed update should restore the previous version")
    assert_true((destination / ".skill-index" / "keep.txt").read_text(encoding="utf-8") == "runtime state", "transaction rollback must preserve runtime index state")
    assert_true(not list(temp.glob(".skill-selection-install-*")), "transaction staging directories should be cleaned after rollback")


def test_first_install_experience(temp: Path) -> None:
    codex_home = temp / "custom-codex-home"
    skills = codex_home / "skills"
    shutil.copytree(FIXTURES / "frontend-design", skills / "frontend-design")
    codex_home.mkdir(exist_ok=True)
    (codex_home / "AGENTS.md").write_text("Notes about the skill-selection-assistant repository.\n", encoding="utf-8")
    installed = run_json([
        sys.executable,
        str(INSTALLER),
        "--codex-home",
        str(codex_home),
        "--configure-agents",
        "--json",
    ])
    assert_true(installed["status"] == "installed" and installed["health_status"] == "ok", "first install should finish with a health check")
    if shutil.which("pwsh") or shutil.which("powershell"):
        assert_true(installed["scan_ran"] and installed["RawTotal"] == 1, "PowerShell scanner output should be parsed as structured JSON")
        assert_true("scanner_stdout" not in installed, "successful scanner output should not leak a formatted PowerShell table")
    assert_true(installed["deep_index_metadata"]["raw_files"] == 1, "--codex-home should scan its own skills directory")
    assert_true(installed["deep_index_metadata"]["skills_roots"] == [str(skills.resolve())], "custom Codex home must not fall back to another machine root")
    assert_true(AGENTS_MARKER_START in (codex_home / "AGENTS.md").read_text(encoding="utf-8"), "explicit activation should append a managed AGENTS block")
    assert_true(installed["activation_state"] == "managed", "a prose-only repository mention must not be mistaken for activation")
    assert_true(installed["version"] == "1.7.1", "installer should report the installed version")
    installed_dir = codex_home / "skills" / "skill-selection-assistant"
    memory = run_json([
        sys.executable,
        str(installed_dir / "scripts" / "record-selection-memory.py"),
        "--query",
        "private first-install request",
        "--outcome",
        "selected",
        "--selected-skill",
        "frontend-design",
    ])
    assert_true(not memory["query_stored"], "cross-platform memory should not retain raw queries by default")
    assert_true("private first-install request" not in Path(memory["memory"]).read_text(encoding="utf-8"), "private query text leaked into selection memory")
    doctor = run_json([sys.executable, str(installed_dir / "scripts" / "doctor.py")])
    assert_true(doctor["status"] == "ok" and doctor["recommendation_exit_code"] == 0, "the installed Python doctor should work after the repository is removed")

    (installed_dir / ".skill-index" / "deep" / "metadata.json").write_text("{broken", encoding="utf-8")
    diagnosed = subprocess.run(
        [sys.executable, str(installed_dir / "scripts" / "doctor.py"), "--compact"],
        text=True,
        capture_output=True,
        check=False,
    )
    diagnosis = json.loads(diagnosed.stdout)
    assert_true(diagnosed.returncode == 1 and diagnosis["status"] == "needs-attention" and not diagnosed.stderr, "doctor should report corrupt indexes without a traceback")
    repaired = run_json([sys.executable, str(installed_dir / "scripts" / "doctor.py"), "--fix"])
    assert_true(repaired["status"] == "ok" and repaired["fixed"], "doctor --fix should repair a corrupt index using recovered roots")

    repeated = subprocess.run(
        [sys.executable, str(INSTALLER), "--codex-home", str(codex_home), "--json"],
        text=True,
        capture_output=True,
        check=False,
    )
    repeated_error = json.loads(repeated.stdout)
    assert_true(repeated.returncode == 1 and repeated_error["status"] == "error", "expected install conflicts should return structured errors without tracebacks")

    broken_home = temp / "broken-agents-home"
    broken_home.mkdir(parents=True)
    (broken_home / "AGENTS.md").write_text(AGENTS_MARKER_START + "\n", encoding="utf-8")
    broken_install = subprocess.run(
        [sys.executable, str(INSTALLER), "--codex-home", str(broken_home), "--configure-agents", "--json"],
        text=True,
        capture_output=True,
        check=False,
    )
    broken_result = json.loads(broken_install.stdout)
    assert_true(broken_install.returncode == 1 and broken_result["error_type"] == "ValueError", "unbalanced managed AGENTS markers should fail safely")
    assert_true(not (broken_home / "skills" / "skill-selection-assistant").exists(), "AGENTS preflight failure should happen before installing managed files")

    zh_plan = subprocess.run(
        [sys.executable, str(INSTALLER), "--codex-home", str(temp / "zh-plan-home"), "--dry-run", "--lang", "zh"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert_true(zh_plan.returncode == 0 and "技能选择助手" in zh_plan.stdout and "准备安装" not in zh_plan.stdout, "Chinese dry-run output should remain valid UTF-8 and clearly identify the assistant")

    empty_home = temp / "empty-codex-home"
    empty = run_json([sys.executable, str(INSTALLER), "--codex-home", str(empty_home), "--json"])
    assert_true(empty["health_mode"] == "no_skills_installed", "an empty first install should pass with a friendly no-skills mode")
    recommendation = run_json([
        sys.executable,
        str(empty_home / "skills" / "skill-selection-assistant" / "scripts" / "recommend-skills.py"),
        "--query",
        "analyze data",
        "--compact",
    ])
    assert_true(recommendation["mode"] == "no_skills_installed" and recommendation["candidates"] == [], "empty libraries must not raise a traceback")

    memory_index = temp / "concurrent-memory"
    memory_script = installed_dir / "scripts" / "record-selection-memory.py"
    writers = [
        subprocess.Popen(
            [
                sys.executable,
                str(memory_script),
                "--query",
                f"private query {number}",
                "--selected-skill",
                f"skill`{number}",
                "--route-type",
                "domain_detail",
                "--category",
                "frontend`web",
                "--index-dir",
                str(memory_index),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for number in range(8)
    ]
    writer_results = [writer.communicate(timeout=30) + (writer.returncode,) for writer in writers]
    assert_true(all(item[2] == 0 for item in writer_results), f"concurrent memory writers should succeed: {writer_results}")
    memory_text = (memory_index / "selection-memory.md").read_text(encoding="utf-8")
    assert_true(memory_text.count("### ") == 8, "concurrent feedback writes should not lose entries")
    assert_true("private query" not in memory_text and "skill`" not in memory_text and "frontend`" not in memory_text, "memory fields should remain private and Markdown-safe")


def main() -> int:
    test_skill_contract()
    with tempfile.TemporaryDirectory(prefix="skill-selection-python-smoke-") as value:
        temp = Path(value)
        test_routing_and_incremental(temp / "routing")
        test_manifest_scope(temp / "scope")
        test_failure_manifest_and_memory_scope(temp / "failure")
        test_linked_skill_and_concurrent_publish(temp / "linked")
        test_transactional_installer_copy(temp / "transaction")
        test_first_install_experience(temp / "install")
    print(json.dumps({"status": "passed", "platform": sys.platform}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
