---
applyTo: "scripts/*.sh,docs/DEPLOYMENT.md,docs/BACKUP_RESTORE.md,docker-compose*.yml"
---

Deployment- und Restore-Skripte können kritische Daten verändern: erhaltene Bestätigungs-/Isolationsprüfungen und explizite Zielauswahl nicht entfernen oder umgehen. Dokumentiere Voraussetzungen, Secrets, Rollen, Reihenfolge, Fehlerfälle und geprüfte Rückwege; behaupte keinen Produktivbetrieb ohne konkreten Nachweis. TLS/Proxy, externe Secrets, Backups, Restore, Monitoring und Incident-Abläufe bleiben Betreiberverantwortung, sofern sie nicht nachweislich in der Zielumgebung umgesetzt sind. Niemals aus einer Codeänderung eigenmächtig deployen oder reale Daten verwenden.
