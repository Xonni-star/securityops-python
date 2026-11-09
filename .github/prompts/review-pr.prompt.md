---
name: review-pr
description: Review a pull request diff read-only and report actionable evidence-based findings.
argument-hint: [PR number or diff]
agent: project-reviewer
---

VS Code documents this prompt format for the **Local** harness. GitHub does not document `.prompt.md` as a Copilot Cloud prompt format, and Copilot App support is not documented.

Review the supplied diff without editing files or running commands. Focus on meaningful correctness/regression risks, authorization and object/personnel scope, data integrity/migrations, and missing tests or docs. Report findings first, each with severity, changed-file line evidence, impact, and confidence. Treat only changed lines as review-commentable if a comment draft is requested. Distinguish verified facts from assumptions; do not infer CI or merge state.
