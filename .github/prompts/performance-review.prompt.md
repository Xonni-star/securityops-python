---
name: performance-review
description: Identify measured or code-evident performance risks and propose low-risk improvements without edits.
argument-hint: [query, endpoint, or changed paths]
agent: project-reviewer
---

VS Code documents this prompt format for the **Local** harness. GitHub does not document `.prompt.md` as a Copilot Cloud prompt format, and Copilot App support is not documented.

Review the specified code read-only for a concrete performance bottleneck. Trace relevant query, pagination, serialization, or rendering behavior and cite file/line evidence. Distinguish observed complexity or repeated work from unmeasured runtime impact; do not invent benchmark results. Propose a minimal improvement and a way to measure/regression-test it. Do not edit files or run commands.
