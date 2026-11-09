---
name: migration-change
description: Prepare a safe Alembic migration and aligned model/tests for a requested schema change.
argument-hint: [schema change and data constraints]
agent: database-engineer
---

This prompt file runs in VS Code **Local** only; `.prompt.md` files are not invoked by Copilot Cloud or the Copilot App.

Implement only the requested PostgreSQL schema change. Inspect current models, the Alembic head and chain, related data, database roles, and migration tests. Add a new revision with safe handling for existing rows, correct constraints/indexes, and explicit upgrade/downgrade behavior. Never use runtime `create_all` or silently drop/overwrite business data. Align models and schemas, add/update migration tests, and run the applicable PostgreSQL migration checks if the environment supports them. Report exact commands and limitations; do not merge or deploy.
