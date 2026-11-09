---
name: release-review
description: Assess release readiness from repository and live CI evidence without publishing or deploying.
argument-hint: [branch, PR, or release scope]
agent: devops-engineer
---

VS Code documents this prompt format for the **Local** harness. GitHub does not document `.prompt.md` as a Copilot Cloud prompt format, and Copilot App support is not documented.

Assess the specified release scope using current repository and live GitHub evidence when available. Check required CI, migrations, deployment/backup safeguards, configuration and documentation. Separate code/CI evidence from operator setup, business acceptance, legal/tax review, and production verification. List blockers and unknowns with evidence. This is a review only: do not publish a release, merge, deploy, run a production operation, or claim production approval.
