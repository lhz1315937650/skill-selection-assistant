#!/usr/bin/env python3
"""Build and maintain the SQLite lazy-routing index from portable JSON artifacts."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0.0"
SOURCE_FILES = ("facets.json", "route-cards.json")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def source_signature(deep_dir: Path) -> str:
    parts = []
    for name in SOURCE_FILES:
        path = deep_dir / name
        stat = path.stat()
        parts.append(f"{name}:{stat.st_size}:{stat.st_mtime_ns}")
    return "|".join(parts)


def database_is_current(database: Path, signature: str) -> bool:
    if not database.exists():
        return False
    try:
        with sqlite3.connect(database) as connection:
            values = dict(connection.execute("SELECT key, value FROM metadata"))
        return values.get("schema_version") == SCHEMA_VERSION and values.get("source_signature") == signature
    except (OSError, sqlite3.Error):
        return False


def build_database(deep_dir: Path, database: Path) -> dict[str, Any]:
    signature = source_signature(deep_dir)
    if database_is_current(database, signature):
        return {"status": "current", "database": str(database), "source_signature": signature}

    facets = load_json(deep_dir / "facets.json")
    cards = load_json(deep_dir / "route-cards.json")
    temp = database.with_name(f"{database.name}.build-{os.getpid()}")
    try:
        temp.unlink()
    except FileNotFoundError:
        pass
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(temp)
    try:
        connection.executescript("""
            PRAGMA journal_mode=OFF;
            PRAGMA synchronous=OFF;
            PRAGMA temp_store=MEMORY;
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE levels (position INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
            CREATE TABLE cards (
                skill_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                canonical_name TEXT NOT NULL,
                function_summary TEXT NOT NULL,
                capability_tags TEXT NOT NULL,
                setup_level TEXT NOT NULL,
                setup_requirements TEXT NOT NULL,
                origin TEXT NOT NULL,
                skill_md TEXT NOT NULL,
                logical_skill_md TEXT NOT NULL,
                exact_duplicate_count INTEGER NOT NULL,
                variant_count INTEGER NOT NULL
            );
            CREATE TABLE facet_memberships (
                level TEXT NOT NULL,
                label TEXT NOT NULL,
                skill_id TEXT NOT NULL,
                PRIMARY KEY (level, label, skill_id)
            ) WITHOUT ROWID;
            CREATE INDEX facet_skill_level ON facet_memberships(skill_id, level, label);
            CREATE INDEX cards_canonical_name ON cards(canonical_name);
        """)
        connection.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", [
            ("schema_version", SCHEMA_VERSION),
            ("source_signature", signature),
            ("skill_count", str(len(cards))),
        ])
        connection.executemany(
            "INSERT INTO levels(position, name) VALUES (?, ?)",
            enumerate(facets.get("levels", [])),
        )
        connection.executemany(
            """INSERT INTO cards VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    skill_id,
                    str(card.get("name") or ""),
                    str(card.get("canonical_name") or card.get("name") or ""),
                    str(card.get("function_summary") or ""),
                    json.dumps(card.get("capability_tags") or [], ensure_ascii=False, separators=(",", ":")),
                    str(card.get("setup_level") or "unknown"),
                    json.dumps(card.get("setup_requirements") or [card.get("setup_level") or "unknown"], ensure_ascii=False, separators=(",", ":")),
                    str(card.get("origin") or "unknown"),
                    str(card.get("skill_md") or ""),
                    str(card.get("logical_skill_md") or card.get("skill_md") or ""),
                    int(card.get("exact_duplicate_count") or 1),
                    int(card.get("variant_count") or 1),
                )
                for skill_id, card in cards.items()
            ],
        )
        memberships = (
            (level, label, skill_id)
            for level, labels in facets.get("facets", {}).items()
            for label, skill_ids in labels.items()
            for skill_id in skill_ids
        )
        connection.executemany(
            "INSERT INTO facet_memberships(level, label, skill_id) VALUES (?, ?, ?)",
            memberships,
        )
        connection.commit()
    finally:
        connection.close()
    os.replace(temp, database)
    return {"status": "built", "database": str(database), "source_signature": signature, "skills": len(cards)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the SQLite lazy-routing index from deep JSON artifacts.")
    parser.add_argument("--index-dir", default="")
    parser.add_argument("--database", default="")
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    script_dir = Path(__file__).resolve().parent
    index_dir = Path(args.index_dir).expanduser().resolve() if args.index_dir else script_dir.parent / ".skill-index"
    deep_dir = index_dir / "deep"
    database = Path(args.database).expanduser().resolve() if args.database else deep_dir / "lazy-route.sqlite3"
    result = build_database(deep_dir, database)
    print(json.dumps(result, ensure_ascii=False, indent=None if args.compact else 2, separators=(",", ":") if args.compact else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
