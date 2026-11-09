---
name: new-feature
description: Implement a bounded feature with tests and documentation based on repository conventions.
argument-hint: [feature request and affected area]
agent: agent
---

VS Code documents this prompt format for the **Local** harness. GitHub does not document `.prompt.md` as a Copilot Cloud prompt format, and Copilot App support is not documented.

Implement the user's bounded feature request. Inspect the related code and `AGENTS.md` first; follow `.github/instructions/` for changed paths. Preserve existing behavior, keep the diff focused, add tests for changed behavior, and update directly related German documentation. Keep business logic and authorization in the backend; use Alembic for schema changes. If a necessary business rule is unconfirmed, avoid inventing it and explain the blocker. Run the smallest relevant checks and report exact commands/results. Do not merge or deploy.
