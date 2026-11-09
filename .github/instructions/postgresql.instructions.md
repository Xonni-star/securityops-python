---
applyTo: "backend/app/models.py,backend/app/database.py,backend/migrations/**/*.py,backend/scripts/*database*.py,backend/tests/**/*.py"
---

PostgreSQL ist die Betriebsdatenbank; `models.py` und `backend/migrations/versions/` sind gemeinsam mit Alembic-Tests maßgeblich. Alle Schemaänderungen ausschließlich als neue Alembic-Migration mit korrekter Vorgängerrevision, Constraints und Indizes umsetzen; Migrationen müssen bestehende Daten berücksichtigen. Keine Schemaänderung durch Laufzeit-`create_all`. Laufzeit-, Migrations- und Admin-Rolle getrennt halten. UUIDs und zeitzonenbewusste Zeitpunkte entsprechend vorhandenen Modellen verwenden; Geldbeträge als `Decimal`/`NUMERIC`. Geschäftskritische Datensätze nicht still überschreiben oder löschen. PostgreSQL-spezifische Änderungen gegen die vorgesehenen Integrationstests prüfen.
