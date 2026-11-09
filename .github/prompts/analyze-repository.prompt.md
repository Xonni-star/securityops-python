---
name: analyze-repository
description: Analyze a repository area and provide an evidence-based technical summary without edits.
argument-hint: [area, file, or question]
agent: project-reviewer
---

This prompt file runs in VS Code **Local** only; `.prompt.md` files are not invoked by Copilot Cloud or the Copilot App.

Analyze the requested area. Do not edit files or run commands. Cite relevant file paths and line ranges, separate observed facts from uncertainty, and summarize the architecture or behavior needed to answer the request. Identify material constraints and state what you could not verify. Do not turn the analysis into unrequested implementation work.
