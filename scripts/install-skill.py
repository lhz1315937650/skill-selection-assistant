#!/usr/bin/env python3
"""Portable, first-time-friendly installer for skill-selection-assistant."""

from __future__ import annotations

import argparse
import json
import locale
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


MIN_PYTHON = (3, 10)
AGENTS_MARKER_START = "<!-- skill-selection-assistant:start -->"
AGENTS_MARKER_END = "<!-- skill-selection-assistant:end -->"
MANAGED_ITEMS = ("SKILL.md", "VERSION", "agents", "references", "rules", "schemas", "scripts")


def resolve_codex_home(explicit: str) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env_home = os.environ.get("CODEX_HOME", "").strip()
    if env_home:
        return Path(env_home).expanduser().resolve()
    return (Path.home() / ".codex").resolve()


def resolve_roots(values: list[str], codex_home: Path, explicit_codex_home: bool) -> list[str]:
    candidates = [Path(value).expanduser() for value in values if value]
    if not candidates:
        candidates.append(codex_home / "skills")
        default_codex_home = (Path.home() / ".codex").resolve()
        agents_root = Path.home() / ".agents" / "skills"
        if not explicit_codex_home and codex_home == default_codex_home and agents_root.is_dir():
            candidates.append(agents_root)
    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        key = os.path.normcase(str(resolved))
        if key not in seen:
            seen.add(key)
            result.append(str(resolved))
    return result


def read_version(skill_dir: Path) -> str:
    version_path = skill_dir / "VERSION"
    return version_path.read_text(encoding="utf-8-sig").strip() if version_path.exists() else "development"


def path_present(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def remove_path(path: Path) -> None:
    if not path_present(path):
        return
    if path.is_symlink() or not path.is_dir():
        path.unlink()
    else:
        shutil.rmtree(path)


def copy_skill(source: Path, destination: Path) -> None:
    """Replace managed files as one rollback-capable transaction.

    Local runtime state such as .skill-index and unrelated user files are never
    staged, moved, or deleted.
    """
    if destination.is_symlink():
        raise RuntimeError(f"Refusing to install through a symlinked destination: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    created_destination = not path_present(destination)
    destination.mkdir(parents=True, exist_ok=True)
    transaction_root = Path(tempfile.mkdtemp(prefix=".skill-selection-install-", dir=destination.parent))
    staged_root = transaction_root / "staged"
    backup_root = transaction_root / "backup"
    staged_root.mkdir()
    backup_root.mkdir()
    replaced: list[tuple[Path, Path, bool]] = []
    try:
        for item_name in MANAGED_ITEMS:
            src = source / item_name
            staged = staged_root / item_name
            if not src.exists():
                continue
            if src.is_dir():
                shutil.copytree(src, staged, ignore=shutil.ignore_patterns(".skill-index", "__pycache__", "*.pyc"))
            else:
                shutil.copy2(src, staged)

        for item_name in MANAGED_ITEMS:
            destination_item = destination / item_name
            staged_item = staged_root / item_name
            backup_item = backup_root / item_name
            had_existing = path_present(destination_item)
            if had_existing:
                os.replace(destination_item, backup_item)
            replaced.append((destination_item, backup_item, had_existing))
            if path_present(staged_item):
                os.replace(staged_item, destination_item)
    except Exception:
        for destination_item, backup_item, had_existing in reversed(replaced):
            remove_path(destination_item)
            if had_existing and path_present(backup_item):
                os.replace(backup_item, destination_item)
        if created_destination:
            try:
                destination.rmdir()
            except OSError:
                pass
        raise
    finally:
        shutil.rmtree(transaction_root, ignore_errors=True)


def find_powershell() -> str:
    for command in ("pwsh", "powershell"):
        if shutil.which(command):
            return command
    return ""


def completed_process(command: list[str], stream_progress: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=None if stream_progress else subprocess.PIPE,
        check=False,
    )


def run_scan(destination: Path, skills_root: str, stream_progress: bool) -> dict[str, Any]:
    shell = find_powershell()
    if not shell:
        return {
            "scan_ran": False,
            "scan_skipped_reason": "PowerShell was not found. The deep Python index will still be built and normal recommendations remain available; only legacy reports are skipped.",
        }
    scan_script = destination / "scripts" / "scan-local-skills.ps1"
    if not scan_script.exists():
        raise FileNotFoundError(f"Installed scanner not found: {scan_script}")
    command = [
        shell,
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(scan_script),
        "-SkillsRoot",
        skills_root,
        "-AsJson",
    ]
    result = completed_process(command, stream_progress)
    if result.returncode != 0:
        return {
            "scan_ran": False,
            "scan_skipped_reason": "The optional legacy scanner exited with a non-zero status; the deep Python index can still be used.",
            "scanner_stdout": result.stdout.strip(),
            "scanner_stderr": (result.stderr or "").strip(),
        }
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        parsed = {"scanner_stdout": result.stdout.strip()}
    parsed["scan_ran"] = True
    return parsed


def run_summary(destination: Path, index_dir: str) -> dict[str, Any]:
    summary_script = destination / "scripts" / "summarize-index.py"
    if not summary_script.exists():
        return {"summary_ran": False, "summary_skipped_reason": f"Summary script not found: {summary_script}"}
    result = completed_process([sys.executable, str(summary_script), "--index-dir", index_dir])
    if result.returncode != 0:
        return {
            "summary_ran": False,
            "summary_skipped_reason": "Summary script exited with a non-zero status.",
            "summary_stdout": result.stdout.strip(),
            "summary_stderr": (result.stderr or "").strip(),
        }
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        parsed = {"summary_stdout": result.stdout.strip()}
    parsed["summary_ran"] = True
    return parsed


def run_deep_index(destination: Path, index_dir: str, skills_roots: list[str], stream_progress: bool) -> dict[str, Any]:
    deep_script = destination / "scripts" / "deep-classify-skills.py"
    if not deep_script.exists():
        return {"deep_index_ran": False, "deep_index_skipped_reason": f"Deep classifier not found: {deep_script}"}
    command = [sys.executable, str(deep_script), "--index-dir", index_dir]
    for skills_root in skills_roots:
        command.extend(["--skills-root", skills_root])
    result = completed_process(command, stream_progress)
    if result.returncode != 0:
        return {
            "deep_index_ran": False,
            "deep_index_skipped_reason": "Deep classifier exited with a non-zero status.",
            "deep_index_stdout": result.stdout.strip(),
            "deep_index_stderr": (result.stderr or "").strip(),
        }
    metadata_path = Path(index_dir) / "deep" / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig")) if metadata_path.exists() else {}
    return {"deep_index_ran": True, "deep_index": str(metadata_path), "deep_index_metadata": metadata}


def run_health_check(destination: Path, index_dir: str) -> dict[str, Any]:
    recommender = destination / "scripts" / "recommend-skills.py"
    if not recommender.exists() or not (Path(index_dir) / "deep" / "metadata.json").exists():
        return {"health_check_ran": False, "health_status": "not-ready", "health_reason": "The deep index is not available."}
    result = completed_process([
        sys.executable,
        str(recommender),
        "--query",
        "help me choose an installed local skill",
        "--index-dir",
        index_dir,
        "--compact",
    ])
    if result.returncode != 0:
        return {
            "health_check_ran": True,
            "health_status": "failed",
            "health_reason": (result.stderr or result.stdout).strip()[-1000:],
        }
    parsed = json.loads(result.stdout)
    return {"health_check_ran": True, "health_status": "ok", "health_mode": parsed.get("mode", "")}


def count_skill_files(roots: list[str], destination: Path) -> int:
    excluded = os.path.normcase(str((destination / "SKILL.md").resolve()))
    found: set[str] = set()
    for root_value in roots:
        root = Path(root_value)
        if not root.is_dir():
            continue
        for candidate in root.rglob("SKILL.md"):
            key = os.path.normcase(str(candidate.resolve()))
            if key != excluded:
                found.add(key)
    return len(found)


def agents_block(destination: Path) -> str:
    return "\n".join([
        AGENTS_MARKER_START,
        "## Local skill selection",
        "",
        "Before answering each new normal request:",
        "",
        "1. Use the installed `skill-selection-assistant` first.",
        f"2. Run `python \"{destination / 'scripts' / 'recommend-skills.py'}\" --query \"<user request>\" --compact`.",
        "3. Present the returned weighted skills in the user's language and ask which one to use.",
        "4. Keep the chosen skill active for later turns in the same workflow.",
        "5. Ask before dependency downloads and before assuming user-owned prerequisite settings.",
        AGENTS_MARKER_END,
        "",
    ])


def configure_agents(agents_path: Path, destination: Path, write: bool) -> dict[str, Any]:
    existing = agents_path.read_text(encoding="utf-8-sig", errors="replace") if agents_path.exists() else ""
    start_count = existing.count(AGENTS_MARKER_START)
    end_count = existing.count(AGENTS_MARKER_END)
    marker_order_valid = (
        start_count == 1
        and end_count == 1
        and existing.index(AGENTS_MARKER_START) < existing.index(AGENTS_MARKER_END)
    )
    if start_count or end_count:
        activation_state = "managed" if marker_order_valid else "corrupt-managed-block"
    elif "recommend-skills.py" in existing and "skill-selection-assistant" in existing:
        activation_state = "legacy"
    else:
        activation_state = "not-configured"
    if write and activation_state == "corrupt-managed-block":
        raise ValueError(
            f"The managed skill-selection block in {agents_path} has missing, duplicated, or out-of-order markers. "
            "Repair that block before running --configure-agents again."
        )
    configured = activation_state in {"managed", "legacy"}
    if write and not configured:
        agents_path.parent.mkdir(parents=True, exist_ok=True)
        prefix = existing.rstrip() + "\n\n" if existing.strip() else ""
        agents_path.write_text(prefix + agents_block(destination), encoding="utf-8")
        configured = True
        activation_state = "managed"
    return {
        "activation_configured": configured,
        "activation_state": activation_state,
        "agents_file": str(agents_path),
        "activation_write_requested": write,
    }


def human_language(requested: str) -> str:
    if requested != "auto":
        return requested
    value = (locale.getlocale()[0] or "").lower()
    return "zh" if value.startswith("zh") else "en"


def emit_human(output: dict[str, Any], language: str) -> None:
    zh = language == "zh"
    print("\n技能选择助手" if zh else "\nSkill Selection Assistant")
    labels = {
        "status": "状态" if zh else "Status",
        "version": "版本" if zh else "Version",
        "destination": "安装位置" if zh else "Destination",
        "roots": "扫描目录" if zh else "Skill roots",
        "found": "发现技能" if zh else "Skills discovered",
        "health": "自检" if zh else "Health check",
    }
    print(f"{labels['status']}: {output.get('status')}")
    print(f"{labels['version']}: {output.get('version')}")
    print(f"{labels['destination']}: {output.get('destination')}")
    print(f"{labels['roots']}: {', '.join(output.get('skills_roots', []))}")
    metadata = output.get("deep_index_metadata") or {}
    print(f"{labels['found']}: {metadata.get('raw_files', output.get('planned_skill_files', 0))}")
    if output.get("health_check_ran"):
        print(f"{labels['health']}: {output.get('health_status')} ({output.get('health_mode', '')})")
    if not output.get("activation_configured") and output.get("status") != "planned":
        print("下一步：如需在普通请求前自动选择 skill，请重新安装时添加 --configure-agents。" if zh else "Next: add --configure-agents during install if you want skill selection before normal requests.")
    if output.get("scan_skipped_reason"):
        print(("提示：" if zh else "Note: ") + str(output["scan_skipped_reason"]))
    if int(metadata.get("failed_files") or 0):
        print(("警告：" if zh else "Warning: ") + f"{metadata['failed_files']} skill files failed classification.")


def emit(output: dict[str, Any], json_mode: bool, language: str) -> None:
    if json_mode:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        emit_human(output, language)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install skill-selection-assistant into a local Codex skills directory (Python 3.10+).")
    parser.add_argument("--codex-home", default="", help="Codex home directory. Defaults to CODEX_HOME or ~/.codex.")
    parser.add_argument("--destination", default="", help="Install destination. Defaults to <codex-home>/skills/skill-selection-assistant.")
    parser.add_argument("--skills-root", action="append", default=[], help="Skills root to index. Repeat for multiple roots.")
    parser.add_argument("--skip-scan", action="store_true", help="Copy the skill only; skip both compatibility and deep indexing.")
    parser.add_argument("--skip-deep-index", action="store_true", help="Run the compatibility scan but skip exhaustive deep classification.")
    parser.add_argument("--force", action="store_true", help="Update an existing installation while preserving its .skill-index.")
    parser.add_argument("--dry-run", action="store_true", help="Show the resolved installation plan without changing files.")
    parser.add_argument("--check", action="store_true", help="Check an existing installation without changing files.")
    parser.add_argument("--configure-agents", action="store_true", help="Append a managed opt-in activation block to the global AGENTS.md.")
    parser.add_argument("--agents-file", default="", help="AGENTS.md path used with --configure-agents or activation detection.")
    parser.add_argument("--no-health-check", action="store_true", help="Skip the first recommendation self-test.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON instead of a human summary.")
    parser.add_argument("--lang", choices=("auto", "zh", "en"), default="auto", help="Language for human output.")
    parser.add_argument("--debug", action="store_true", help="Show Python tracebacks for unexpected failures.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if sys.version_info < MIN_PYTHON:
        raise RuntimeError(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer is required.")
    repo_root = Path(__file__).resolve().parents[1]
    source = repo_root / "skill-selection-assistant"
    if not (source / "SKILL.md").exists():
        raise FileNotFoundError(f"Cannot find skill source folder: {source}")

    codex_home = resolve_codex_home(args.codex_home)
    destination = (Path(args.destination).expanduser() if args.destination else codex_home / "skills" / "skill-selection-assistant").resolve()
    skills_roots = resolve_roots(args.skills_root, codex_home, bool(args.codex_home))
    agents_path = Path(args.agents_file).expanduser().resolve() if args.agents_file else codex_home / "AGENTS.md"
    version = read_version(source)
    language = human_language(args.lang)
    activation_preflight = configure_agents(agents_path, destination, False)
    if args.configure_agents and activation_preflight["activation_state"] == "corrupt-managed-block":
        raise ValueError(
            f"The managed skill-selection block in {agents_path} has missing, duplicated, or out-of-order markers. "
            "Repair that block before running --configure-agents again."
        )

    if args.check:
        if not destination.is_dir():
            raise FileNotFoundError(f"Installation not found: {destination}")
        index_dir = destination / ".skill-index"
        metadata_path = index_dir / "deep" / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig")) if metadata_path.exists() else {}
        activation = activation_preflight
        health = run_health_check(destination, str(index_dir)) if not args.no_health_check else {"health_check_ran": False}
        output = {
            "status": "installed" if (destination / "SKILL.md").exists() else "not-installed",
            "version": read_version(destination),
            "destination": str(destination),
            "skills_roots": metadata.get("skills_roots", skills_roots),
            "index_dir": str(index_dir),
            "deep_index_metadata": metadata,
            **activation,
            **health,
        }
        emit(output, args.json, language)
        return 0 if output["status"] == "installed" and output.get("health_status", "ok") == "ok" else 1

    planned_count = count_skill_files(skills_roots, destination)
    if args.dry_run:
        activation = activation_preflight
        output = {
            "status": "planned",
            "version": version,
            "destination": str(destination),
            "skills_roots": skills_roots,
            "planned_skill_files": planned_count,
            "powershell_available": bool(find_powershell()),
            **activation,
        }
        emit(output, args.json, language)
        return 0

    if destination.exists() and not args.force:
        raise FileExistsError(f"Destination already exists: {destination}. Re-run with --force to update, or --check to inspect it.")
    if not args.json:
        print(("准备安装" if language == "zh" else "Preparing installation") + f" v{version}")
        print(("安装位置：" if language == "zh" else "Destination: ") + str(destination))
        print(("扫描目录：" if language == "zh" else "Skill roots: ") + ", ".join(skills_roots))
        print(("预计发现：" if language == "zh" else "Discovered before install: ") + str(planned_count))

    copy_skill(source, destination)
    scan_result: dict[str, Any] = {"scan_ran": False, "scan_skipped_reason": "--skip-scan was requested."}
    if not args.skip_scan:
        scan_result = run_scan(destination, skills_roots[0], stream_progress=not args.json)
    index_dir = str(scan_result.get("OutputDir") or destination / ".skill-index")
    summary_result: dict[str, Any] = {"summary_ran": False, "summary_skipped_reason": "The optional compatibility scan did not complete."}
    if scan_result.get("scan_ran"):
        summary_result = run_summary(destination, index_dir)

    if args.skip_scan:
        deep_result: dict[str, Any] = {"deep_index_ran": False, "deep_index_skipped_reason": "--skip-scan was requested."}
    elif args.skip_deep_index:
        deep_result = {"deep_index_ran": False, "deep_index_skipped_reason": "--skip-deep-index was requested."}
    else:
        deep_result = run_deep_index(destination, index_dir, skills_roots, stream_progress=not args.json)

    activation = configure_agents(agents_path, destination, args.configure_agents)
    health = (
        run_health_check(destination, index_dir)
        if not args.no_health_check and deep_result.get("deep_index_ran")
        else {"health_check_ran": False, "health_status": "not-run"}
    )
    metadata = deep_result.get("deep_index_metadata") or {}
    installation_state = "degraded" if int(metadata.get("failed_files") or 0) else "complete"
    if not deep_result.get("deep_index_ran"):
        installation_state = "copy-only" if args.skip_scan else "compatibility-only"
    output = {
        **scan_result,
        **summary_result,
        **deep_result,
        **activation,
        **health,
        "status": "installed",
        "installation_state": installation_state,
        "version": version,
        "destination": str(destination),
        "skills_root": skills_roots[0] if skills_roots else "",
        "skills_roots": skills_roots,
        "planned_skill_files": planned_count,
        "index_dir": index_dir,
    }
    emit(output, args.json, language)
    return 0 if health.get("health_status", "ok") != "failed" else 1


def cli() -> int:
    try:
        return main()
    except Exception as exc:
        if "--debug" in sys.argv:
            raise
        suggestion = ""
        if isinstance(exc, FileExistsError):
            suggestion = "Use --force to update the installation or --check to inspect it."
        elif isinstance(exc, FileNotFoundError):
            suggestion = "Check the repository path, destination, and configured skills roots."
        payload = {"status": "error", "error_type": type(exc).__name__, "message": str(exc), "suggestion": suggestion}
        if "--json" in sys.argv:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Installation failed: {exc}", file=sys.stderr)
            if suggestion:
                print(suggestion, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(cli())
