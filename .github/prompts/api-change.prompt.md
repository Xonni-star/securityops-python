---
name: api-change
description: Design or implement a focused FastAPI endpoint change with schemas, authorization, tests, and docs.
argument-hint: [endpoint requirement]
agent: backend-engineer
---

VS Code documents this prompt format for the **Local** harness. GitHub does not document `.prompt.md` as a Copilot Cloud prompt format, and Copilot App support is not documented.

Implement the requested API change using the existing FastAPI router and Pydantic schema patterns. Check router registration, authentication, required permissions, object/personnel scope, input validation, response exposure, and transaction behavior. Keep the frontend out of the security boundary. Add backend tests for success, invalid input, and denied or out-of-scope access as relevant; update API docs in German. Create a migration only if persistent schema changes require one. Run relevant backend checks and report exact results. Do not merge or deploy.
