#!/usr/bin/env python3
"""Build and maintain the SQLite lazy-routing index from portable JSON artifacts."""

from __future__ import annotations

import argparse
import json
import re
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.5.0"
SOURCE_FILES = ("facets.json", "route-cards.json")
OVERLAY_FILE = "tag-overlay.json"
DEFAULT_WEIGHT = 100
SKIP_DIR_NAMES = {".git", ".hg", ".svn", "node_modules", "__pycache__", ".skill-index"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))

def json_list(value: Any) -> str:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                value = parsed
        except json.JSONDecodeError:
            value = [value]
    return json.dumps(list(value or []), ensure_ascii=False, separators=(",", ":"))


def parse_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not value:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            return [value]
    return []


def alias_tokens(*texts: str) -> list[str]:
    found: list[str] = []
    for text in texts:
        for token in re.findall("[a-zA-Z][a-zA-Z0-9]{1,}|" + "[一-鿿]{2,}", str(text or "").lower()):
            if len(token) >= 2 and token not in found:
                found.append(token)
    return found


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
        schema = str(values.get("schema_version") or "")
        if schema == SCHEMA_VERSION:
            return True
        return schema == "1.3.0" and values.get("source_signature") == signature
    except (OSError, sqlite3.Error):
        return False


def card_row(skill_id: str, card: dict[str, Any]) -> tuple[Any, ...]:
    return (
        skill_id,
        str(card.get("name") or ""),
        str(card.get("canonical_name") or card.get("name") or ""),
        str(card.get("function_summary") or ""),
        json.dumps(card.get("selection_positive_examples") or [], ensure_ascii=False, separators=(",", ":")),
        json.dumps(card.get("selection_negative_examples") or [], ensure_ascii=False, separators=(",", ":")),
        json.dumps(card.get("capability_tags") or [], ensure_ascii=False, separators=(",", ":")),
        str(card.get("setup_level") or "unknown"),
        json.dumps(card.get("setup_requirements") or [card.get("setup_level") or "unknown"], ensure_ascii=False, separators=(",", ":")),
        str(card.get("origin") or "unknown"),
        str(card.get("skill_md") or ""),
        str(card.get("logical_skill_md") or card.get("skill_md") or ""),
        int(card.get("exact_duplicate_count") or 1),
        int(card.get("variant_count") or 1),
        str(card.get("function_purpose") or card.get("function_summary") or ""),
        int(card.get("function_weight") or DEFAULT_WEIGHT),
        json.dumps(card.get("aliases") or [], ensure_ascii=False, separators=(",", ":")),
        json_list(card.get("does") or card.get("selection_positive_examples") or []),
        json_list(card.get("does_not") or card.get("selection_negative_examples") or []),
    )


def fts_row(skill_id: str, card: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        skill_id,
        str(card.get("name") or ""),
        str(card.get("function_summary") or "") + " " + str(card.get("function_purpose") or ""),
        " ".join(str(value) for value in (card.get("selection_positive_examples") or []) + (card.get("does") or [])),
        " ".join(str(tag) for tag in list(card.get("capability_tags") or []) + list(card.get("aliases") or [])),
    )


def build_database(deep_dir: Path, database: Path) -> dict[str, Any]:
    signature = source_signature(deep_dir)
    if database_is_current(database, signature):
        return {"status": "current", "database": str(database), "source_signature": signature}

    facets = load_json(deep_dir / "facets.json")
    cards = load_json(deep_dir / "route-cards.json")
    overlay_path = deep_dir / OVERLAY_FILE
    overlay = load_json(overlay_path) if overlay_path.exists() else {}
    overlay_rules = {
        **(overlay.get("domain_detail_rules") or {}),
        **(overlay.get("specialty_rules") or {}),
        **(overlay.get("task_type_rules") or {}),
    }
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
                selection_positive_examples TEXT NOT NULL,
                selection_negative_examples TEXT NOT NULL,
                capability_tags TEXT NOT NULL,
                setup_level TEXT NOT NULL,
                setup_requirements TEXT NOT NULL,
                origin TEXT NOT NULL,
                skill_md TEXT NOT NULL,
                logical_skill_md TEXT NOT NULL,
                exact_duplicate_count INTEGER NOT NULL,
                variant_count INTEGER NOT NULL,
                function_purpose TEXT NOT NULL,
                function_weight INTEGER NOT NULL,
                aliases TEXT NOT NULL,
                does TEXT NOT NULL,
                does_not TEXT NOT NULL
            );
            CREATE TABLE facet_memberships (
                level TEXT NOT NULL,
                label TEXT NOT NULL,
                skill_id TEXT NOT NULL,
                PRIMARY KEY (level, label, skill_id)
            ) WITHOUT ROWID;
            CREATE TABLE tags (
                level TEXT NOT NULL,
                label TEXT NOT NULL,
                origin TEXT NOT NULL,
                keywords TEXT NOT NULL,
                aliases TEXT NOT NULL,
                weight INTEGER NOT NULL,
                canonical_label TEXT NOT NULL,
                PRIMARY KEY (level, label)
            ) WITHOUT ROWID;
            CREATE TABLE tag_aliases (
                alias TEXT NOT NULL,
                level TEXT NOT NULL,
                label TEXT NOT NULL,
                PRIMARY KEY (alias, level, label)
            ) WITHOUT ROWID;
            CREATE INDEX tag_aliases_lookup ON tag_aliases(alias);
            CREATE INDEX facet_skill_level ON facet_memberships(skill_id, level, label);
            CREATE INDEX cards_canonical_name ON cards(canonical_name);
            CREATE VIRTUAL TABLE cards_fts USING fts5(
                skill_id UNINDEXED,
                name,
                function_summary,
                positive_examples,
                capability_tags,
                tokenize = 'unicode61 remove_diacritics 2'
            );
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
            "INSERT INTO cards VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [card_row(skill_id, card) for skill_id, card in cards.items()],
        )
        connection.executemany(
            "INSERT INTO cards_fts(skill_id, name, function_summary, positive_examples, capability_tags) VALUES (?, ?, ?, ?, ?)",
            [
                (
                    skill_id,
                    str(card.get("name") or ""),
                    str(card.get("function_summary") or ""),
                    " ".join(str(value) for value in (card.get("selection_positive_examples") or [])),
                    " ".join(str(tag) for tag in (card.get("capability_tags") or [])),
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
        tag_rows = [
            (
                level,
                label,
                "overlay" if label in overlay_rules else "seeded",
                str(overlay_rules.get(label) or ""),
                "[]",
                DEFAULT_WEIGHT,
                label,
            )
            for level, labels in facets.get("facets", {}).items()
            for label in labels
        ]
        connection.executemany(
            "INSERT INTO tags(level, label, origin, keywords, aliases, weight, canonical_label) VALUES (?, ?, ?, ?, ?, ?, ?)",
            tag_rows,
        )
        rebuild_tag_aliases(connection)
        connection.commit()
    finally:
        connection.close()
    os.replace(temp, database)
    return {"status": "built", "database": str(database), "source_signature": signature, "skills": len(cards)}


def table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def set_metadata(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        "INSERT INTO metadata(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def migrate_database(database: Path) -> dict[str, Any]:
    connection = sqlite3.connect(database)
    try:
        tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "cards" not in tables:
            raise sqlite3.DatabaseError("cards table missing")
        if "tags" not in tables:
            connection.execute(
                """CREATE TABLE tags (
                    level TEXT NOT NULL,
                    label TEXT NOT NULL,
                    origin TEXT NOT NULL,
                    keywords TEXT NOT NULL,
                    aliases TEXT NOT NULL DEFAULT '[]',
                    weight INTEGER NOT NULL DEFAULT 100,
                    canonical_label TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (level, label)
                ) WITHOUT ROWID"""
            )
        card_cols = table_columns(connection, "cards")
        for name, definition in (
            ("function_purpose", "TEXT NOT NULL DEFAULT ''"),
            ("function_weight", "INTEGER NOT NULL DEFAULT 100"),
            ("aliases", "TEXT NOT NULL DEFAULT '[]'"),
            ("does", "TEXT NOT NULL DEFAULT '[]'"),
            ("does_not", "TEXT NOT NULL DEFAULT '[]'"),
        ):
            if name not in card_cols:
                connection.execute(f"ALTER TABLE cards ADD COLUMN {name} {definition}")
        if "tag_aliases" not in tables:
            connection.execute(
                """CREATE TABLE tag_aliases (
                    alias TEXT NOT NULL,
                    level TEXT NOT NULL,
                    label TEXT NOT NULL,
                    PRIMARY KEY (alias, level, label)
                ) WITHOUT ROWID"""
            )
            connection.execute("CREATE INDEX IF NOT EXISTS tag_aliases_lookup ON tag_aliases(alias)")
        tag_cols = table_columns(connection, "tags")
        for name, definition in (
            ("aliases", "TEXT NOT NULL DEFAULT '[]'"),
            ("weight", "INTEGER NOT NULL DEFAULT 100"),
            ("canonical_label", "TEXT NOT NULL DEFAULT ''"),
        ):
            if name not in tag_cols:
                connection.execute(f"ALTER TABLE tags ADD COLUMN {name} {definition}")
        connection.execute("UPDATE tags SET canonical_label = label WHERE canonical_label IS NULL OR canonical_label = ''")
        rebuild_tag_aliases(connection)
        set_metadata(connection, "schema_version", SCHEMA_VERSION)
        set_metadata(connection, "source_signature", "sqlite-source-of-truth")
        skill_count = int(connection.execute("SELECT COUNT(*) FROM cards").fetchone()[0])
        set_metadata(connection, "skill_count", str(skill_count))
        connection.commit()
    finally:
        connection.close()
    return {"status": "migrated", "database": str(database), "schema_version": SCHEMA_VERSION, "skills": skill_count}


def ensure_database(deep_dir: Path, database: Path) -> dict[str, Any]:
    if database.exists():
        try:
            return migrate_database(database)
        except (OSError, sqlite3.Error):
            pass
    return build_database(deep_dir, database)


def list_tags(database: Path) -> list[dict[str, Any]]:
    if not database.exists():
        return []
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        if "tags" not in {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
            return []
        rows = connection.execute("SELECT level, label, origin, keywords, aliases, weight, canonical_label FROM tags")
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["aliases"] = json.loads(item.get("aliases") or "[]")
            except json.JSONDecodeError:
                item["aliases"] = []
            result.append(item)
        return result
    finally:
        connection.close()



def tag_alias_values(label: str, keywords: str, aliases: Any) -> list[str]:
    values = alias_tokens(label, keywords, " ".join(str(item) for item in parse_json_list(aliases)))
    if label and label.lower() not in values:
        values.append(label.lower())
    return values


def rebuild_tag_aliases(connection: sqlite3.Connection) -> None:
    tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "tag_aliases" not in tables:
        connection.execute(
            """CREATE TABLE tag_aliases (
                alias TEXT NOT NULL,
                level TEXT NOT NULL,
                label TEXT NOT NULL,
                PRIMARY KEY (alias, level, label)
            ) WITHOUT ROWID"""
        )
        connection.execute("CREATE INDEX IF NOT EXISTS tag_aliases_lookup ON tag_aliases(alias)")
    connection.execute("DELETE FROM tag_aliases")
    rows = []
    for level, label, keywords, aliases in connection.execute("SELECT level, label, keywords, aliases FROM tags"):
        for alias in tag_alias_values(str(label), str(keywords or ""), aliases):
            rows.append((alias, str(level), str(label)))
    if rows:
        connection.executemany("INSERT OR REPLACE INTO tag_aliases(alias, level, label) VALUES (?, ?, ?)", rows)


def gc_orphan_tags(connection: sqlite3.Connection) -> int:
    before = int(connection.execute("SELECT COUNT(*) FROM tags").fetchone()[0])
    connection.execute(
        """DELETE FROM tags
           WHERE NOT EXISTS (
               SELECT 1 FROM facet_memberships fm
               WHERE fm.level = tags.level AND fm.label = tags.label
           )"""
    )
    removed = before - int(connection.execute("SELECT COUNT(*) FROM tags").fetchone()[0])
    rebuild_tag_aliases(connection)
    return removed


def walk_skill_md_paths(root: Path, max_depth: int = 6) -> list[Path]:
    found: list[Path] = []

    def walk(current: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = list(os.scandir(current))
        except OSError:
            return
        skill = None
        dirs: list[Path] = []
        for entry in entries:
            name = entry.name
            if name.startswith(".") or name in SKIP_DIR_NAMES:
                continue
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
                is_file = entry.is_file(follow_symlinks=False)
            except OSError:
                continue
            if is_file and name.lower() == "skill.md":
                skill = Path(entry.path)
            elif is_dir:
                dirs.append(Path(entry.path))
        if skill is not None:
            found.append(skill)
            return
        for child in dirs:
            walk(child, depth + 1)

    walk(Path(root), 0)
    return found


def list_pending_skills(database: Path, skills_roots: list[str] | list[Path]) -> dict[str, Any]:
    indexed: set[str] = set()
    if database.exists():
        migrate_database(database)
        connection = sqlite3.connect(database)
        try:
            for skill_md, logical in connection.execute("SELECT skill_md, logical_skill_md FROM cards"):
                for value in (skill_md, logical):
                    if value:
                        indexed.add(os.path.normcase(str(Path(str(value)))))
        finally:
            connection.close()
    pending = []
    scanned_dirs = 0
    for root_value in skills_roots:
        root = Path(root_value).expanduser().resolve()
        if not root.is_dir():
            continue
        scanned_dirs += 1
        for path in walk_skill_md_paths(root):
            key = os.path.normcase(str(path))
            logical = os.path.normcase(str(path.absolute()))
            if key in indexed or logical in indexed:
                continue
            pending.append({
                "name": path.parent.name,
                "skill_md": str(path),
                "status": "pending",
            })
    return {
        "status": "ok",
        "mode": "list_pending",
        "full_library_scan": False,
        "read_skill_bodies": False,
        "scanned_directories": scanned_dirs,
        "pending_count": len(pending),
        "pending": pending,
    }


def upsert_skill(
    database: Path,
    deep_dir: Path,
    card: dict[str, Any],
    memberships: list[tuple[str, str, str]],
    created_tags: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Insert or replace one skill card and its tags without rebuilding the library."""
    if not database.exists():
        built = build_database(deep_dir, database)
        if not database.exists():
            return built
    migrate_database(database)

    skill_id = str(card.get("skill_id") or "")
    if not skill_id:
        raise ValueError("Cannot upsert a skill card without skill_id")

    connection = sqlite3.connect(database)
    try:
        connection.execute(
            """INSERT INTO cards VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(skill_id) DO UPDATE SET
                    name=excluded.name,
                    canonical_name=excluded.canonical_name,
                    function_summary=excluded.function_summary,
                    selection_positive_examples=excluded.selection_positive_examples,
                    selection_negative_examples=excluded.selection_negative_examples,
                    capability_tags=excluded.capability_tags,
                    setup_level=excluded.setup_level,
                    setup_requirements=excluded.setup_requirements,
                    origin=excluded.origin,
                    skill_md=excluded.skill_md,
                    logical_skill_md=excluded.logical_skill_md,
                    exact_duplicate_count=excluded.exact_duplicate_count,
                    variant_count=excluded.variant_count,
                    function_purpose=excluded.function_purpose,
                    function_weight=excluded.function_weight,
                    aliases=excluded.aliases,
                    does=excluded.does,
                    does_not=excluded.does_not""",
            card_row(skill_id, card),
        )
        connection.execute("DELETE FROM cards_fts WHERE skill_id = ?", (skill_id,))
        connection.execute(
            "INSERT INTO cards_fts(skill_id, name, function_summary, positive_examples, capability_tags) VALUES (?, ?, ?, ?, ?)",
            fts_row(skill_id, card),
        )
        connection.execute("DELETE FROM facet_memberships WHERE skill_id = ?", (skill_id,))
        connection.executemany(
            "INSERT OR REPLACE INTO facet_memberships(level, label, skill_id) VALUES (?, ?, ?)",
            memberships,
        )
        for tag in created_tags or []:
            aliases = tag.get("aliases") or []
            if isinstance(aliases, str):
                alias_json = aliases
            else:
                alias_json = json.dumps(aliases, ensure_ascii=False, separators=(",", ":"))
            connection.execute(
                """INSERT INTO tags(level, label, origin, keywords, aliases, weight, canonical_label)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(level, label) DO UPDATE SET
                        origin=excluded.origin,
                        keywords=excluded.keywords,
                        aliases=excluded.aliases,
                        canonical_label=excluded.canonical_label""",
                (
                    tag["level"],
                    tag["label"],
                    tag.get("origin") or "overlay",
                    tag.get("keywords") or "",
                    alias_json,
                    int(tag.get("weight") or DEFAULT_WEIGHT),
                    tag.get("canonical_label") or tag["label"],
                ),
            )
        rebuild_tag_aliases(connection)
        skill_count = int(connection.execute("SELECT COUNT(*) FROM cards").fetchone()[0])
        set_metadata(connection, "schema_version", SCHEMA_VERSION)
        set_metadata(connection, "source_signature", "sqlite-source-of-truth")
        set_metadata(connection, "skill_count", str(skill_count))
        connection.commit()
    finally:
        connection.close()
    return {"status": "upserted", "database": str(database), "skill_id": skill_id, "skills": skill_count}


def delete_skill(database: Path, skill_md: str = "", skill_id: str = "") -> dict[str, Any]:
    if not database.exists():
        raise FileNotFoundError(f"SQLite index does not exist: {database}")
    migrate_database(database)
    connection = sqlite3.connect(database)
    try:
        row = None
        if skill_id:
            row = connection.execute("SELECT skill_id, name, skill_md FROM cards WHERE skill_id = ?", (skill_id,)).fetchone()
        if row is None and skill_md:
            row = connection.execute(
                "SELECT skill_id, name, skill_md FROM cards WHERE LOWER(skill_md) = LOWER(?) OR LOWER(logical_skill_md) = LOWER(?)",
                (skill_md, skill_md),
            ).fetchone()
        if row is None:
            return {"status": "missing", "database": str(database), "skill_md": skill_md, "skill_id": skill_id}
        skill_id = str(row[0])
        connection.execute("DELETE FROM cards_fts WHERE skill_id = ?", (skill_id,))
        connection.execute("DELETE FROM facet_memberships WHERE skill_id = ?", (skill_id,))
        connection.execute("DELETE FROM cards WHERE skill_id = ?", (skill_id,))
        removed_tags = gc_orphan_tags(connection)
        skill_count = int(connection.execute("SELECT COUNT(*) FROM cards").fetchone()[0])
        set_metadata(connection, "skill_count", str(skill_count))
        set_metadata(connection, "source_signature", "sqlite-source-of-truth")
        connection.commit()
    finally:
        connection.close()
    return {"status": "deleted", "database": str(database), "skill_id": skill_id, "name": str(row[1]), "skill_md": str(row[2]), "skills": skill_count, "removed_tags": removed_tags}


def apply_feedback(database: Path, selected_skill: str, outcome: str, skill_id: str = "", matched_tags: list[str] | None = None) -> dict[str, Any]:
    if not database.exists() or not (selected_skill or skill_id):
        return {"status": "skipped"}
    migrate_database(database)
    delta = {"selected": 8, "rejected": -6, "missed": 0, "setup-failed": -2}.get(outcome, 0)
    tag_delta = 4 if outcome == "selected" else (-2 if outcome in {"rejected", "setup-failed"} else 0)
    connection = sqlite3.connect(database)
    try:
        row = None
        if skill_id:
            row = connection.execute(
                "SELECT skill_id, function_weight, name FROM cards WHERE skill_id = ? LIMIT 1",
                (skill_id,),
            ).fetchone()
        if row is None and selected_skill:
            row = connection.execute(
                "SELECT skill_id, function_weight, name FROM cards WHERE canonical_name = ? OR name = ? LIMIT 1",
                (selected_skill.lower(), selected_skill),
            ).fetchone()
        if row is None and selected_skill:
            row = connection.execute(
                "SELECT skill_id, function_weight, name FROM cards WHERE LOWER(canonical_name) = LOWER(?) OR LOWER(name) = LOWER(?) LIMIT 1",
                (selected_skill, selected_skill),
            ).fetchone()
        if row is None:
            return {"status": "missing", "selected_skill": selected_skill, "skill_id": skill_id}
        skill_id, current = str(row[0]), int(row[1] or DEFAULT_WEIGHT)
        selected_name = str(row[2] or selected_skill)
        updated = max(40, min(200, current + delta))
        connection.execute("UPDATE cards SET function_weight = ? WHERE skill_id = ?", (updated, skill_id))
        if tag_delta:
            useful_tags = [str(tag) for tag in (matched_tags or []) if str(tag).strip()]
            if useful_tags:
                placeholders = ",".join("?" for _ in useful_tags)
                connection.execute(
                    f"UPDATE tags SET weight = MIN(200, MAX(40, weight + ?)) WHERE label IN ({placeholders})",
                    [tag_delta, *useful_tags],
                )
            else:
                connection.execute(
                    """UPDATE tags SET weight = MIN(200, MAX(40, weight + ?))
                       WHERE (level, label) IN (
                           SELECT level, label FROM facet_memberships WHERE skill_id = ?
                       )""",
                    (tag_delta, skill_id),
                )
        connection.commit()
    finally:
        connection.close()
    return {"status": "updated", "selected_skill": selected_name, "skill_id": skill_id, "function_weight": updated, "outcome": outcome}


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
    result = ensure_database(deep_dir, database)
    print(json.dumps(result, ensure_ascii=False, indent=None if args.compact else 2, separators=(",", ":") if args.compact else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
