# Installation Behavior

This document explains the portability rule for `skill-selection-assistant`.

## Core Rule

This repository is published for different Codex users.

Therefore, any install-time or update-time scan must target the user's own local Codex skill installation, not the repository author's machine.

## Portable Skills Root

The intended portable skills root is:

```text
$CODEX_HOME/skills
```

On Windows, a common local example may look like:

```text
C:\Users\<YourUser>\.codex\skills
```

That example is documentation only. It is not a hardcoded runtime default.

## What Must Not Happen

Published behavior must not:

- scan `C:\Users\Administrator\.codex\skills` as a product default
- depend on the publisher's username or filesystem layout
- assume that all users installed the same set of skills

## Future Offline Indexing Direction

If the project later adds install-time or update-time indexing for lower token usage, the intended behavior is:

1. resolve the user's local Codex home or skills root from the runtime environment
2. scan that installed local skill directory
3. build a lightweight local catalog of installed skills
4. use that catalog only as a portable per-user runtime aid

The catalog should reflect the user's actual installed skills, because every user's local skill set may be different.
