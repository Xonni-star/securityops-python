---
applyTo: "backend/app/*_api.py,backend/app/*portal*api.py,backend/app/auth.py,backend/app/upload_scanning.py,backend/app/document_storage.py,frontend/src/api.ts"
---

Jeder geschützte API-Endpunkt prüft serverseitig Authentifizierung, benötigte Rechte und bei operativen Daten den Objekt-/Personalbereich. Dieselben Scopes müssen Listen, Aggregate, Suche, Exporte und Dateiabruf begrenzen; IDs oder UI-Sichtbarkeit sind keine Autorisierung. Sensible Felder und Dateiinhalte nur über dafür berechtigte Wege ausgeben. Uploads serverseitig begrenzen und typisieren; Malware-Scan muss fail-closed sein. Keine Secrets oder echten Personen-/Kundendaten in Code, Fixtures oder Logs. Ergänze Tests für verweigerte Zugriffe und Scope-Isolation.
