#!/usr/bin/env python3
"""Normalize user-owned Markdown/text/PDF/DOCX sources for the RAG layer."""
from __future__ import annotations
import argparse, json, re, zipfile
from pathlib import Path

def read_doc(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown", ".txt"}:
        return path.read_text(encoding="utf-8-sig", errors="replace"), "native"
    if suffix == ".docx":
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml").decode("utf-8", "replace")
        return re.sub(r"<[^>]+>", " ", xml).replace("&amp;", "&"), "docx-stdlib"
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader  # type: ignore
        except ImportError:
            return "", "unsupported: install pypdf to ingest PDF"
        reader = PdfReader(str(path))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages), "pypdf"
    return "", f"unsupported extension: {suffix}"

def ingest(source: Path, output: Path) -> dict[str, object]:
    paths = [source] if source.is_file() else [p for p in source.rglob("*") if p.is_file()]
    records = []; skipped = []
    for path in paths:
        text, parser = read_doc(path)
        if not text:
            skipped.append({"path": str(path), "reason": parser}); continue
        records.append({"source": str(path.resolve()), "name": path.stem, "text": text, "parser": parser})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"schema_version": "documents-1.0.0", "records": records, "skipped": skipped}, ensure_ascii=False), encoding="utf-8")
    return {"status": "ok", "output": str(output), "records": len(records), "skipped": len(skipped)}

def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest user documents into a normalized JSON source bundle.")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    print(json.dumps(ingest(args.source, args.output), ensure_ascii=False, indent=None if args.compact else 2, separators=(",", ":") if args.compact else None))
    return 0
if __name__ == "__main__": raise SystemExit(main())
