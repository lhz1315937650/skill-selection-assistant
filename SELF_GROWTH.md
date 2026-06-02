# Self-Growing Skill Library

`skill-selection-assistant` is intended to make a user's local Codex skill library self-growing.

## What self-growing means

The skill library should not stay as a static list of folders. It should continuously improve through:

- install-time or first-use local scanning
- multi-level classification
- deduplicated recommendation views
- weighted fine-grained domain detection
- token-saving route-first selection
- concise skill recommendations in the user's language
- local selection memory
- missed-match notes
- new skill suggestions for repeated workflows
- review suggestions for overlapping or stale skills

## Generated local files

The scanner writes local runtime artifacts to:

```text
skill-selection-assistant/.skill-index/
|-- skills-index.json
|-- skills-categories.md
|-- route-summary.json
|-- route-summary.md
|-- routes/
|   |-- primary-domain/
|   |-- domain-detail/
|   `-- task-type/
|-- shortlists/
|   |-- primary-domain/
|   |-- domain-detail/
|   `-- task-type/
`-- selection-memory.md
```

These files describe the installing user's local skill library and should not be committed by default.

## Deduplication and classification

The scanner keeps the real local skills untouched. Deduplication only changes the generated recommendation index.

- `raw_total` records every discovered `SKILL.md`.
- `total` records the deduplicated recommendation candidates.
- `duplicates_removed` records how many duplicate entries were merged out of the index view.
- `duplicates` records merged names, source paths, source origins, and distinct content counts.
- `primary_domain` is the best single broad domain for fast selection.
- `domain_detail` records weighted fine-grained labels such as `frontend-web`, `backend-api`, `academic-research`, `visual-design`, `publishing-social`, and `testing-debugging`.
- Same-name skills with different content are preserved as separate variants instead of being forced into one representative candidate.

Fine-grained domain detection is weighted. Skill name matches are strongest, frontmatter description matches are next, and body preview matches are weakest. This keeps generic template words from overwhelming the actual skill purpose.

## Route-first selection

To avoid wasting context on large local libraries, recommendation should not read all skill files.

1. Prefer `scripts/recommend-skills.ps1` to infer the request category and filter candidates in one local step.
2. If the wrapper is unavailable, run `scripts/infer-route.ps1` and then `scripts/select-route-candidates.ps1`.
3. If scripts are unavailable, read `.skill-index/route-summary.md` or `.skill-index/route-summary.json`.
4. Pick one shortlist file by `primary_domain`, `domain_detail`, or `task_type`.
5. Read full route files only as fallback when a shortlist is missing or insufficient.
6. Shortlist `1-3` candidates.
7. Read candidate `SKILL.md` files only after shortlisting or after the user chooses.

The full `skills-index.json` and full route files are fallback and audit files. They should not be the default recommendation input.

## Growth loop

1. Scan the user's local skills root.
2. Build or refresh the deduplicated classified skill index.
3. Use the recommender or route inference to choose one category.
4. Use the selector script or category shortlist to recommend the best `1-3` skills.
5. Record useful matches and missed matches.
6. Suggest new skills when repeated workflows are not covered.
7. Suggest link, merge, or review actions when skills overlap.
8. Re-scan after new skills are installed.

## Safety rules

- Do not delete local skills automatically.
- Do not overwrite another skill's `SKILL.md` without explicit user permission.
- Do not hardcode the publisher's filesystem path.
- Treat the user's local installation as the source of truth.
