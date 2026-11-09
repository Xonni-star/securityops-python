---
applyTo: "backend/tests/**/*.py,frontend/src/**/*.test.ts,frontend/src/**/*.test.tsx"
---

Ergänze Tests am vorhandenen Verhalten und an relevanten negativen/Autorisierungsfällen; Tests müssen deterministisch und mit synthetischen Daten arbeiten. Backendtests nutzen pytest; die CI prüft zusätzlich Migrationen und Integration gegen PostgreSQL 17/Redis. Frontendtests verwenden Vitest. Teste Scope-Grenzen mit erlaubten und nicht erlaubten Objekt-/Personalbereichen. Führe passende betroffene Tests aus und unterscheide lokale Ergebnisse von CI-Abdeckung.
