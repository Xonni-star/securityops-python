---
applyTo: "backend/app/**/*.py"
---

Halte dich an FastAPI-, SQLAlchemy- und Pydantic-Muster in den benachbarten Modulen. Router werden in `backend/app/main.py` registriert; Fachrouter und Schemas sind nach Bereich getrennt, die ORM-Modelle liegen zentral in `models.py`. Eingaben serverseitig validieren, Authentifizierung/Berechtigungen und Objekt-/Personalbereich im Backend prüfen. Änderungen an Zustandsübergängen, Audit und Datenbankzugriff müssen transaktional und nachvollziehbar sein. Ergänze passende Backendtests und aktualisiere API-Dokumentation, wenn sich der Vertrag ändert.
