---
name: test-changes
description: Add focused regression tests and run the smallest relevant test set.
argument-hint: [behavior or changed paths]
agent: qa-engineer
---

VS Code documents this prompt format for the **Local** harness. GitHub does not document `.prompt.md` as a Copilot Cloud prompt format, and Copilot App support is not documented.

Inspect the requested behavior and existing tests. Add focused, deterministic tests using synthetic fixtures, including relevant invalid-input, permission-denial, or scope-isolation cases. Do not weaken assertions or change production behavior solely to satisfy tests. Run the smallest relevant backend pytest or frontend Vitest command from its correct directory. Report exact commands/results and checks not run. Do not merge or deploy.
