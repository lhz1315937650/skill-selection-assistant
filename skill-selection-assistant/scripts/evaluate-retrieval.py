#!/usr/bin/env python3
"""Evaluate RAG retrieval with a small JSONL/JSON labelled query set."""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate retrieval using {query, relevant} records.")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    raw = json.loads(args.dataset.read_text(encoding="utf-8-sig"))
    cases = raw.get("queries", raw) if isinstance(raw, dict) else raw
    total = hits = 0; reciprocal = 0.0; details = []
    for case in cases:
        query = str(case.get("query") or ""); relevant = {str(x).lower() for x in (case.get("relevant") or [])}
        proc = subprocess.run([sys.executable, str(Path(__file__).with_name("rag-index.py")), "--output", str(args.index), "--query", query, "--limit", str(args.limit), "--compact"], text=True, capture_output=True)
        if proc.returncode: raise RuntimeError(proc.stderr or proc.stdout)
        results = json.loads(proc.stdout).get("results") or []
        rank = next((i + 1 for i, item in enumerate(results) if str(item.get("name") or "").lower() in relevant or str(item.get("id") or "").lower() in relevant), 0)
        total += 1
        if rank: hits += 1; reciprocal += 1.0 / rank
        details.append({"query": query, "rank": rank, "top": [item.get("name") for item in results]})
    result = {"status": "ok", "queries": total, "hit_rate_at_5": hits / total if total else 0.0, "mrr_at_5": reciprocal / total if total else 0.0, "details": details}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
if __name__ == "__main__": raise SystemExit(main())
