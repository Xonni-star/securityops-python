---
applyTo: "backend/migrations/**/*.py,backend/alembic.ini"
---

Erstelle Schemaänderungen als vorwärts gerichtete Alembic-Revision in der linearen Migrationskette. Prüfe Modell/Migration-Konsistenz, Upgrade-Pfad, Constraints, Indizes, Fremdschlüssel und Auswirkungen auf vorhandene Daten. Kein `create_all` als Ersatz für produktive Migrationen und keine stillschweigende destruktive Datenmigration. Für Änderungen an nicht verlustfrei rücksetzbaren Daten muss Downgrade-Verhalten sicher und explizit sein. Verwende die PostgreSQL-Migrationsprüfungen aus `.github/workflows/ci.yml`.
