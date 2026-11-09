---
name: security-review
description: Review a requested change for evidence-based vulnerabilities without modifying code.
argument-hint: [changed paths or security concern]
agent: security-reviewer
---

This prompt file runs in VS Code **Local** only; `.prompt.md` files are not invoked by Copilot Cloud or the Copilot App.

Perform a read-only review of the requested paths or diff. Trace authentication, permissions, object/personnel scoping, input handling, sensitive data, database access, and file handling where relevant. Report only substantiated, actionable vulnerabilities with severity, file/line evidence, impact, preconditions, and confidence. Do not edit files, run commands, claim that absence of findings proves security, or provide generic hardening suggestions as findings.
