# Changelog

All notable changes to this project will be documented in this file.

## v1.5.11 - 2026-06-06

- added `scripts/install-skill.py` as a cross-platform installer for users who are not on Windows PowerShell-first setups
- added a dynamic recommendation relevance gate through `MinRelevanceScore` so broad route shortlists do not include high-scoring but weakly related candidates by default
- documented cross-platform install commands and recommendation tuning knobs
- extended smoke tests to verify the Python installer is included and can copy the skill package

## v1.5.10 - 2026-06-06

- added `README.zh-CN.md`, a Chinese project introduction for GitHub readers
- linked the Chinese introduction from the English README
- clarified the published package boundary: this repo ships portable router logic, not any author's local skill index or private skill library
- added `record-selection-memory.ps1` so selection outcomes, missed matches, setup failures, and overlap notes can be recorded into the installing user's local `.skill-index/selection-memory.md`
- reduced recommendation JSON noise by emitting variant details only when multiple same-name variants exist
- documented the executable self-growth memory update flow in the skill instructions and self-growth guide
- added `scripts/install-skill.ps1` for first-time installation into a user's local Codex skills directory
- changed `recommend-skills.ps1` to build the local index automatically when the first-use `.skill-index/route-summary.json` is missing
- included `README.zh-CN.md` in release packages and fixed published Chinese agent metadata
- added `doctor.ps1` to diagnose first installs and rebuild missing local route summaries with `-Fix`
- made local selection memory influence future shortlist ranking through per-user boosts and penalties
- fixed self-only installs so the router skill excludes its own `SKILL.md` from recommendation candidates
- improved Chinese query candidate matching with CJK bigram tokens
- improved Chinese project/workspace routing and boosted project-local skills so they are not buried by large generic skill libraries
- changed recommendation selection from a hardcoded `1-3` default to a dynamic score-window policy with an explicit `-Limit` override

## v1.5.9 - 2026-06-03

- fixed garbled Chinese display metadata in `skill-selection-assistant/agents/openai.yaml`
- added shared classification rules in `skill-selection-assistant/rules/categories.json`
- changed scan and route inference scripts to load the same shared category rules
- split parser, rules, and output schema versions so output-only changes do not force parser-cache invalidation
- changed parsed skill cache output to `parsed-skills-cache.ndjson`
- optimized route bucket generation to avoid repeated full-list filtering by category
- added `scripts/clean-local-artifacts.ps1` for repository-only cleanup before review or packaging
- added `scripts/package-release.ps1` so release zips exclude local `.skill-index/` and `dist/` artifacts
- extended smoke tests to verify release packaging does not include local runtime artifacts

## v1.5.8 - 2026-06-03

- clarified the boundary between the installed router skill and the downloader's scanned local skill library
- added `IndexScope` and `SkillInstanceDir` to scanner output, while keeping `SkillsRoot` as the scanned user skill library
- documented that publisher-local skill counts, timings, paths, and indexes are development observations only
- extended smoke tests to verify that route summaries declare the per-user index scope and distinguish skill instance from scanned root

## v1.5.7 - 2026-06-03

- made full route file generation optional through `scan-local-skills.ps1 -IncludeFullRoutes`
- changed the default scan output to generate shortlists and route summaries without large full route JSON files
- updated selector errors to explain when full routes were not generated and how to create them for audits
- extended smoke tests to verify default shortlist-only scanning and explicit full-route generation

## v1.5.6 - 2026-06-03

- split scan caching into a lightweight `.skill-index/manifest.json` plus `.skill-index/parsed-skills-cache.json`
- removed full parsed skill objects from the manifest so the manifest stays small and easier to inspect
- added GitHub Actions smoke tests for pushes, pull requests, and manual workflow runs
- extended smoke tests to verify the manifest points to the parse cache and does not embed full skill items

## v1.5.5 - 2026-06-02

- added `.skill-index/manifest.json` to cache parsed skill metadata and reuse unchanged `SKILL.md` files on later scans
- made recommendations merge same-name variants by default while preserving variant details internally
- documented manifest-backed rescanning and same-name variant display behavior
- extended smoke tests to verify default variant merging in recommendation output

## v1.5.4 - 2026-06-02

- added a dependency-free PowerShell smoke test suite under `tests/`
- added fixture skills covering frontend routing, academic routing, spreadsheet classification, testing/debugging, exact duplicate merging, and same-name variant preservation
- verified scan, stale route cleanup, route inference, shortlist selection, and one-command recommendation through `tests/run-smoke-tests.ps1`
- documented the smoke test command for pre-release validation

## v1.5.3 - 2026-06-02

- added `scripts/recommend-skills.ps1` as a one-command route inference and candidate selection wrapper
- made normal recommendation easier to invoke without manually passing inferred route parameters
- added safe cleanup of generated `.skill-index/routes/` and `.skill-index/shortlists/` before rescanning to avoid stale route files
- documented the one-command recommender as the preferred token-saving entry point

## v1.5.2 - 2026-06-02

- added `scripts/infer-route.ps1` to infer the best route category before candidate selection
- added generated `.skill-index/shortlists/` files so normal routing can read small category shortlists instead of full route files
- changed `select-route-candidates.ps1` to prefer shortlist files by default and use full routes only as an explicit fallback
- preserved same-name skills with different content as separate variants instead of force-merging them into one representative
- documented the new infer-route -> select-candidates -> read-candidate-skill workflow

## v1.5.1 - 2026-06-02

- added route-first skill selection to avoid reading the full local skill index by default
- added route summary files and category route generation for primary domains, fine-grained domains, and task types
- added `scripts/select-route-candidates.ps1` to return a small local shortlist from one selected route
- documented that actual `SKILL.md` files should be read only after shortlisting or after the user chooses a skill
- improved token efficiency for large local skill libraries while preserving the full index as a fallback and audit file

## v1.5.0 - 2026-06-02

- added first-use / install-time local skill scanning through `scripts/scan-local-skills.ps1`
- added multi-level skill classification: origin, domain, task type, output type, setup level, and status
- added `.skill-index/` runtime artifacts for local indexes, category maps, and selection memory
- added self-growing skill-library logic for recurring intents, missed matches, overlapping skills, and new skill suggestions
- documented repository-level self-growth requirements in `SELF_GROWTH.md`
- kept published behavior portable by resolving the user's own skills root instead of hardcoding a publisher path

## v1.4.0 - 2026-05-25

- added a portability rule so published behavior must target each user's own installed local skills, not the repository author's personal path
- documented that future offline indexing should scan the user's runtime skills root, typically `$CODEX_HOME/skills`
- cleaned up README, skill instructions, and agent metadata to remove machine-specific assumptions and broken display text

## v1.3.0 - 2026-05-12

- added conversation-level active skill continuity after the user's first skill choice
- now keeps using the user's previously chosen skill on later turns when the workflow still fits
- now asks the user to choose again only when a later turn clearly needs a different skill
- refreshed the public README and agent metadata so the GitHub presentation is clearer and cleaner

## v1.2.0 - 2026-05-12

- added prerequisite-configuration question flow after skill selection
- now asks users for required setup choices when a selected skill depends on accounts, paths, providers, destinations, or other user-specific settings
- kept environment download confirmation and language-aware replies

## v1.1.0 - 2026-05-12

- changed skill selection replies from fixed Chinese to the user's request language
- updated local prompt metadata and documentation to reflect language-aware replies
- kept dependency or environment setup confirmation before downloads

## v1.0.0 - 2026-05-12

- published the first reusable version of `skill-selection-assistant`
- added Chinese-first skill selection behavior
- added confirmation flow for dependency or environment downloads
- added repository documentation and release metadata
