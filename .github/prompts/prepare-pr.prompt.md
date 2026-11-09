---
name: prepare-pr
description: Review current changes and draft an evidence-based German pull request title and body without publishing.
argument-hint: [base branch, default main]
agent: agent
---

This prompt is for VS Code with the **Local** harness. `.prompt.md` files are not runnable by Copilot cloud agent or the Copilot app.

Inspect the current branch, base branch, working tree, and full diff. Follow `AGENTS.md` and `.github/copilot-instructions.md`. Draft a concise German PR title and body that describe only the actual changes and checks actually run. Clearly label checks not run and do not infer CI, merge, issue, release, or production status; consult live GitHub state only if available and relevant. Do not edit files, create/update a PR, push, merge, or deploy. Output only the proposed title and body.
