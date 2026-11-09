---
name: test-changes
description: Run the smallest relevant local checks for the current changes and report exact results.
argument-hint: [changed paths]
agent: agent
---

This prompt is for VS Code with the **Local** harness. `.prompt.md` files are not runnable by Copilot cloud agent or the Copilot app.

Use `AGENTS.md` and `.github/copilot-instructions.md`. Inspect the current diff and the specified paths, then run only the smallest relevant checks supported by the repository configuration. Do not edit files, install dependencies, or claim a check passed unless you ran it successfully. For each command, report its working directory and exact result; distinguish skipped checks and environment blockers. For documentation-only changes, do not run unrelated application test suites.
