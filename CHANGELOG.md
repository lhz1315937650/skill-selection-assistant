# Changelog

All notable changes to this project will be documented in this file.

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
