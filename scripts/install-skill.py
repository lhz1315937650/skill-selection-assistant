#!/usr/bin/env python3
"""Portable installer for skill-selection-assistant."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def resolve_codex_home(explicit: str) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    env_home = os.environ.get("CODEX_HOME", "").strip()
    if env_home:
        return Path(env_home).expanduser()
    return Path.home() / ".codex"


def copy_skill(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for item_name in ("SKILL.md", "agents", "rules", "scripts"):
        src = source / item_name
        dst = destination / item_name
        if not src.exists():
            continue
        if dst.exists():
            if dst.is_dir():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".skill-index", "__pycache__"))
        else:
            shutil.copy2(src, dst)


def find_powershell() -> str:
    for command in ("pwsh", "powershell"):
        if shutil.which(command):
            return command
    return ""


def run_scan(destination: Path, skills_root: str) -> dict:
    shell = find_powershell()
    if not shell:
        return {
            "scan_ran": False,
            "scan_skipped_reason": "PowerShell was not found. Run scripts/scan-local-skills.ps1 manually after installing PowerShell/pwsh, or use the skill and let first-use diagnostics guide you.",
        }

    scan_script = destination / "scripts" / "scan-local-skills.ps1"
    if not scan_script.exists():
        raise FileNotFoundError(f"Installed scanner not found: {scan_script}")

    command = [shell, "-ExecutionPolicy", "Bypass", "-File", str(scan_script)]
    if skills_root:
        command.extend(["-SkillsRoot", skills_root])

    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return {
            "scan_ran": False,
            "scan_skipped_reason": "Scanner exited with a non-zero status.",
            "scanner_stdout": result.stdout.strip(),
            "scanner_stderr": result.stderr.strip(),
        }

    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        parsed = {"scanner_stdout": result.stdout.strip()}
    parsed["scan_ran"] = True
    return parsed


def run_summary(destination: Path, index_dir: str) -> dict:
    summary_script = destination / "scripts" / "summarize-index.py"
    if not summary_script.exists():
        return {"summary_ran": False, "summary_skipped_reason": f"Summary script not found: {summary_script}"}
    if not index_dir:
        return {"summary_ran": False, "summary_skipped_reason": "Index directory is unknown."}

    result = subprocess.run(
        [sys.executable, str(summary_script), "--index-dir", index_dir],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return {
            "summary_ran": False,
            "summary_skipped_reason": "Summary script exited with a non-zero status.",
            "summary_stdout": result.stdout.strip(),
            "summary_stderr": result.stderr.strip(),
        }
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        parsed = {"summary_stdout": result.stdout.strip()}
    parsed["summary_ran"] = True
    return parsed


def run_deep_index(destination: Path, index_dir: str, skills_root: str) -> dict:
    deep_script = destination / "scripts" / "deep-classify-skills.py"
    if not deep_script.exists():
        return {"deep_index_ran": False, "deep_index_skipped_reason": f"Deep classifier not found: {deep_script}"}
    if not skills_root:
        return {"deep_index_ran": False, "deep_index_skipped_reason": "Skills root is unknown."}
    result = subprocess.run(
        [sys.executable, str(deep_script), "--skills-root", skills_root, "--index-dir", index_dir],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return {
            "deep_index_ran": False,
            "deep_index_skipped_reason": "Deep classifier exited with a non-zero status.",
            "deep_index_stdout": result.stdout.strip(),
            "deep_index_stderr": result.stderr.strip(),
        }
    metadata_path = Path(index_dir) / "deep" / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig")) if metadata_path.exists() else {}
    return {"deep_index_ran": True, "deep_index": str(metadata_path), "deep_index_metadata": metadata}


def main() -> int:
    parser = argparse.ArgumentParser(description="Install skill-selection-assistant into a local Codex skills directory.")
    parser.add_argument("--codex-home", default="", help="Codex home directory. Defaults to CODEX_HOME or ~/.codex.")
    parser.add_argument("--destination", default="", help="Install destination. Defaults to <codex-home>/skills/skill-selection-assistant.")
    parser.add_argument("--skills-root", default="", help="Skills root to scan. Defaults to the runtime resolver in scan-local-skills.ps1.")
    parser.add_argument("--skip-scan", action="store_true", help="Copy the skill without running the first local scan.")
    parser.add_argument("--skip-deep-index", action="store_true", help="Skip the exhaustive first-use SKILL.md classification.")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing installed router skill.")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    source = repo_root / "skill-selection-assistant"
    if not (source / "SKILL.md").exists():
        raise FileNotFoundError(f"Cannot find skill source folder: {source}")

    destination = Path(args.destination).expanduser() if args.destination else resolve_codex_home(args.codex_home) / "skills" / "skill-selection-assistant"
    if destination.exists() and not args.force:
        raise FileExistsError(f"Destination already exists: {destination}. Re-run with --force to update the installed router skill.")

    copy_skill(source=source, destination=destination)

    scan_result: dict = {"scan_ran": False, "scan_skipped_reason": "skip-scan was requested."}
    if not args.skip_scan:
        scan_result = run_scan(destination=destination, skills_root=args.skills_root)
    index_dir = str(scan_result.get("OutputDir", destination / ".skill-index"))
    summary_result: dict = {"summary_ran": False, "summary_skipped_reason": "scan was skipped or did not complete."}
    deep_result: dict = {"deep_index_ran": False, "deep_index_skipped_reason": "deep indexing was not requested."}
    if scan_result.get("scan_ran"):
        summary_result = run_summary(destination=destination, index_dir=index_dir)
    if not args.skip_scan and not args.skip_deep_index:
        deep_result = run_deep_index(
            destination=destination,
            index_dir=index_dir,
            skills_root=str(scan_result.get("SkillsRoot") or args.skills_root or destination.parent),
        )
    elif args.skip_deep_index:
        deep_result = {"deep_index_ran": False, "deep_index_skipped_reason": "skip-deep-index was requested."}
    else:
        deep_result = {"deep_index_ran": False, "deep_index_skipped_reason": "skip-scan was requested."}

    output = {
        "status": "installed",
        "destination": str(destination.resolve()),
        "skills_root": scan_result.get("SkillsRoot", args.skills_root),
        "index_dir": index_dir,
        **scan_result,
        **summary_result,
        **deep_result,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
