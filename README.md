# SecurityOps – Entwicklungsstand

Modularer Start für die Verwaltungsplattform eines Sicherheitsdienstes. Enthalten sind FastAPI, PostgreSQL, Alembic, eine React-Oberfläche, Kunden-, Objekt-, Personal-, Planungs-, Zeit-, OWKS-, Dokumenten-/Vertrags- und Rechnungswesenfunktionen sowie Benutzeranmeldung, RBAC, optionales TOTP-MFA und Sitzungsverwaltung. Der aktuelle `main`-Stand ist keine Produktionsfreigabe; offene PRs und Issues sind in [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md) getrennt ausgewiesen.

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
- `GET /api/v1/auth/mfa` und `POST /api/v1/auth/mfa/setup|enable|disable` – TOTP-MFA verwalten
- `GET /api/v1/auth/sessions` / `DELETE /api/v1/auth/sessions/{id}` – eigene Sitzungen einsehen/widerrufen
- `GET /api/v1/users/{id}/sessions` / `POST /api/v1/users/{id}/reset-password` – berechtigte administrative Sitzungsverwaltung/Passwortzurücksetzung
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

Bei direktem Backend-Start außerhalb von Docker: Python 3.12+, `cd backend`, `pip install '.[test]'`, die getrennten Datenbankrollen mit `python -m scripts.provision_database_roles` als Administrator provisionieren, Alembic mit `securityops_migrator` und die API mit `securityops_runtime` starten. Für Notification-/OWKS-Hintergrundverarbeitung zusätzlich in einem separaten Prozess `python -m app.notification_worker run` starten. Für lokale HTTP-Entwicklung müssen `APP_ENV=development` und `SESSION_COOKIE_SECURE=false` ausdrücklich gesetzt werden. Datenbank-Secrets gehören nicht in Quellcode oder Versionsverwaltung.

## Frontend ohne Docker (Monorepo)

Das Repository ist ein Monorepo: `backend/` enthält die FastAPI-Anwendung, `frontend/` die React-Oberfläche mit Vite und TypeScript. `frontend/` ist als npm-Workspace im Wurzel-`package.json` eingetragen, damit `npm install` und `npm run …` direkt am Repo-Root funktionieren und alle Abhängigkeiten in `node_modules/` im Wurzelverzeichnis landen. Voraussetzung ist Node.js ≥ 22.22.2; die Frontend-Abhängigkeiten verlangen aktuelle Node-Versionen (`vite` ≥ 20.19/22.12, `vitest` und `jsdom` ≥ 22.22).

```sh
npm install     # installiert alle Workspace-Abhängigkeiten
npm run dev     # Vite-Entwicklungsserver auf http://localhost:5173
npm run build   # Typprüfung und Produktionsbuild nach frontend/dist
npm test        # Vitest
```

Damit lässt sich das Frontend auch in Umgebungen starten, die ausschließlich ein Node-Projekt im Wurzelverzeichnis erwarten. Der Vite-Entwicklungsserver proxyt `/api` und `/health` auf `http://api:8000`, also auf den API-Container; ohne Compose rendert die Oberfläche, die API-Aufrufe laufen jedoch ins Leere. Für die vollständige Anwendung bleibt Docker Compose der vorgesehene Weg. Die CI installiert unverändert direkt in `frontend/` und nutzt dort weiterhin `frontend/package-lock.json`; bei Änderungen an den Frontend-Abhängigkeiten müssen beide Lockfiles aktuell sein.

## Tests

```sh
cd backend
pip install '.[test]'
pytest
```

Die lokalen API-Tests verwenden standardmäßig eine isolierte SQLite-Testdatenbank. Die GitHub-CI wendet alle Alembic-Migrationen auf PostgreSQL 17 an, führt die Backendtests gegen PostgreSQL und Redis aus und prüft einen verschlüsselten Backup-/Restore-Zyklus in einer isolierten Datenbank. Das belegt keinen Restore einer Produktionssicherung.

## Projektstatus und Sicherheit

Die Bestandsaufnahme und offenen Module sind in [`docs/PROJECT_AUDIT.md`](docs/PROJECT_AUDIT.md), [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md) und der [priorisierten Implementierungs-Roadmap](docs/IMPLEMENTATION_ROADMAP.md) dokumentiert. Weitere technische Informationen: [Architektur](docs/ARCHITECTURE.md), [Datenbank](docs/DATABASE.md), [API](docs/API.md), [Sicherheitsstatus](docs/SECURITY.md), [Sicherheitsprüfung](docs/SECURITY_REVIEW.md), [Installation](docs/INSTALLATION.md), [Deployment](docs/DEPLOYMENT.md), [Backup/Restore](docs/BACKUP_RESTORE.md), [Benutzeranleitung](docs/USER_GUIDE.md), [Changelog](docs/CHANGELOG.md) und [Roadmap](docs/ROADMAP.md).

Die Objektverwaltung umfasst Backend, API und Frontend mit Suche, Filtern, Details, Anschriften, Ansprechpartnern, Archivierung, Historie, Zuweisungen und getrennt geschützten Sicherheitsdaten. Objektzugriff wird serverseitig anhand globaler Rechte oder einer Objektzuweisung geprüft. Personalakten, Qualifikationen, Abwesenheiten, getrennte sensible Daten und versionierte Qualifikationsdateien sind in `main`. PRs #18–#20, #22–#24, #26–#29, #31, #33–#38 sind gemergt; Issues #2–#6 geschlossen. Die Leitstellenübersicht aus PR #38 ist eine berechtigungsgefilterte Momentaufnahme über aktive erreichbare Objekte und vorhandene Fachquellen, keine Echtzeitüberwachung. Sie erfindet keine Alarmmeldungen und gibt keine sensiblen Vorfalldetails oder Anhänge aus. OWKS umfasst objektspezifische QR-/NFC-Kontrollpunkte und -Routen, ein append-only Wachbuch, geschützte Anhänge und Offline-Synchronisierung mit sichtbaren Konflikten. QR-Codes werden erzeugt und können per Kamera gescannt werden; Web-NFC liest/beschreibt NDEF-Textkennungen nur bei sicherem Kontext und kompatiblem Browser/Gerät. Der eingebaute PostgreSQL-Minutenmonitor prüft versäumte Kontrollen auch über mehrere API-Instanzen. Statische QR-/NFC-Treffer bleiben `presence_verified=false`, gelten nicht als erledigter Besuch und beweisen keine physische Anwesenheit; dynamische kryptografische Tags oder Geräte-/Standortnachweise sind nicht integriert. Neue Dokumente/-versionen, OWKS-Anhänge, Personal-Qualifikationsdateien und Vorfallanhänge werden vor Speicherung fail-closed mit ClamAV geprüft. Bereits gespeicherte Dateien werden nicht rückwirkend geprüft; Scan und CI sind keine Garantie vollständiger Erkennung oder Produktionssicherheit. Dokumenten-/Vertragsverwaltung (PR #24), Rechnungswesen (PR #27), MFA/Sitzungsverwaltung (PR #31), Uploadscan (PR #33), Aufgaben-Kern (PR #34), In-App-Aufgabenbenachrichtigungen (PR #35), Schlüsselverwaltung (PR #36), Vorfallmanagement (PR #37) und Leitstellenübersicht (PR #38) sind in `main`. Issues #7–#10 sind aktuell offen, darunter Issue #8 trotz Merge der Dokumentenfunktionen. Das Audit-Protokoll ist über die Anwendung schreibgeschützt, aber nicht durch getrennte Datenbankrollen gegen privilegierte direkte Änderungen abgesichert.

PR #47 ergänzt getrennte Administrator-, Migrations- und Laufzeitrollen, PostgreSQL-Append-only-Schutz und eine prüfbare SHA-256-Auditkette; Datenbank-Owner/Superuser können diese Kontrollen weiterhin umgehen. PR #50 ergänzt im PR-Stack eine Inventarverwaltung für nicht schlüsselartige Betriebsmittel mit nachvollziehbaren Bewegungsereignissen. Externe getrennte Backups und Integritätsprüfpunkte bleiben Betreiberaufgaben. Weder CI noch diese Funktionen bedeuten eine Produktionsfreigabe.

Die Anwendung ist weiterhin keine Produktionsfreigabe. Produktions-Compose liefert statische Assets über Nginx aus, erzwingt Secure-Cookies und nutzt Redis für gemeinsame Rate-Limits; Migration, Scanner sowie ein verschlüsselter PostgreSQL-17-Restore sind in CI eingebunden. Für einen realen Betrieb müssen Betreiber TLS, Zertifikate, vertrauenswürdige Proxy-IP-Adressen, externe Secrets, minimale Datenbankrechte, Überwachung und getrennte Backup-Aufbewahrung einrichten und den Restore in ihrer eigenen Testumgebung wiederholen. Es wurde kein Produktions-Restore durchgeführt. MFA ist optional; Passwortzurücksetzung steht nur berechtigten Administratoren zur Verfügung. Selbstbedienungs-Reset per E-Mail fehlt. Ruhezeitregeln sind keine automatische Rechtsprüfung; gesetzliche, steuerliche oder buchhalterische Konformität wird nicht behauptet und erfordert unabhängige fachliche Prüfung.

## Dokumenten- und Vertragsverwaltung (in `main`, PR #24)

`main` enthält private, serverseitig geschützte Dokumentablage, geprüfte Uploads (PDF, PNG, JPG/JPEG, DOCX und XLSX), unveränderliche Dateiversionen, Historie, Freigaben, Lesebestätigungen, Vertragsverwaltung und konfigurierbare Erinnerungsdatensätze. Die Alembic-Kette verläuft von `0013_time_tracking_surcharges` über PR #23 (`0014_owks_wachbuch`) zu PR #24 (`0015_documents_contracts`). Dateien liegen in einem privaten, persistenten Docker-Volume und nicht im öffentlichen Frontend-Verzeichnis. Die Anwendungsebene-Verschlüsselung und der wiederaufnehmbare Re-Key-Befehl sind Teil der noch nicht in `main` integrierten Arbeit zu Issue #56. Neue Dateien und Versionen werden vor Speicherung synchron mit ClamAV geprüft; bei Erkennung oder Scannerfehlern wird der Upload abgewiesen. Bereits gespeicherte Dateien werden nicht rückwirkend geprüft. Die Uploadgröße ist über `DOCUMENT_MAX_UPLOAD_BYTES` konfigurierbar (Standard 20 MiB, maximal 100 MiB).

Die Erinnerungen werden über die geschützte Erinnerungsfunktion idempotent erzeugt und in der Oberfläche angezeigt. Es gibt keinen eingebauten Scheduler und keinen E-Mail-/Push-Versand; die Generierung muss von einer berechtigten Person oder einem externen, authentifizierten Prozess ausgelöst werden. Eine qualifizierte elektronische Signatur ist nicht enthalten. Issue #8 ist aktuell offen und bleibt bis zur fachlichen Abnahme offen. Die GitHub-CI prüft Migrationen und Backendtests auf PostgreSQL 17 sowie Frontend und Docker-Images, ohne daraus Produktionsfreigabe abzuleiten.

## Rechnungswesen

Die in PR #27 gemergte Migration `0017_billing` folgt auf `0016_scheduling_availability` und ergänzt Preisstammdaten, Rechnungen mit unveränderlichen Positionen und Snapshots, Zahlungen und versionierte Buchhaltungsexporte. Preis-, Steuerkennzeichen- und Steuersatzwerte sind explizite Konfigurationen und werden zusammen mit Kunden-, Vertrags- und verwendeten Zeiterfassungs-/Zuschlagssnapshots gespeichert; es wird keine steuerliche oder buchhalterische Konformität behauptet. Geldwerte werden mit `Decimal`/`NUMERIC` berechnet; jede Position wird mit `ROUND_HALF_UP` auf zwei Nachkommastellen gerundet, danach werden Summen aus den gespeicherten Positionswerten gebildet. Freigegebene Rechnungen sind schreibgeschützt. Korrekturen erzeugen einen neuen Folgebeleg, der die Ursprungspositionen storniert und optional Ersatzpositionen enthält. Issue #7 bleibt trotz Merge offen, bis die fachlichen Kriterien geprüft sind.

Rechnungsnummern und Idempotenzschlüssel sind datenbankseitig eindeutig. Freigabe, Archivierung, Preisanlage, Zahlungen, Mahnstatus und Exporte werden serverseitig berechtigt und im Audit-Protokoll vermerkt. PDF-Dateien werden erst nach Freigabe aus dem gespeicherten Snapshot serverseitig erzeugt und mit privaten/no-store-Headern ausgeliefert; es gibt keinen öffentlichen Dateiablagepfad. Der Export ist eine versionierte JSON-Schnittstelle (`securityops-accounting-v1`), keine zertifizierte Buchhaltungsintegration.

## Aufgabenmanagement (in `main`, PR #34)

Migration `0019_tasks` ergänzt einen generischen Aufgaben-Kern mit Zuständigkeit, optionalem Kunden-/Objektbezug, Fälligkeit, Priorität, Status, Erledigungsnachweis, Kommentaren, Verlauf und Audit. Die API erzwingt Rechte und Objektbereich serverseitig. Aufgaben entstehen nicht automatisch aus Vorfällen, Kontrollgängen, Planung, Qualifikationen, Verträgen oder Abrechnung. Anhänge, Hintergrundjobs und Eskalationen sind nicht Bestandteil des Moduls; eine spätere Integration benötigt abgestimmte Ereignis- und Berechtigungsregeln.

## In-App-Benachrichtigungen (in `main`, PR #35)

Migration `0020_notifications` ergänzt eine empfängergebundene Inbox und dauerhafte Outbox; Migration `0024_notification_outbox_worker` ergänzt den separaten Worker und append-only Attempt-Historie. Der Worker verarbeitet `task.assigned` und `task.status_changed` idempotent zu In-App-Einträgen, mit konkurrierenden Claims, Lease/Wiederaufnahme, Backoff/Retry und Dead-Letter-Status. Derselbe Dienst führt den OWKS-Prüfzyklus aus. Lesestatus und Liste sind über `notifications.read_own` und Aufgabenbereichsrechte geschützt. E-Mail-/Push-Zustellung, Task-Erinnerungen/Eskalationen und Ereignisse aus anderen Modulen sind nicht enthalten; der Worker ist keine fachliche oder produktive Abnahme.

## Schlüsselverwaltung (in `main`, PR #36)

Migration `0021_key_management` ergänzt ein objektgebundenes Register für physische Schlüssel und append-only Bewegungen für Ausgabe, Rückgabe, Verlust, Defekt und Inventur. Eine Ausgabe erfordert eine aktive, dem Schlüsselobjekt zugewiesene Person sowie bestätigte Quittierung; Rechte und Objektbereich werden im Backend geprüft. Die digitale Quittierung ist keine qualifizierte elektronische Signatur und belegt weder physische Verwahrung noch tatsächliche Sicherung. Bestehende Freitext-Zutrittsangaben werden nicht migriert oder als Schlüsselbestand interpretiert. Details zu Tabellen, API, Berechtigungen und Grenzen stehen in [`docs/KEY_MANAGEMENT.md`](docs/KEY_MANAGEMENT.md).

## Vorfall- und Beschwerdemanagement (in `main`, PR #37)

Migration `0022_incident_management` ergänzt objektbezogene Vorgänge mit Fristen, Verantwortlichkeiten, Status, Maßnahmen, Abschlussbericht und optionaler OWKS-Referenz desselben Objekts. Sieben abgestufte `incidents.*`-Rechte erzwingen serverseitigen Objektzugriff; Hergang, Abschlussbericht, Beteiligte/Zeugen und Dateizugriff sind zusätzlich sensitiv geschützt. PDF-/PNG-/JPEG-Anhänge bis 10 MiB werden fail-closed mit ClamAV geprüft, im privaten Dokumentenspeicher abgelegt und nur über autorisierte Endpunkte abgerufen. Verlauf, Personenbezüge und Dateireferenzen sind append-only. Es gibt keine automatische Aufgaben- oder Benachrichtigungsintegration, Fristerinnerung oder Eskalationsregeln; Scans und CI belegen keine vollständige Malware-Erkennung oder Produktionssicherheit. Details: [`docs/INCIDENTS.md`](docs/INCIDENTS.md).
