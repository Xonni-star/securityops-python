# Zentrales Aufgabenmanagement

## Umfang

Der Aufgaben-Kern stellt generische Aufgaben mit Titel, Beschreibung, verantwortlichem Benutzer, Ersteller, optionalem Kunden und Objekt, Fälligkeit, Priorität, Status und Erledigungsnachweis bereit. Kommentare und ein fortlaufend erfasster Aufgabenverlauf ergänzen die zentrale Audit-Protokollierung. Änderungen an Aufgabe, Zuweisung und Abschluss werden gemeinsam mit dem fachlichen Schreibvorgang persistiert.

Die Revision `0019_tasks` folgt auf `0018_identity_security`; die Benachrichtigungserweiterung `0020_notifications` folgt auf `0019_tasks`. Aufgaben verwenden die Statuswerte `open`, `in_progress`, `blocked`, `completed` und `cancelled`; Prioritäten sind `low`, `normal`, `high` und `urgent`. Zum erstmaligen Abschließen ist ein Erledigungsnachweis erforderlich. Ein Fälligkeitszeitpunkt muss eine Zeitzone enthalten und wird in UTC gespeichert.

## API

- `GET /api/v1/tasks`: paginierte Liste mit Suche, Status-, Prioritäts-, Verantwortlichen-, Kunden-, Objekt- und Überfälligkeitsfilter.
- `POST /api/v1/tasks`: Aufgabe anlegen; ohne explizite Verantwortlichkeit wird der Ersteller eingetragen.
- `GET /api/v1/tasks/{id}`: Aufgabendetails einschließlich Kommentaren und Verlauf.
- `PATCH /api/v1/tasks/{id}`: validierte Änderungen, Zuweisung und Statuswechsel.
- `POST /api/v1/tasks/{id}/comments`: Kommentar anfügen.
- `GET /api/v1/tasks/locations` und `GET /api/v1/tasks/assignees`: datensparsame Auswahlwerte für berechtigte Aufgabenersteller und Zuweisende.

Schreibvorgänge verwenden Datenbanktransaktionen; Aufgaben-, Kommentar-, Verlauf- und Audit-Einträge werden gemeinsam committed. Nicht sichtbare Aufgaben werden bei Einzelabrufen als nicht gefunden behandelt, damit IDs nicht als Auskunftskanal dienen.

## Berechtigungen

- `tasks.read_own`: eigene Aufgaben sowie Aufgaben zu persönlich zugewiesenen Objekten einsehen.
- `tasks.read_all`: Aufgaben übergreifend einsehen.
- `tasks.create`: Aufgaben anlegen, wobei Objekt- und Kundenzuordnungen dem eigenen Objektbereich entsprechen müssen.
- `tasks.update_own`: eigene oder auf eigene Objekte bezogene Aufgaben bearbeiten.
- `tasks.manage`: sichtbare Aufgaben verwalten.
- `tasks.assign`: Aufgaben anderen aktiven Benutzern zuweisen.
- `tasks.manage_all`: Aufgaben und Zuordnungen unabhängig vom Objektbereich verwalten.

Die Migration weist alle Aufgabenberechtigungen der Administratorrolle zu, Lese-/Bearbeitungsrechte im eigenen Bereich den Rollen `operations` und `employee` und bereichsübergreifende Verwaltungsrechte der Geschäftsführung. Die Berechtigungsprüfung findet ausschließlich im Backend statt.

## In-App-Benachrichtigungen

PR #35 hat mit `0020_notifications` eine In-App-Inbox und persistente Outbox ergänzt. Tatsächliche Neuzuweisungen und Statuswechsel erzeugen ein Outbox-Ereignis innerhalb derselben Datenbanktransaktion wie Aufgabenhistorie und Audit. Der Worker erzeugt daraus deduplizierte Empfängerbenachrichtigungen; neue Zuweisungen benachrichtigen die neue verantwortliche Person, Statuswechsel die verantwortliche Person und den Ersteller, soweit diese nicht selbst handeln.

Der separate Worker aus PR #39 / Migration `0024_notification_outbox_worker` verarbeitet `task.assigned` und `task.status_changed` zu In-App-Einträgen. Er nutzt PostgreSQL-Claims mit `SKIP LOCKED`, Lease-/Token-Schutz, Wiederaufnahme abgelaufener Claims, idempotente Empfängererzeugung, exponentiellen Backoff, Dead-Letter-Status und append-only Attempt-Historie. Der Worker führt außerdem den OWKS-Prüfzyklus aus, der zuvor im API-Lifespan lief. Das bestätigt nur die implementierte Verarbeitung dieser Ereignisse, nicht externe Zustellung oder produktive Betriebsfähigkeit: E-Mail/Push, Task-Erinnerungen/Eskalationen und Ereignisse aus anderen Modulen bleiben ausgeschlossen.

## Grenzen und Folgeintegration

Der Aufgaben-Kern erzeugt noch keine automatischen Aufgaben aus Vorfällen, Objektprüfungen, Kontrollgängen, Dienstplanproblemen, Qualifikations- oder Vertragsabläufen, Materialprüfungen, Rechnungsfreigaben oder Kundenanfragen. Diese Module veröffentlichen derzeit keine vereinbarte Task-Event-Schnittstelle; sie werden daher nicht direkt gekoppelt. Anhänge, Erinnerungen, Hintergrundjobs und automatisierte Eskalationen sind nicht Bestandteil dieser Einheit. Anhänge müssen über autorisierte Backend-Endpunkte und mit dem bestehenden Malware-Scan geschützt werden.
