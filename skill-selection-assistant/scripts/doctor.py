#!/usr/bin/env python3
"""Cross-platform health check for an installed skill-selection-assistant."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the installed router and its local deep index.")
    parser.add_argument("--index-dir", default="")
    args = parser.parse_args()
    script_dir = Path(__file__).resolve().parent
    skill_dir = script_dir.parent
    index_dir = Path(args.index_dir).expanduser().resolve() if args.index_dir else skill_dir / ".skill-index"
    metadata_path = index_dir / "deep" / "metadata.json"
    version_path = skill_dir / "VERSION"
    result = {
        "status": "needs-attention",
        "version": version_path.read_text(encoding="utf-8-sig").strip() if version_path.exists() else "development",
        "skill_dir": str(skill_dir),
        "index_dir": str(index_dir),
        "deep_index_exists": metadata_path.exists(),
    }
    if not metadata_path.exists():
        result["reason"] = "Deep index is missing. Run recommend-skills.py once or reinstall without --skip-scan."
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1
    metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
    command = [
        sys.executable,
        str(script_dir / "recommend-skills.py"),
        "--query",
        "health check local skill routing",
        "--index-dir",
        str(index_dir),
        "--compact",
    ]
    checked = subprocess.run(command, text=True, capture_output=True, check=False)
    result.update({
        "raw_files": int(metadata.get("raw_files") or 0),
        "classified_files": int(metadata.get("classified_files") or 0),
        "failed_files": int(metadata.get("failed_files") or 0),
        "skills_roots": metadata.get("skills_roots", []),
        "recommendation_exit_code": checked.returncode,
    })
    if checked.returncode == 0:
        recommendation = json.loads(checked.stdout)
        result["recommendation_mode"] = recommendation.get("mode", "")
        result["status"] = "degraded" if result["failed_files"] else "ok"
    else:
        result["reason"] = (checked.stderr or checked.stdout).strip()[-1000:]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"ok", "degraded"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
