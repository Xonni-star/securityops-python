# Produktionshärtung und PostgreSQL-Integrationsprüfungen

Diese Dokumentation beschreibt die Implementierung der Produktionshärtung und PostgreSQL-Integrationsprüfungen gemäß Issue #9.

## Überblick

Die Implementierung zielt darauf ab, den lokalen Entwicklungsaufbau von einem kontrollierbaren Produktionsbetrieb zu trennen und die PostgreSQL-Laufzeit zu verifizieren. Dies umfasst die Einrichtung echter PostgreSQL-Integrations-Tests, Produktions-Frontend-Assets, TLS-Reverse-Proxy, sichere Header und andere Sicherheitsmaßnahmen.

## PostgreSQL-Integration

### Datenbankstruktur
Die PostgreSQL-Datenbank verwendet eine moderne Struktur mit folgenden Hauptkomponenten:
- `automation_rules` - Automatisierungsregeln
- `automation_runs` - Ausführungshistorie der Automatisierungsregeln
- `notifications_outbox` - Benachrichtigungsausgangsqueue
- `notifications_outbox_attempts` - Versuche für Benachrichtigungsausgänge
- `automations` - Automatisierungsspezifische Tabellen
- Und viele weitere Tabellen für verschiedene Geschäftsprozesse

### Migrationen
- Alle Migrationen sind linear auf dem aktuellen `main`-Head ausgeführt
- Daten bleiben erhalten während der Migrationen
- Migrationen werden als einmaliger Release-Schritt durchgeführt
- Parallel beim Start jeder API-Replik wird keine Migration durchgeführt

### PostgreSQL-Integrations-Tests
Die Integration wurde mit folgenden Tests verifiziert:
- Vollständige Migrationen mit Alembic
- API-Transaktionen mit PostgreSQL
- Datenbankverbindungsmanagement
- Transaktionale Konsistenz
- Performance-Tests mit echten Daten

## Produktionskonfiguration

### Backend-Konfiguration
Die Produktionsumgebung ist in `docker-compose.yml` konfiguriert mit folgenden Sicherheitsmerkmalen:

#### Umgebungsvariablen
- `APP_ENV: production` - Produktionsmodus aktiviert
- `SESSION_COOKIE_SECURE: "true"` - Secure-Cookies erzwungen
- `FORWARDED_ALLOW_IPS: ${FORWARDED_ALLOW_IPS:-172.28.0.10}` - Vertrauenswürdige IPs
- `RATE_LIMIT_STORAGE_URI: ${RATE_LIMIT_STORAGE_URI:-redis://redis:6379/0}` - Gemeinsamer Rate-Limit-Speicher

#### Sicherheitskonfiguration
- Alle API-Zugriffe erfordern Authentifizierung
- Transaktionssichere Ausführung
- Fail-closed-Design bei Fehlern
- Keine stille Klartext-Fallbacks

### Frontend-Deployment
- Produktions-Frontend als statische Assets statt Vite-Devserver
- Alle Assets werden kompiliert und als statische Dateien bereitgestellt
- Keine Entwicklungsserver in Produktionsumgebung

## TLS-Reverse-Proxy

### Konfiguration
Die Anwendung ist für die Nutzung mit TLS-Reverse-Proxy konzipiert:

#### Sichere Header
- Secure-Cookies aktiviert
- XSS-Schutz aktiviert
- Content-Type-Options
- Frame-Options
- Referrer-Policy

#### Proxy-Konfiguration
- Vertrauenswürdige Proxy-IPs werden in `FORWARDED_ALLOW_IPS` konfiguriert
- X-Forwarded-* Header werden korrekt verarbeitet
- Client-IP-Adresse wird korrekt ermittelt

## Rate Limiting

### Gemeinsamer Rate-Limit-Speicher
- Redis wird als gemeinsamer Rate-Limit-Speicher verwendet
- Mehrere API-Prozesse teilen denselben Rate-Limit-Status
- Transaktionssichere Implementierung

### Konfiguration
- `RATE_LIMIT_STORAGE_URI` kann in `.env` konfiguriert werden
- Standardmäßig auf Redis gestellt
- Unterstützung für verschiedene Speicherkonfigurationen

## Sicherheit und Compliance

### Datenbanksicherheit
- Separate Benutzerkonten für verschiedene Zugriffsarten:
  - `securityops_admin` - Admin-Zugriff
  - `securityops_migrator` - Migrationen
  - `securityops_runtime` - Laufzeit-Zugriff
- Keine privilegierten Zugriffe in Produktionsumgebung
- Secure Connection Strings

### Backup- und Wiederherstellung
- Verschlüsselte Backups sind implementiert
- Dokumentierte und regelmäßig getestete Wiederherstellung
- Migration von Backups in Testumgebung

## CI/CD-Integration

### Automatisierte Sicherheitsprüfungen
- Automatisierte Abhängigkeits- und statische Sicherheitsanalyse in CI (SCA/SAST)
- Definierte Umgang mit Befunden
- Integration von CodeQL und anderen Security-Tools

### Testabdeckung
- CI startet PostgreSQL, spielt Migrationen ein und führt Tests aus
- API-/RBAC-Tests werden durchgeführt
- Frontend- und Backendtests sowie Build-Tests
- Docker-Build-Tests
- Verschlüsselter PostgreSQL-17-Restore-Tests

## Deployment-Prozess

### Release-Schritte
1. Migrationen als einmaliger Release-Schritt durchführen
2. Produktionscontainer starten
3. Sicherstellen, dass keine Entwicklungsserver aktiv sind
4. Alle Tests durchführen

### Sicherheitschecks
- PostgreSQL-Integrationstests
- API-Transaktionstests
- RBAC-Tests
- Sicherheitstests
- Performance-Tests

## Fehlerbehandlung

### PostgreSQL-Fehler
- Transaktionssichere Fehlerbehandlung
- Rollback bei Fehlern
- Protokollierung von Datenbankfehlern

### Sicherheitsfehler
- Fail-closed-Modus bei Sicherheitsproblemen
- Keine Datenverluste durch Sicherheitsfehler
- Klare Fehlermeldungen für Administratoren

## Produktions-Checkliste

### Vor Deployment
- [ ] Alle Migrationen erfolgreich ausgeführt
- [ ] PostgreSQL-Integrationstests bestanden
- [ ] Sicherheitsprüfungen (SCA/SAST) bestanden
- [ ] Alle API-Tests erfolgreich
- [ ] Frontend-Assets kompiliert
- [ ] TLS-Konfiguration überprüft
- [ ] Rate-Limiting konfiguriert
- [ ] Backup-Strategie getestet

### Nach Deployment
- [ ] Produktionscontainer startet korrekt
- [ ] Secure-Cookies aktiviert
- [ ] Vertrauenswürdige Proxy-IPs korrekt konfiguriert
- [ ] Alle Services healthy
- [ ] Logging und Monitoring aktiv

## Compliance

### Datenschutz
- Alle Daten werden serverseitig gespeichert
- Keine sensiblen Daten im Klartext gespeichert
- Authentifizierung aller Datenbankzugriffe
- Audittrail für alle Datenbankoperationen

### Technische Sicherheit
- Authentifizierung aller API-Zugriffe
- Fail-closed-Design bei Sicherheitsfehlern
- Wiederherstellbarkeit bei Fehlern
- Transaktionssichere Ausführung