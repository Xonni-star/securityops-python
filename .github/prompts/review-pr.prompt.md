---
name: review-pr
description: Review a pull request diff read-only and report actionable evidence-based findings.
argument-hint: [PR number or diff]
agent: project-reviewer
---

This prompt file runs in VS Code **Local** only; `.prompt.md` files are not invoked by Copilot Cloud or the Copilot App.

Review the supplied diff without editing files or running commands. Focus on meaningful correctness/regression risks, authorization and object/personnel scope, data integrity/migrations, and missing tests or docs. Report findings first, each with severity, changed-file line evidence, impact, and confidence. Treat only changed lines as review-commentable if a comment draft is requested. Distinguish verified facts from assumptions; do not infer CI or merge state.
