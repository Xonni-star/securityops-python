---
name: documentation-change
description: Update German documentation using verified code and project evidence.
argument-hint: [documentation request or affected paths]
agent: documentation-engineer
---

This prompt file runs in VS Code **Local** only; `.prompt.md` files are not invoked by Copilot Cloud or the Copilot App.

Update the documentation required by the request in German. Ground technical and status claims in current source, migration, test, workflow, and live GitHub evidence as applicable. Preserve distinctions among merged code, open PRs, CI, business acceptance, and production operation. Do not invent capabilities, legal/tax conformity, or production readiness. Check affected relative links and Mermaid blocks, and report exact checks. Do not merge or deploy.
