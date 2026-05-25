# Changelog

All notable changes to this project will be documented in this file.

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
