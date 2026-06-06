# Self-Growing Skill Library

`skill-selection-assistant` is intended to make a user's local Codex skill library self-growing.

## Scope boundary

The published repository contains the router skill. It does not contain or define the downloader's full skill library.

- `SkillInstanceDir` is the installed `skill-selection-assistant` folder.
- `SkillsRoot` is the current user's local Codex skills directory.
- `.skill-index/` is generated beside the router skill, but it describes the user's own `SkillsRoot`.

The publisher's local skill count, categories, benchmark timings, and generated indexes are development observations only. They are not assumptions for downloaders.

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
|-- manifest.json
|-- parsed-skills-cache.ndjson
|-- skills-categories.md
|-- route-summary.json
|-- route-summary.md
|-- DETAILED_CLASSIFICATION.md
|-- detailed-classification.json
|-- domain-task-matrix.csv
|-- routes/                 # optional; only with -IncludeFullRoutes
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

`DETAILED_CLASSIFICATION.md` and `domain-task-matrix.csv` are generated summaries for humans. They make the local skill library easier to inspect, tune, and prune without loading the full index into the conversation.

## Deduplication and classification

The scanner keeps the real local skills untouched. Deduplication only changes the generated recommendation index.

- `raw_total` records every discovered `SKILL.md`.
- `total` records the deduplicated recommendation candidates.
- `duplicates_removed` records how many duplicate entries were merged out of the index view.
- `duplicates` records merged names, source paths, source origins, and distinct content counts.
- `manifest.json` stores lightweight file fingerprints so unchanged files can be recognized quickly.
- `parsed-skills-cache.ndjson` stores reusable parsed skill metadata for cache hits, one skill per line.
- `rules/categories.json` stores shared classification and query-inference rules used by both the scanner and route inference.
- `primary_domain` is the best single broad domain for fast selection.
- `domain_detail` records weighted fine-grained labels such as `frontend-web`, `backend-api`, `academic-research`, `visual-design`, `publishing-social`, and `testing-debugging`.
- Same-name skills with different content are preserved as separate variants instead of being forced into one representative candidate.
- Recommendation output merges same-name variants by default for readability and emits variant details only when there is more than one variant.

Fine-grained domain detection is weighted. Skill name matches are strongest, frontmatter description matches are next, and body preview matches are weakest. This keeps generic template words from overwhelming the actual skill purpose.

## Route-first selection

To avoid wasting context on large local libraries, recommendation should not read all skill files.

1. Prefer `scripts/recommend-skills.ps1` to infer the request category and filter candidates in one local step.
2. If the wrapper is unavailable, run `scripts/infer-route.ps1` and then `scripts/select-route-candidates.ps1`.
3. If scripts are unavailable, read `.skill-index/route-summary.md` or `.skill-index/route-summary.json`.
4. Pick one shortlist file by `primary_domain`, `domain_detail`, or `task_type`.
5. Read full route files only as fallback when a shortlist is missing or insufficient; generate them with `scan-local-skills.ps1 -IncludeFullRoutes` only for audits.
6. Shortlist candidates according to the selector's score-window policy.
7. Read candidate `SKILL.md` files only after shortlisting or after the user chooses.

Dynamic recommendations also apply a relevance gate. Candidates should not enter the default dynamic shortlist just because they score well inside a broad route; they should also match enough useful words from the user's actual query. This keeps large public installs from recommending high-scoring but weakly related skills.

For Chinese requests, the selector expands common Chinese intent words into portable English routing hints before scoring candidates. This helps Chinese users match English-language skill descriptions without hardcoding any publisher-specific skill names.

The full `skills-index.json` and full route files are fallback and audit files. Full route files are not generated by default and should not be the default recommendation input.

## Growth loop

1. Scan the user's local skills root.
2. Build or refresh the deduplicated classified skill index.
3. Use the recommender or route inference to choose one category.
4. Use the selector script or category shortlist to recommend the weighted shortlist.
5. Record useful matches and missed matches.
6. Suggest new skills when repeated workflows are not covered.
7. Suggest link, merge, or review actions when skills overlap.
8. Re-scan after new skills are installed.

Record a selection or missed match with:

```powershell
powershell -ExecutionPolicy Bypass -File skill-selection-assistant/scripts/record-selection-memory.ps1 -Query "<user request>" -Outcome selected -SelectedSkill "<skill name>" -RouteType domain_detail -Category "<category>"
```

This keeps self-growth local to the installing user's `.skill-index/selection-memory.md`.

The selector reads that local memory during ranking. Repeatedly selected skills receive a local boost for matching categories; rejected or setup-failed skills receive a local penalty. This keeps learning personal to the installing user's machine and avoids hardcoding publisher-specific preferences.

## Diagnostics

For a first install or a broken local index, run:

```powershell
powershell -ExecutionPolicy Bypass -File skill-selection-assistant/scripts/doctor.ps1 -Fix
```

The doctor checks the installed router skill, local skills root, shared rules, route summary, shortlists, selection memory, and a sample recommendation. With `-Fix`, it rebuilds the local index when the route summary is missing.

## Safety rules

- Do not delete local skills automatically.
- Do not overwrite another skill's `SKILL.md` without explicit user permission.
- Do not hardcode the publisher's filesystem path.
- Treat the user's local installation as the source of truth.
