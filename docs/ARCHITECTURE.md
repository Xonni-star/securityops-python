# Architektur

## Ist-Architektur auf `main`

SecurityOps ist ein modular gedachter, derzeit noch zentral organisierter Monolith. Die API-Router sind nach fachlichen Dateien getrennt, die SQLAlchemy-Modelle liegen jedoch gemeinsam in `backend/app/models.py`, und das Frontend ist eine gemeinsame React-Anwendung ohne eigenständige Modul-Bundles. PostgreSQL ist die Betriebsdatenbank; Alembic verwaltet Schemaänderungen. Docker Compose umfasst ein Produktionssetup und ein getrenntes Entwicklungs-Override.

```mermaid
flowchart LR
    Browser["Browser / React UI"]
    UI["React / TypeScript / Vite<br/>statisches Frontend"]
    Web["Nginx<br/>unprivilegierter Webserver"]
    API["FastAPI-Prozess<br/>app/main.py"]
    Identity["Identity / RBAC / MFA / Audit<br/>identity_api.py · auth.py"]
    Customer["Kunden / Objekte<br/>api.py"]
    People["Personal / Qualifikationen<br/>personnel_api.py"]
    Scheduling["Dienstplanung<br/>scheduling_api.py"]
    Time["Zeiterfassung / Zuschlagszeit<br/>time_tracking_api.py · time_tracking_surcharges.py"]
    OWKS["OWKS / Kontrollgänge<br/>owks_api.py · owks_scheduler.py"]
    Docs["Dokumente / Verträge<br/>documents_contracts_api.py"]
    Billing["Rechnungswesen<br/>billing_api.py"]
    Tasks["Aufgaben<br/>tasks_api.py"]
    Notifications["In-App-Benachrichtigungen<br/>notifications_api.py"]
    Worker["Separater Worker<br/>notification_worker.py<br/>Outbox + OWKS-Prüfzyklus"]
    Keys["Schlüsselverwaltung<br/>key_management_api.py"]
    Incidents["Vorfallmanagement<br/>incidents_api.py"]
    ControlRoom["Leitstellenübersicht<br/>control_room_api.py"]
    Outbox[("Benachrichtigungs-Outbox<br/>Task-Events / Attempts")]
    Scanner["Upload-Grenze<br/>ClamAV INSTREAM, fail-closed"]
    Models["Gemeinsame SQLAlchemy-Modelle<br/>models.py"]
    DB[("PostgreSQL")]
    Redis[("Redis<br/>Rate-Limit-Speicher")]
    Migrations["Alembic-Release-Schritt<br/>0001–0024 auf main"]
    CI["GitHub Actions<br/>PostgreSQL · Tests · Build · Docker · Security · Restore"]
    Browser -->|"HTTP(S)"| Web
    Web -->|"statischer Build"| Browser
    Browser -->|"/api/v1 · Session-Cookie · CSRF-Header"| Web
    Web -->|"Reverse Proxy /api/"| API
    API --> Identity
    API --> Customer
    API --> People
    API --> Scheduling
    API --> Time
    API --> OWKS
    API --> Docs
    API --> Billing
    API --> Tasks
    API --> Notifications
    API --> Keys
    API --> Incidents
    API --> ControlRoom
    API --> Scanner
    Identity --> Models
    Customer --> Models
    People --> Models
    Scheduling --> Models
    Time --> Models
    OWKS --> Models
    Docs --> Models
    Billing --> Models
    Tasks --> Models
    Notifications --> Models
    Keys --> Models
    Incidents --> Models
    ControlRoom --> Models
    Tasks --> Outbox
    Outbox --> Worker
    Worker --> DB
    Outbox --> DB
    Models --> DB
    API --> Redis
    Migrations --> DB
    CI --> API
    CI --> UI
    CI --> DB
```

## Request- und Berechtigungsfluss

`main.py` registriert Router aus `api.py`, `personnel_api.py`, `scheduling_api.py`, `time_tracking_api.py`, `time_tracking_surcharges.py`, `tasks_api.py`, `notifications_api.py`, `key_management_api.py`, `incidents_api.py`, `control_room_api.py`, `documents_contracts_api.py`, `billing_api.py`, `identity_api.py` und `owks_api.py` unter `/api/v1`; die Health-Endpunkte liegen außerhalb des Präfixes. Authentifizierte Requests lesen ein zufälliges opaque Session-Cookie. Gespeichert wird der Hash des Session-Tokens; Berechtigungen werden aus Benutzerrollen und Rollenrechten serverseitig ermittelt. MFA per TOTP ist optional aktivierbar; Recovery-Codes sind einmalig und gehasht, MFA-Secrets verschlüsselt. Sitzungen können durch den Kontoinhaber oder berechtigte Administratoren eingesehen bzw. widerrufen werden. Für zustandsändernde authentifizierte Requests müssen CSRF-Cookie und `X-CSRF-Token` übereinstimmen und der gespeicherte Tokenhash passen. Objekt-/Personal-Scope ist zusätzlich zu Modulrechten relevant; Mitarbeiter-Objektzuweisungen werden gegen den Objektzugriff geprüft. Benachrichtigungen verlangen `notifications.read_own` und ein Task-Leserecht sowie Empfänger- und Aufgabenbereichsprüfung. Schlüsselverwaltung verlangt `keys.*`-Rechte plus Objektbereich; Mitarbeitende für eine Ausgabe müssen dem Schlüsselobjekt zugewiesen sein. Das Vorfallmodul prüft ebenfalls den Objektbereich und nutzt eigene Lese-/Schreib- sowie getrennte Sensitivitätsrechte für Hergang, Abschlussbericht, Personen und Dateiabruf. Die Leitstellenroute verlangt `control_room.read` sowie `objects.read`, filtert aktive erreichbare Objekte und wendet je Datenquelle deren Fachrecht und Personen-/Objektbereich an; sensible Vorfallberichte und Anhänge werden nicht ausgegeben. Frontend-Sichtbarkeit ist keine Sicherheitsgrenze.

`/health/live` prüft nur den Prozess. `/health/ready` prüft Datenbank und in Produktion Redis und liefert bei Nichtverfügbarkeit HTTP 503. Das Produktions-Compose-Setup liefert statische Frontenddateien über Nginx; TLS wird von einem separat zu betreibenden Reverse Proxy terminiert. Nginx setzt Security-Header. Der API-Prozess nutzt in Produktion Redis für gemeinsam geteilte Rate-Limit-Zähler; Proxy-Header werden nur von konfigurierten vertrauenswürdigen Hops übernommen.

## Daten- und Integritätsgrenzen

Geschäftsdaten und Benutzerrechte liegen in PostgreSQL. Die fachlichen Tabellen, Beziehungen und Constraints stehen in [`DATABASE.md`](DATABASE.md). Migrationen sind eine lineare Alembic-Kette bis Revision `0024_notification_outbox_worker` auf `main`; das Schema umfasst 74 SQLAlchemy-Tabellen. Revision `0014_owks_wachbuch` ergänzt OWKS, `0015_documents_contracts` Dokumente und Verträge, `0016_scheduling_availability` Mitarbeiter-Verfügbarkeiten und Dienstwünsche, `0017_billing` Rechnungen/Positionen/Zahlungen/Exporte, `0018_identity_security` MFA, Recovery-Codes sowie Sitzungs-/Passwortverwaltungsfelder, `0019_tasks` den generischen Aufgaben-Kern, `0020_notifications` In-App-Benachrichtigungen samt Outbox, `0021_key_management` ein objektgebundenes Schlüsselregister mit Bewegungsverlauf, `0022_incident_management` Vorfälle, sensible Details, Maßnahmen, Personen, Anhänge und append-only Verlauf, `0023_control_room_permission` das Recht für die Leitstellenübersicht und `0024_notification_outbox_worker` Lock-/Lease-Felder sowie append-only Attempt-Historie für den separaten Worker. PRs #23, #24, #26, #27, #31, #34, #35, #36, #37, #38 und #39 sind gemergt. Revision 0024 ergänzt eine Tabelle und führt die Verarbeitung der Task-Outbox-Ereignisse ein. Schlüsselbewegungen sowie Vorfallverlauf, Personenbezüge und Dateireferenzen sind durch PostgreSQL-Trigger gegen UPDATE/DELETE geschützt; dies ersetzt keine getrennte Kontrolle privilegierter Datenbankadministration. Digitale Schlüsselquittierung belegt keine physische Verwahrung und ist keine qualifizierte elektronische Signatur.

Mehrere Datenbereiche haben separate sensitive Tabellen und Endpunkte. Qualifikationsdateien und OWKS-Anhänge werden in PostgreSQL gespeichert; allgemeine Dokumentversionen und Vorfallanhänge liegen in einem konfigurierten privaten lokalen Dateispeicher und werden über geschützte Endpunkte gelesen. Neue Uploads in diesen Bereichen werden vor Speicherung synchron durch ClamAV geprüft; Scannerfehler, Timeout und Nichterreichbarkeit führen zur Ablehnung. Vorhandene Dateien werden nicht rückwirkend geprüft. Das ist keine Garantie vollständiger Erkennung oder Produktionssicherheit. Vorfalldateien benötigen beim Upload sowohl Vorfall-Schreib- als auch Sensitivitätsverwaltungsrecht, beim Download Vorfall-Lese- und Sensitivitätsleserecht sowie Objektbereichszugriff. Billing-Rechnungen speichern Kunden-/Eingabe-Snapshots, und Korrekturen erzeugen Folgebelege statt Originalrechnungen zu überschreiben. Geldwerte verwenden `Decimal`/`NUMERIC`; Steuerwerte bleiben Konfiguration und sind nicht fachlich oder steuerlich abgenommen. Ein externer Datei-/Objektspeicher, KMS/Schlüsselrotation sind nicht vorhanden. Für Planungs- und Zeiterfassungsoperationen bestehen Datenbankconstraints und PostgreSQL-Advisory-Locks; der separate Worker führt den OWKS-Prüfzyklus mit bestehendem Advisory-Lock aus. Aufgabenänderungen erzeugen In-App-Benachrichtigungen für Zuweisung und Statuswechsel in derselben Transaktion. Der Worker verarbeitet ausschließlich diese beiden Task-Ereignistypen mit Konkurrenzschutz, Lease/Wiederaufnahme, Retry/Backoff und Dead-Letter-/Attempt-Historie. E-Mail/Push, Task-Erinnerungen/Eskalationen und Ereignisse aus anderen Modulen fehlen. Vorfallmaßnahmen und Fristen werden manuell verwaltet; es gibt keine automatische Aufgabenanlage, Benachrichtigung, Fristerinnerung oder Eskalationsregel. Details stehen in der Datenbank-, API- und Sicherheitsdokumentation.

## Deployment und CI

Das Produktions-Compose-Setup startet PostgreSQL, Redis, ClamAV, einen separaten einmaligen Alembic-Release-Schritt, API, Notification-/OWKS-Worker und Nginx für statische Frontenddateien. Ein separates Compose-Override stellt den lokalen Vite-Entwicklungsserver und HTTP-spezifische Einstellungen bereit. GitHub Actions prüft Backend und Migrationen auf PostgreSQL, Frontend-Build/Tests, Containerimages, Sicherheitsanalyse und einen isolierten synthetischen Backup-/Restorelauf. CI-Erfolg belegt weder reale Betriebsfähigkeit noch Produktionsfreigabe.

## Modulgrenzen und offene Arbeit

OWKS-Wachbuch, Dokumenten-/Vertragsfunktionen, Dienstplan-Verfügbarkeiten, Rechnungswesen, MFA/Sitzungsverwaltung, ClamAV-Uploadscan, Aufgaben-Kern, In-App-Aufgabenbenachrichtigungen, Schlüssel-, Vorfallmanagement, Leitstellenübersicht und Notification-/OWKS-Worker sind in `main` integriert. PR #25 (Dokumentation) ist gemergt; PR #40 ist offen und nicht Bestandteil von `main` (siehe [`PROJECT_STATUS.md`](PROJECT_STATUS.md)). Issues #7–#10 bleiben offen; ihre offenen Akzeptanz-/Betriebsfragen bedeuten nicht, dass die zugehörigen gemergten Funktionen fehlen. Das Dashboard liefert berechtigungsgefilterte Momentaufnahmen, keine umfassende Echtzeitüberwachung und keine simulierten Alarme. Vorfälle sind objektgebunden; sensible Details, Personen und Anhangzugriff sind granular berechtigt. Anhänge werden fail-closed gescannt und privat abgelegt. Maßnahmen, Fristen, Abschlüsse und Eskalationen lösen keine automatische Fachmodul- oder Benachrichtigungsintegration aus. Der Worker verarbeitet ausschließlich `task.assigned` und `task.status_changed` zu In-App-Benachrichtigungen und führt den OWKS-Prüfzyklus aus; E-Mail/Push, Task-Erinnerungen/Eskalationen und Ereignisse aus anderen Modulen sind ausgeschlossen. MFA ist optional; es gibt keinen nutzerinitiierten E-Mail-Passwortreset. Ein administrativer Reset verlangt Passwortwechsel und widerruft Sessions. Das Schlüsselregister beweist nicht die physische Verwahrung; Quittierung ist keine qualifizierte elektronische Signatur. Der modulare Monolith ist nicht in getrennte Services aufgeteilt und das ist keine stillschweigende Zielanforderung.
