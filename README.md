# SecurityOps – Entwicklungsstand

Modularer Start für die Verwaltungsplattform eines Sicherheitsdienstes. Enthalten sind FastAPI, PostgreSQL, Alembic, eine React-Oberfläche, Kunden-, Objekt- und Personalverwaltung sowie Benutzeranmeldung, Rollen-/Rechteprüfung und Audit-Protokoll. Dienstplanung und Zeiterfassung sind in `main`; PR #23 ergänzt das objektgebundene OWKS-Wachbuch, QR-/NFC-Kontrollgänge und Offline-Synchronisierung.

## Start mit Docker Compose

Voraussetzung ist Docker mit Compose. Im Projektordner:

```sh
cp .env.example .env
```

Trage in `.env` drei unterschiedliche, zufällige Secrets für Datenbankadministrator, Migration und Laufzeit ein. Lokal wird die gesicherte Produktionskonfiguration mit einem ausdrücklich getrennten HTTP-Entwicklungs-Override verwendet:

```sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db redis
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile release run --rm provision-db
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile release run --rm --no-deps migrate
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build -d
```

Die Anwendung wird als statischer Build unter <http://localhost:5173> ausgeliefert. Die API-Dokumentation befindet sich unter <http://localhost:8000/docs>. Die Ports sind standardmäßig nur an `localhost` gebunden. Die Migration wird einmalig und vor dem API-Start ausgeführt, nicht durch jede API-Replik.

Der Entwicklungs-Override deaktiviert Secure-Cookies ausschließlich für lokales HTTP. Ohne ihn erzwingt Compose `APP_ENV=production`, `SESSION_COOKIE_SECURE=true` und einen gemeinsamen Redis-Speicher für Rate-Limits. `POSTGRES_ADMIN_PASSWORD`, `POSTGRES_MIGRATION_PASSWORD` und `POSTGRES_RUNTIME_PASSWORD` sind erforderlich; ersetze die Beispielwerte und verwende unterschiedliche Secrets.

## Erstes Administratorkonto

Nach der erfolgreich ausgeführten Migration sind Systemrollen und Berechtigungen angelegt. Erstelle danach ein erstes Administratorkonto. Setze die vier Variablen in deiner lokalen Shell (nicht in Git) und führe aus:

```sh
export BOOTSTRAP_ADMIN_USERNAME=admin
export BOOTSTRAP_ADMIN_EMAIL=admin@deine-domain.de
export BOOTSTRAP_ADMIN_NAME="System Administration"
export BOOTSTRAP_ADMIN_PASSWORD='ein-einmaliges-lang-passwort'
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec \
  -e BOOTSTRAP_ADMIN_USERNAME \
  -e BOOTSTRAP_ADMIN_EMAIL \
  -e BOOTSTRAP_ADMIN_NAME \
  -e BOOTSTRAP_ADMIN_PASSWORD \
  api python -m app.bootstrap_admin
unset BOOTSTRAP_ADMIN_USERNAME BOOTSTRAP_ADMIN_EMAIL BOOTSTRAP_ADMIN_NAME BOOTSTRAP_ADMIN_PASSWORD
```

Das Passwort muss mindestens 12 Zeichen lang sein. Der Bootstrapping-Befehl erstellt kein Standardpasswort und verweigert doppelte Benutzernamen oder E-Mail-Adressen. Melde dich anschließend an und erstelle weitere Benutzer über `POST /api/v1/users`.

## API

- `GET /health/live` – Prozessstatus
- `GET /health/ready` – Datenbankverbindung und in Produktion Redis prüfen
- `GET /api/v1/dashboard` – Kundenkennzahlen
- `POST /api/v1/auth/login` – Anmeldung und sichere Sitzung starten
- `GET /api/v1/auth/me` – angemeldeten Benutzer und Berechtigungen abrufen
- `POST /api/v1/auth/logout` – Sitzung beenden (CSRF-Token erforderlich)
- `POST /api/v1/auth/change-password` – Passwort ändern und Sitzungen widerrufen
- `GET /api/v1/users` / `POST /api/v1/users` – Benutzerverwaltung (entsprechende Berechtigung erforderlich)
- `GET /api/v1/roles` – Standardrollen und Rechte einsehen
- `GET /api/v1/audit-logs` – jüngste Audit-Einträge einsehen
- `GET /api/v1/customers?q=...&limit=25&offset=0` – Kunden suchen und paginieren
- `POST /api/v1/customers` – Kunde anlegen
- `GET /api/v1/customers/{id}` – Kundendetails abrufen
- `PATCH /api/v1/customers/{id}` – Kundendaten ändern
- `GET /api/v1/objects?q=...&status=...&customer_id=...` – Objekte suchen, filtern und paginieren
- `POST /api/v1/objects` – Objekt mit Kundenbeziehung anlegen
- `GET /api/v1/objects/{id}` / `PATCH /api/v1/objects/{id}` – Objekt abrufen oder ändern
- `POST /api/v1/objects/{id}/archive` und `/reactivate` – Objekt archivieren oder reaktivieren
- `GET /api/v1/objects/{id}/history` – Objektänderungen einsehen
- `/api/v1/objects/{id}/contacts` – Ansprechpartner einzeln verwalten
- `/api/v1/objects/{id}/assignments` – Objektmitarbeiter zuweisen (separate Berechtigung)
- `/api/v1/objects/{id}/security` – sensible Sicherheits- und Zutrittsdaten (separate Berechtigungen)
- `/api/v1/inventory/assets` – Inventargegenstände suchen/filtern und mit Berechtigung anlegen oder ändern; Ausgabe, Rückgabe, Übergabe, Meldungen, Wartung und Reparaturen werden als Ereignisse protokolliert
- `/api/v1/inventory/assets/{id}/events` – Inventarhistorie einsehen oder neue Vorgänge erfassen
- `GET /api/v1/employees?q=...&status=...` – Personal suchen, filtern und paginieren (`employees.read`)
- `POST /api/v1/employees` und `GET /api/v1/employees/{id}` – Personalakte anlegen und abrufen
- `/api/v1/employees/{id}/qualifications` – Qualifikationsnachweise verwalten
- `/api/v1/employees/qualifications/expiring` – ablaufende und abgelaufene Nachweise
- `/api/v1/employees/{id}/absences` – Abwesenheiten mit eigenen Rechten verwalten
- `/api/v1/employees/{id}/sensitive` – getrennt geschützte sensible Personaldaten
- `/api/v1/scheduling/settings` – Zeitzone und Mindestruhezeit lesen/ändern
- `/api/v1/scheduling/shifts` – Schichten mit Tages-/Wochen-/Monatsfiltern lesen und verwalten
- `/api/v1/scheduling/shifts/{id}/history` – nachvollziehbaren Änderungsverlauf lesen
- `/api/v1/time-tracking/start` und `/entries/{id}/pause|resume|stop` – Arbeitsintervalle und Pausen erfassen
- `/api/v1/time-tracking/entries` – eigene oder berechtigt sichtbare Buchungen nach Zeitraum und Status abrufen
- `/api/v1/time-tracking/entries/manual` – manuelle, freigabepflichtige Nachträge für berechtigte Benutzer
- `/api/v1/time-tracking/entries/{id}/corrections` und `/corrections/{id}/approve|reject` – Korrekturen beantragen und entscheiden
- `/api/v1/time-tracking/entries/{id}/approve|reject|lock` – Einreichungen freigeben, begründet ablehnen oder sperren
- `/api/v1/time-tracking/reports` und `/reports/missing` – Soll-/Ist-, Pausen-, Abweichungs- und Fehlbuchungsübersichten
- `/api/v1/time-tracking/export.csv` – CSV-Export freigegebener Arbeitszeiten
- `/api/v1/time-tracking/surcharge-rules` und `/settings` – konfigurierbare Zuschlagsarten und Feiertags-Bundesland
- `/api/v1/time-tracking/entries/{id}/surcharge-calculations` – getrennte, versionierte Zuschlagszeit-Nachweise
- `/api/v1/time-tracking/reports/surcharges` und `/export-surcharges.csv` – Auswertung und CSV historisierter Zuschlagszeiten
- `/api/v1/time-tracking/periods/lock` – geprüfte, endgültige Abrechnungsperiodensperre
- `/api/v1/billing/rates` – Abrechnungspreise mit Einheit, konfiguriertem Steuerkennzeichen und -satz (`billing.rates.manage`)
- `/api/v1/billing/invoices` – Rechnungsentwürfe aus Preiskonfigurationen, Vertragsreferenzen und freigegebenen Zeitbuchungen (`billing.invoices.create`)
- `/api/v1/billing/invoices/{id}/approve|archive` – Statusmaschine und unveränderliche Freigabe mit Audit-Eintrag
- `/api/v1/billing/invoices/{id}/corrections` – Folgebeleg mit Storno der Originalpositionen und optionalen Ersatzpositionen
- `/api/v1/billing/invoices/{id}/payments` und `/dunning` – idempotente Zahlungen und nachvollziehbarer Mahnstatus
- `/api/v1/billing/invoices/{id}/pdf` – serverseitig erzeugtes PDF ausschließlich für freigegebene Rechnungen
- `/api/v1/billing/invoices/{id}/exports` – idempotenter Buchhaltungsexport `securityops-accounting-v1`

Statuswerte: `active`, `inactive`, `lead`. Kundennummern werden serverseitig eindeutig als `K-<UUID>` erzeugt. Kunden werden in dieser Ausbaustufe nicht physisch gelöscht.

Dienstplanung und Zeiterfassung speichern Zeitpunkte als UTC und verwenden die konfigurierte IANA-Zeitzone (standardmäßig `Europe/Berlin`) für lokale Tagesfilter und Anzeige. Arbeitszeitbuchungen können mehrere Arbeits- und Pausenabschnitte umfassen. Freigegebene Zeitwerte bleiben unverändert; beantragte Korrekturen werden als neue Version mit Grund und erneuter Freigabe historisiert. Ein Mitarbeiter kann nicht gleichzeitig mehrere offene Zeitbuchungen haben; parallele Prüfungen werden pro Mitarbeiter transaktionsgebunden serialisiert. Rollenrechte und Objektzuweisungen werden serverseitig kontrolliert. CSV-Zeilen werden gegen Tabellenformelinjektion abgesichert. Überstunden in der Auswertung bezeichnen ausschließlich positive Abweichungen zur geplanten Arbeitszeit, keine tarifliche oder gesetzliche Berechnung. Diese Funktionen sind keine automatische arbeitsrechtliche Konformitätsgarantie.

Zuschlagsregeln unterstützen Nacht, Samstag, Sonntag, Feiertag und betriebliche Zeitfenster mit Gültigkeit, Werttyp, Priorität und ausdrücklich gesetztem Kombinationsmodus. Feiertage folgen dem konfigurierten Bundesland. Versionierte Berechnungen speichern nur tatsächliche zuschlagsfähige Arbeitszeit und Regel-/Kalender-Snapshots; Periodensperren verhindern nachträgliche Zeitänderungen und Neuberechnungen. Geldbeträge sind bewusst nicht implementiert: Lohnbasis, Prozentbasis, Festzuschlagseinheit und Rundung sind nicht fachlich bestätigt. Die Anwendung ist kein Payroll-System und nicht produktions- oder rechtsfreigegeben.

## Datenbankserver konfigurieren

Das Backend liest `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER` und `POSTGRES_PASSWORD` aus der Umgebung. Compose gibt der API und dem Worker ausschließlich die Rolle `securityops_runtime`; Migrationen laufen als `securityops_migrator`, der Administrator bleibt auf Provisioning und getrennte Betriebsaufgaben beschränkt. `CORS_ORIGINS` steuert die erlaubte Browser-Origin. Der Datenbankport wird absichtlich nicht öffentlich freigegeben. Sitzungen verwenden zufällige opaque Cookies; der Datenbankeintrag speichert nur den Token-Hash. Schreibzugriffe erfordern einen CSRF-Header. Passwort-Hashes werden mit Argon2id erzeugt.

Bei direktem Backend-Start außerhalb von Docker: Python 3.12+, `cd backend`, `pip install '.[test]'`, Rollen mit `python -m scripts.provision_database_roles` als Administrator provisionieren, Migrationen mit `securityops_migrator` und danach die API mit `securityops_runtime` starten. Für lokale HTTP-Entwicklung müssen `APP_ENV=development` und `SESSION_COOKIE_SECURE=false` ausdrücklich gesetzt werden. Datenbank-Secrets gehören nicht in Quellcode oder Versionsverwaltung.

## Tests

```sh
cd backend
pip install '.[test]'
pytest
```

Die lokalen API-Tests verwenden standardmäßig eine isolierte SQLite-Testdatenbank. Die GitHub-CI wendet alle Alembic-Migrationen auf PostgreSQL 17 an, führt die Backendtests gegen PostgreSQL und Redis aus und prüft einen verschlüsselten Backup-/Restore-Zyklus in einer isolierten Datenbank. Das belegt keinen Restore einer Produktionssicherung.

## Projektstatus und Sicherheit

Die Bestandsaufnahme und offenen Module sind in [`docs/PROJECT_AUDIT.md`](docs/PROJECT_AUDIT.md), [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md) und der [priorisierten Implementierungs-Roadmap](docs/IMPLEMENTATION_ROADMAP.md) dokumentiert. Weitere technische Informationen: [Architektur](docs/ARCHITECTURE.md), [Datenbank](docs/DATABASE.md), [API](docs/API.md), [Sicherheitsstatus](docs/SECURITY.md), [Sicherheitsprüfung](docs/SECURITY_REVIEW.md), [Installation](docs/INSTALLATION.md), [Deployment](docs/DEPLOYMENT.md), [Backup/Restore](docs/BACKUP_RESTORE.md), [Benutzeranleitung](docs/USER_GUIDE.md), [Changelog](docs/CHANGELOG.md) und [Roadmap](docs/ROADMAP.md).

Die Objektverwaltung umfasst Backend, API und Frontend mit Suche, Filtern, Details, Anschriften, Ansprechpartnern, Archivierung, Historie, Zuweisungen und getrennt geschützten Sicherheitsdaten. Objektzugriff wird serverseitig anhand globaler Rechte oder einer Objektzuweisung geprüft. Die Inventarverwaltung ergänzt nicht schlüsselartige Betriebsmittel; physische Einzelschlüssel verbleiben im separaten Schlüsselregister. Sie protokolliert Ausgabe, Rückgabe, Übergabe, Verlust/Beschädigung, Wartung und Reparatur nachvollziehbar. Es gibt keine automatische Wartungsfrist oder Benachrichtigung; Details stehen in [`docs/INVENTORY.md`](docs/INVENTORY.md). Personalakten, Qualifikationen, Abwesenheiten, getrennte sensible Daten und versionierte Qualifikationsdateien sind in `main`. PR #18 ist mit Merge-Commit `c8d4fbe203d179b7c4b620d604409c7217478033` gemergt; Backend/PostgreSQL, Frontend einschließlich Vitest und Docker CI waren grün, Issue #6 ist geschlossen. Issue #2 bleibt bis zur formalen Abnahme seiner Akzeptanzkriterien offen. Dienstplanung ist mit PR #19 in `main`; Zeiterfassung wurde mit PR #22 gemergt. PR #23 ergänzt OWKS mit objektspezifischen QR-/NFC-Kontrollpunkten und -Routen, einem append-only Wachbuch, geschützten Anhängen und Offline-Synchronisierung mit sichtbaren Konflikten. QR-Codes werden erzeugt und können per Kamera gescannt werden; Web-NFC liest/beschreibt NDEF-Textkennungen nur bei sicherem Kontext und kompatiblem Browser/Gerät. Der eingebaute PostgreSQL-Minutenmonitor prüft versäumte Kontrollen auch über mehrere API-Instanzen. Statische QR-/NFC-Treffer bleiben `presence_verified=false`, gelten nicht als erledigter Besuch und beweisen keine physische Anwesenheit; dynamische kryptografische Tags oder Geräte-/Standortnachweise sind nicht integriert. Issue #3 bleibt bis zur fachlichen Abnahme offen. PR #24 ergänzt auf PR #23 gestapelt Dokumenten- und Vertragsverwaltung mit Migration 0015; beide PRs bleiben bis zur jeweiligen Prüfung offen. MFA, Passwortzurücksetzung und Rechnungswesen sind noch nicht implementiert. Die Audit-Einträge sind in PostgreSQL append-only und SHA-256-verkettet; Laufzeit-, Migrations- und Administratorrollen sind getrennt. Das schützt nicht vor privilegierter Manipulation durch Datenbank-Owner/Superuser. Externe getrennte Backups und ein separat gespeicherter Integritätsprüfpunkt bleiben Betreiberaufgaben und sind keine Produktionsfreigabe.

Die Anwendung ist weiterhin keine Produktionsfreigabe. Produktions-Compose liefert statische Assets über Nginx aus, erzwingt Secure-Cookies und nutzt Redis für gemeinsame Rate-Limits; Migration, Scanner sowie ein verschlüsselter PostgreSQL-17-Restore sind in CI eingebunden. Für einen realen Betrieb müssen Betreiber TLS, Zertifikate, vertrauenswürdige Proxy-IP-Adressen, externe Secrets, minimale Datenbankrechte, Überwachung und getrennte Backup-Aufbewahrung einrichten und den Restore in ihrer eigenen Testumgebung wiederholen. Es wurde kein Produktions-Restore durchgeführt. Ruhezeitregeln sind keine automatische Rechtsprüfung; gesetzliche Konformität wird nicht behauptet und erfordert unabhängige fachliche Prüfung.

## Dokumenten- und Vertragsverwaltung (PR #24, auf PR #23 gestapelt)

Dieser Branch ergänzt Issue #8 um private, serverseitig geschützte Dokumentablage, geprüfte Uploads (PDF, PNG, JPG/JPEG, DOCX und XLSX), unveränderliche Datei-Versionen, Historie, Freigaben, Lesebestätigungen, Vertragsverwaltung und konfigurierbare Erinnerungsdatensätze. Die additive Alembic-Kette verläuft von `0013_time_tracking_surcharges` über PR #23 (`0014_owks_wachbuch`) zu PR #24 (`0015_documents_contracts`). Dateien liegen in einem privaten, persistenten Docker-Volume und nicht im öffentlichen Frontend-Verzeichnis. Die Uploadgröße ist über `DOCUMENT_MAX_UPLOAD_BYTES` konfigurierbar (Standard 20 MiB, maximal 100 MiB).

Die Erinnerungen werden über die geschützte Erinnerungsfunktion idempotent erzeugt und hier in der Oberfläche angezeigt. Es gibt keinen eingebauten Scheduler und keinen E-Mail-/Push-Versand; die Generierung muss von einer berechtigten Person oder einem externen, authentifizierten Prozess ausgelöst werden. Ein Malware-/Virenscanner und eine qualifizierte elektronische Signatur sind ebenfalls nicht enthalten. PR #24 ist auf PR #23 gestapelt und bleibt ungemergt; Issue #8 bleibt bis zur fachlichen Abnahme offen. Die kombinierte CI validiert Migrationen und Backendtests auf PostgreSQL 17 sowie Frontend und Docker-Images.

## Rechnungswesen

Migration `0017_billing` ergänzt nach der Dienstplan-Erweiterung `0016_scheduling_availability` Preisstammdaten, Rechnungen mit unveränderlichen Positionen und Snapshots, Zahlungen und versionierte Buchhaltungsexporte. Preis-, Steuerkennzeichen- und Steuersatzwerte sind explizite Konfigurationen und werden zusammen mit Kunden-, Vertrags- und verwendeten Zeiterfassungs-/Zuschlagssnapshots gespeichert; es wird keine steuerliche oder buchhalterische Konformität behauptet. Geldwerte werden mit `Decimal`/`NUMERIC` berechnet; jede Position wird mit `ROUND_HALF_UP` auf zwei Nachkommastellen gerundet, danach werden Summen aus den gespeicherten Positionswerten gebildet. Freigegebene Rechnungen sind schreibgeschützt. Korrekturen erzeugen einen neuen Folgebeleg, der die Ursprungspositionen storniert und optional Ersatzpositionen enthält.

Rechnungsnummern und Idempotenzschlüssel sind datenbankseitig eindeutig. Freigabe, Archivierung, Preisanlage, Zahlungen, Mahnstatus und Exporte werden serverseitig berechtigt und im Audit-Protokoll vermerkt. PDF-Dateien werden erst nach Freigabe aus dem gespeicherten Snapshot serverseitig erzeugt und mit privaten/no-store-Headern ausgeliefert; es gibt keinen öffentlichen Dateiablagepfad. Der Export ist eine versionierte JSON-Schnittstelle (`securityops-accounting-v1`), keine zertifizierte Buchhaltungsintegration.
