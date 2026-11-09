---
name: frontend-change
description: Implement a focused React/TypeScript interface change with German copy and Vitest coverage.
argument-hint: [UI requirement or component]
agent: frontend-engineer
---

VS Code documents this prompt format for the **Local** harness. GitHub does not document `.prompt.md` as a Copilot Cloud prompt format, and Copilot App support is not documented.

Implement the requested change in `frontend/src/` following existing component, `api.ts`, `types.ts`, strict TypeScript, CSS, and Vitest patterns. Keep labels and errors in German and preserve existing behavior. Do not treat client checks or hidden controls as authorization; rely on server-enforced permissions and scopes. Add/update tests and run relevant frontend checks from `frontend/`. Do not merge or deploy.
