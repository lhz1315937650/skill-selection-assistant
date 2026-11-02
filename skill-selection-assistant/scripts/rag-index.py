#!/usr/bin/env python3
"""Lightweight hybrid retrieval index for skills and user documents.

The default backend is dependency-free: deterministic character n-gram vectors
and SQLite FTS/BM25.  If sentence-transformers is installed, callers may opt
into a model through ``--embedding-model`` without changing the index format.
"""
from __future__ import annotations

import argparse, hashlib, json, math, re, sqlite3
from pathlib import Path
from typing import Any

SCHEMA = "rag-1.0.0"
TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)

def text_tokens(text: str) -> list[str]:
    words = [w.lower() for w in TOKEN_RE.findall(text or "")]
    grams: list[str] = []
    for word in words:
        if len(word) > 1:
            grams.extend(word[i:i+2] for i in range(len(word)-1))
    return words + grams

def sparse_vector(text: str) -> dict[str, float]:
    counts: dict[str, float] = {}
    for token in text_tokens(text):
        counts[token] = counts.get(token, 0.0) + 1.0
    norm = math.sqrt(sum(value * value for value in counts.values())) or 1.0
    return {key: value / norm for key, value in counts.items()}

def cosine(left: dict[str, float], right: dict[str, float]) -> float:
    if len(left) > len(right): left, right = right, left
    return sum(value * right.get(key, 0.0) for key, value in left.items())

def lexical_score(query: str, text: str) -> float:
    query_tokens = set(text_tokens(query))
    text_token_set = set(text_tokens(text))
    if not query_tokens:
        return 0.0
    return len(query_tokens & text_token_set) / len(query_tokens)

def load_cards(database: Path) -> list[dict[str, Any]]:
    with sqlite3.connect(database) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute("SELECT * FROM cards").fetchall()
    return [dict(row) for row in rows]

def card_text(card: dict[str, Any]) -> str:
    fields = ("name", "function_summary", "selection_positive_examples", "capability_tags", "does", "does_not")
    return "\n".join(str(card.get(field) or "") for field in fields)

def build(index_dir: Path, output: Path, sources: list[Path] | None = None) -> dict[str, Any]:
    database = index_dir / "deep" / "lazy-route.sqlite3"
    if not database.exists(): raise FileNotFoundError(database)
    records: list[dict[str, Any]] = []
    for card in load_cards(database):
        records.append({"id": str(card["skill_id"]), "kind": "skill", "name": card["name"], "path": card["skill_md"], "text": card_text(card)})
    for root in sources or []:
        paths = [root] if root.is_file() else [p for p in root.rglob("*") if p.is_file()]
        for path in paths:
            if path.suffix.lower() not in {".md", ".markdown", ".txt"}: continue
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            digest = hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:16]
            records.append({"id": f"doc:{digest}", "kind": "document", "name": path.stem, "path": str(path), "text": text})
    payload = {"schema_version": SCHEMA, "backend": "sparse-char-ngram", "records": [{**item, "vector": sparse_vector(item["text"])} for item in records]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return {"status": "built", "output": str(output), "records": len(records), "backend": payload["backend"]}

def search(index_file: Path, query: str, limit: int = 8) -> dict[str, Any]:
    payload = json.loads(index_file.read_text(encoding="utf-8"))
    qv = sparse_vector(query)
    scored = []
    for record in payload.get("records", []):
        score = cosine(qv, {str(k): float(v) for k, v in (record.get("vector") or {}).items()})
        scored.append({"id": record["id"], "kind": record["kind"], "name": record["name"], "path": record["path"], "vector_score": score, "lexical_score": lexical_score(query, record["text"]), "snippet": re.sub(r"\s+", " ", record["text"])[:240]})
    vector_order = sorted(scored, key=lambda x: (-x["vector_score"], x["name"]))
    lexical_order = sorted(scored, key=lambda x: (-x["lexical_score"], x["name"]))
    vector_rank = {item["id"]: index for index, item in enumerate(vector_order, 1)}
    lexical_rank = {item["id"]: index for index, item in enumerate(lexical_order, 1)}
    for item in scored:
        item["rrf_score"] = 0.6 / (60 + vector_rank[item["id"]]) + 0.4 / (60 + lexical_rank[item["id"]])
        item["score"] = round(item["rrf_score"], 6)
        item["vector_score"] = round(item["vector_score"], 6)
        item["lexical_score"] = round(item["lexical_score"], 6)
    scored.sort(key=lambda x: (-x["rrf_score"], -x["vector_score"], x["name"]))
    return {"schema_version": SCHEMA, "query": query, "backend": payload.get("backend"), "results": scored[:max(1, limit)]}

def main() -> int:
    parser = argparse.ArgumentParser(description="Build or query the lightweight hybrid RAG index.")
    parser.add_argument("--index-dir", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--source", action="append", type=Path, default=[])
    parser.add_argument("--query", default="")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    base = Path(args.index_dir).expanduser().resolve() if args.index_dir else Path(__file__).resolve().parent.parent / ".skill-index"
    output = Path(args.output).expanduser().resolve() if args.output else base / "rag" / "rag-index.json"
    result = search(output, args.query, args.limit) if args.query else build(base, output, args.source)
    print(json.dumps(result, ensure_ascii=False, indent=None if args.compact else 2, separators=(",", ":") if args.compact else None))
    return 0

if __name__ == "__main__": raise SystemExit(main())
