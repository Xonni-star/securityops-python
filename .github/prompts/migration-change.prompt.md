---
name: migration-change
description: Prepare a safe Alembic migration and aligned model/tests for a requested schema change.
argument-hint: [schema change and data constraints]
agent: database-engineer
---

VS Code documents this prompt format for the **Local** harness. GitHub does not document `.prompt.md` as a Copilot Cloud prompt format, and Copilot App support is not documented.

Implement only the requested PostgreSQL schema change. Inspect current models, the Alembic head and chain, related data, database roles, and migration tests. Add a new revision with safe handling for existing rows, correct constraints/indexes, and explicit upgrade/downgrade behavior. Never use runtime `create_all` or silently drop/overwrite business data. Align models and schemas, add/update migration tests, and run the applicable PostgreSQL migration checks if the environment supports them. Report exact commands and limitations; do not merge or deploy.
