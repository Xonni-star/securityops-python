# Lokale Installation

> **Geltungsbereich:** Diese Anleitung beschreibt eine lokale Entwicklungsinstallation, keine
> produktive Bereitstellung. Produktive DNS-, TLS-, Secret-, Backup-, Monitoring- und
> Wiederherstellungsverfahren sind Betreiberaufgaben; die Hinweise in
> [Deployment](DEPLOYMENT.md) müssen für die Zielumgebung umgesetzt und getestet werden.

## Docker Compose (Entwicklung)

1. Docker Engine und Compose installieren.
2. `cp .env.example .env` ausführen. Die Werte in `.env.example` sind Platzhalter und keine verwendbaren Secrets. Für eine lokale Installation drei getrennte, zufällige Datenbank-Secrets setzen. `.env` nicht committen oder weitergeben; für Produktion ist ein verwalteter Secret Store vorzuziehen. Die Dokumentenschlüssel sind nicht in diesem Beispiel vorgegeben.
3. Für ein bestehendes Datenbankvolume vor dem Upgrade ein vollständiges Backup erstellen. `POSTGRES_ADMIN_USER` und `POSTGRES_ADMIN_PASSWORD` müssen auf einen PostgreSQL-Superuser zeigen; dieser wird bei einer neuen Compose-Datenbank angelegt, nicht an API oder Worker weitergereicht.
4. PostgreSQL und Redis starten. Danach die Rollen als Administrator provisionieren und die Migration genau einmal als Migrationsrolle ausführen. Erst nach erfolgreichem Abschluss API, Frontend und Worker starten:

   ```sh
   docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db redis
   docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile release run --rm provision-db
   docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile release run --rm --no-deps migrate
   docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build -d
   ```

   Das letzte `up` startet die Standarddienste `api`, `notification-worker` und `frontend`; die API wartet auf gesunde Datenbank, Redis und ClamAV. Die Migration gehört zum Profil `release` und wird nicht automatisch bei jedem Start ausgeführt.
5. Den Admin-Bootstrap-Befehl aus der README mit einmaligen Shell-Umgebungsvariablen ausführen. Die Beispielwerte dort durch lokale Testwerte ersetzen und die Variablen nach dem Befehl aus der Shell entfernen.
6. Statische Oberfläche unter `http://localhost:5173`, API-Dokumentation unter `http://localhost:8000/docs` öffnen. Die Compose-Ports sind an Loopback gebunden und nicht als öffentlicher Zugang gedacht.

Der Override `docker-compose.dev.yml` setzt `APP_ENV=development`, lokale CORS-Ursprünge und `SESSION_COOKIE_SECURE=false`. Nur für lokales HTTP verwenden. Ohne den Override setzt das Produktions-Compose `APP_ENV=production` und sichere Cookies; diese Einstellung allein macht eine Installation noch nicht produktionsbereit.

Für Produktivbetrieb, TLS-/Proxy-Anforderungen und die Betriebs-Checkliste siehe [Deployment](DEPLOYMENT.md); Backup und isolierte Restore-Proben sind in [Backup und Wiederherstellung](BACKUP_RESTORE.md) beschrieben. Beide Dokumente enthalten Betreiber-Leitlinien, die vor Einsatz in der Zielumgebung umgesetzt und getestet werden müssen.

## Ohne Container

Backend: Python 3.12+, `cd backend`, `pip install '.[test]'`, zunächst `python -m scripts.provision_database_roles` mit dem Administratorzugang und den beiden Rollen-Secrets ausführen. Anschließend `POSTGRES_USER=securityops_migrator` und `POSTGRES_PASSWORD` auf das Migrations-Secret setzen und einmalig `alembic upgrade head` ausführen. Für API und Worker danach `POSTGRES_USER=securityops_runtime` und `POSTGRES_PASSWORD` auf das Laufzeit-Secret setzen; API mit `uvicorn app.main:app --reload`, Hintergrundverarbeitung in einem separaten Prozess mit `python -m app.notification_worker run` starten. Für lokale HTTP-Entwicklung `APP_ENV=development` und `SESSION_COOKIE_SECURE=false` ausdrücklich setzen. Frontend-Entwicklung: `cd frontend`, `npm ci`, `npm run dev`.

## Status

Der lokale Installationspfad wurde nicht in einer Docker-Umgebung ausgeführt. Die PostgreSQL-17-CI prüft Migrationen, API-Tests und einen separaten verschlüsselten Backup-/Restore-Zyklus mit synthetischen Daten. Das ist kein Installations-, Produktions- oder Produktions-Restore-Nachweis. Der erste Administrator benötigt gültige Umgebungsvariablen; es gibt kein fest eingebautes Standardkonto oder Passwort.
