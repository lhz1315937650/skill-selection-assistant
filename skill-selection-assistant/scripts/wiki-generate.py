#!/usr/bin/env python3
"""Generate an offline, searchable HTML knowledge base from the SQLite index."""
from __future__ import annotations
import argparse, html, json, sqlite3
from pathlib import Path

def esc(value: object) -> str: return html.escape(str(value or ""))

def generate(index_dir: Path, output: Path) -> dict[str, object]:
    database = index_dir / "deep" / "lazy-route.sqlite3"
    if not database.exists(): raise FileNotFoundError(database)
    with sqlite3.connect(database) as db:
        db.row_factory = sqlite3.Row
        cards = [dict(row) for row in db.execute("SELECT * FROM cards ORDER BY name COLLATE NOCASE")]
        memberships = db.execute("SELECT skill_id, level, label FROM facet_memberships ORDER BY level, label").fetchall()
    by_skill: dict[str, list[str]] = {}
    for row in memberships: by_skill.setdefault(str(row[0]), []).append(f"{row[1]}: {row[2]}")
    output.mkdir(parents=True, exist_ok=True)
    pages = []
    for card in cards:
        slug = str(card["skill_id"]).replace("/", "-")
        tags = by_skill.get(str(card["skill_id"]), [])
        body = """
<!doctype html><meta charset="utf-8"><title>{title}</title>
<style>body{{font:16px system-ui;max-width:900px;margin:40px auto;padding:0 20px;line-height:1.55}}code{{background:#f3f3f3;padding:2px 4px}}a{{color:#1459a6}}</style>
<p><a href="index.html">← Skill index</a></p><h1>{title}</h1>
<p>{summary}</p><h2>Capabilities</h2><p>{does}</p><h2>Limitations</h2><p>{does_not}</p>
<h2>Classification</h2><ul>{tags}</ul><p><code>{path}</code></p>
""".format(title=esc(card["name"]), summary=esc(card["function_summary"]), does=esc(card["does"]), does_not=esc(card["does_not"]), path=esc(card["skill_md"]), tags="".join(f"<li>{esc(tag)}</li>" for tag in tags) or "<li>unclassified</li>")
        (output / f"{slug}.html").write_text(body, encoding="utf-8")
        pages.append({"name": card["name"], "summary": card["function_summary"], "url": f"{slug}.html", "tags": tags})
    index = """<!doctype html><meta charset='utf-8'><title>Skill Knowledge Base</title>
<style>body{{font:16px system-ui;max-width:1100px;margin:40px auto;padding:0 20px}}input{{width:100%;padding:12px;font-size:16px;margin:10px 0 20px}}li{{margin:8px 0}}small{{color:#666}}</style>
<h1>Skill Knowledge Base</h1><input id='q' placeholder='Search skills…'><ul id='list'></ul>
<script>const data={data};const q=document.querySelector('#q'),list=document.querySelector('#list');function render(){{const s=q.value.toLowerCase();list.innerHTML=data.filter(x=>(x.name+' '+x.summary+' '+x.tags.join(' ')).toLowerCase().includes(s)).map(x=>`<li><a href='${{x.url}}'>${{x.name}}</a><br><small>${{x.summary||''}}</small></li>`).join('')}}q.oninput=render;render()</script>""".format(data=json.dumps(pages, ensure_ascii=False))
    (output / "index.html").write_text(index, encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"schema_version": "wiki-1.0.0", "pages": len(pages)}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "generated", "output": str(output), "pages": len(pages)}

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate static HTML wiki pages from the skill index.")
    parser.add_argument("--index-dir", default="")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    base = Path(args.index_dir).expanduser().resolve() if args.index_dir else Path(__file__).resolve().parent.parent / ".skill-index"
    result = generate(base, Path(args.output_dir).expanduser().resolve())
    print(json.dumps(result, ensure_ascii=False, indent=None if args.compact else 2, separators=(",", ":") if args.compact else None))
    return 0
if __name__ == "__main__": raise SystemExit(main())
