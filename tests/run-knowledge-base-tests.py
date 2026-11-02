#!/usr/bin/env python3
"""Focused acceptance tests for the P0-P2 knowledge-base additions."""
from __future__ import annotations
import json, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skill-selection-assistant"
FIXTURES = ROOT / "tests" / "fixtures" / "skills"

def run(*args: str) -> dict:
    result = subprocess.run([sys.executable, *args], cwd=ROOT, text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(f"failed: {args}\nstdout={result.stdout}\nstderr={result.stderr}")
    return json.loads(result.stdout)

def main() -> int:
    with tempfile.TemporaryDirectory(prefix="knowledge-base-tests-") as folder:
        base = Path(folder); index = base / "index"
        run(str(SKILL_DIR / "scripts" / "deep-classify-skills.py"), "--skills-root", str(FIXTURES), "--skill-dir", str(SKILL_DIR), "--index-dir", str(index), "--full-rebuild")
        rag = run(str(SKILL_DIR / "scripts" / "rag-index.py"), "--index-dir", str(index), "--output", str(base / "rag.json"))
        assert rag["records"] > 0 and rag["backend"] == "sparse-char-ngram"
        result = run(str(SKILL_DIR / "scripts" / "rag-index.py"), "--output", str(base / "rag.json"), "--query", "frontend dashboard")
        assert result["results"][0]["name"] == "frontend-design"
        doc = base / "notes.md"; doc.write_text("# User notes\nA custom knowledge source.", encoding="utf-8")
        bundle = run(str(SKILL_DIR / "scripts" / "document-ingest.py"), "--source", str(doc), "--output", str(base / "documents.json"))
        assert bundle["records"] == 1
        wiki = run(str(SKILL_DIR / "scripts" / "wiki-generate.py"), "--index-dir", str(index), "--output-dir", str(base / "wiki"))
        assert wiki["pages"] > 0 and (base / "wiki" / "index.html").exists()
        evaluation = run(str(SKILL_DIR / "scripts" / "evaluate-retrieval.py"), "--dataset", str(ROOT / "tests" / "fixtures" / "retrieval-eval.json"), "--index", str(base / "rag.json"))
        assert evaluation["queries"] == 30 and evaluation["hit_rate_at_5"] >= 0.60
    print(json.dumps({"status": "passed", "features": ["document-ingest", "rag-index", "wiki-generate", "evaluate-retrieval"]}, ensure_ascii=False))
    return 0

if __name__ == "__main__": raise SystemExit(main())
