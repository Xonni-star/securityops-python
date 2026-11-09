---
name: bug-analysis
description: Trace a reported bug to likely causes and propose evidence-backed remediation without edits.
argument-hint: [symptom, reproduction, and affected area]
agent: project-reviewer
---

VS Code documents this prompt format for the **Local** harness. GitHub does not document `.prompt.md` as a Copilot Cloud prompt format, and Copilot App support is not documented.

Investigate the stated symptom by reading the relevant implementation and tests. Do not edit files or run commands. Trace the behavior to a concrete likely cause, cite file/line evidence, and identify a minimal fix plus regression test. Label hypotheses and missing reproduction details explicitly; do not claim a root cause is confirmed unless code evidence establishes it.
