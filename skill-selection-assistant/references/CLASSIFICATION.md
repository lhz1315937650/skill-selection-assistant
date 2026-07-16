# Classification And Index Reference

Read this reference only for classifier maintenance, taxonomy audits, or deep-index debugging.

## Scope

The index describes configured installing-user roots, not the repository author's environment. Maintain separate fields for the installed router directory and all indexed roots.

## Multi-Label Facets

Each skill may have multiple values for:

- primary domain
- detailed domain
- specialty
- task type
- technology
- output type
- setup requirement

The canonical single route is an audit view. Normal routing intersects multi-label facets so the same skill can be reached through every appropriate label.

## Provenance

Supported origins include:

- `user-local`
- `official-system`
- `installed-topic`
- `linked-external`
- `unknown`

For linked files, preserve both the logical entry path under the configured root and the resolved target path. Use the logical path for user-facing location and origin; use the resolved path for deduplication and content reads.

## Incremental Compatibility

Reuse a record only when:

- schema version matches
- rules fingerprint matches
- classifier fingerprint matches
- source status was successful
- file size and modification timestamp match

An explicit `--full-rebuild` disables reuse. A periodic content-hash audit may be used when stronger change detection is required.

## Failure Audit

Every discovered source must remain in `source-manifest.json`, including failed classifications. A partial build is `degraded`; `--strict` returns a non-zero exit after safely publishing the audit trail.

## Publication

Write a complete temporary generation, serialize publication with a cross-process lock, preserve the prior usable generation until replacement succeeds, and remove only owned temporary/backup paths.

## Runtime Files

Normal routing needs compact metadata, facets, label keywords, and route cards. Detailed NDJSON, CSV, Markdown catalogs, and hierarchy files are audit artifacts and must not be loaded into model context during ordinary selection.
