---
name: test-changes
description: Add focused regression tests and run the smallest relevant test set.
argument-hint: [behavior or changed paths]
agent: qa-engineer
---

This prompt is for VS Code with the **Local** harness. `.prompt.md` files are not runnable by Copilot cloud agent or the Copilot app.

Inspect the requested behavior and existing tests. Add focused, deterministic tests using synthetic fixtures, including relevant invalid-input, permission-denial, or scope-isolation cases. Do not weaken assertions or change production behavior solely to satisfy tests. Run the smallest relevant backend pytest or frontend Vitest command from its correct directory. Report exact commands/results and checks not run. Do not merge or deploy.
