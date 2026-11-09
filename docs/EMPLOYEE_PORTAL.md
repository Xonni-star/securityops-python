# Mitarbeiterportal

Das Mitarbeiterportal stellt angemeldeten Mitarbeitenden eine getrennte Self-Service-Oberfläche unter `/employee-portal/me` bereit. Es verwendet die vorhandenen Personal-, Dienstplan-, Aufgaben-, Benachrichtigungs- und Zeiterfassungsdaten aus Migration-Head `0024_notification_outbox_worker`; eine zusätzliche Tabelle oder Migration ist nicht erforderlich.

## Zugriff und Datenschutz

Jeder Portal-Endpunkt prüft serverseitig die Rolle `employee` und ermittelt den Datensatz über `Employee.user_id` des angemeldeten Kontos. Der Mitarbeiterdatensatz muss aktiv und nicht archiviert sein. Dienste und Arbeitszeiten sind zusätzlich auf dem Konto zugewiesene Objekte begrenzt. Eine vom Client gelieferte Mitarbeiter-ID wird weder als Scope verwendet noch in den Antragsdaten akzeptiert. Änderungen sind auf Anträge des serverseitig verknüpften Mitarbeitenden begrenzt; Status- und Eigentümerfelder können nicht übermittelt werden. Nicht angemeldete Konten erhalten `401`, Konten ohne Mitarbeiterrolle `403` und Konten ohne aktives verknüpftes Profil `404`.

Das Portal erteilt keine Berechtigung für die allgemeinen Personalendpunkte. Antworten enthalten keine Mitarbeiter-ID, Kontakt-/Adressdaten, Personalakte, Gehaltsdaten, Qualifikationsdateien, Objektadressen oder Sicherheitsdetails, Kundeninformationen, Aufgabenkommentare/-historien, interne Aufgabenbeschreibungen, Erledigungsnachweise oder Zeiterfassungs-Korrekturgründe.

## Funktionen und Endpunkte

| Endpunkt | Funktion |
| --- | --- |
| `GET /api/v1/employee-portal/me` | Eigenen Namen und Funktionstitel anzeigen |
| `GET /api/v1/employee-portal/me/shifts` | Eigene veröffentlichte Dienste anzeigen; Entwürfe und abgesagte Dienste bleiben verborgen |
| `GET /api/v1/employee-portal/me/shifts/{shift_id}` | Details eines eigenen veröffentlichten Dienstes; fremde und unveröffentlichte IDs liefern `404` |
| `GET /api/v1/employee-portal/me/tasks` | Zugewiesene Aufgaben mit Titel, Fälligkeit, Priorität und Status |
| `GET /api/v1/employee-portal/me/notifications` | Eigene In-App-Benachrichtigungen (höchstens 100) |
| `PATCH /api/v1/employee-portal/me/notifications/{notification_id}/read` | Eigene Benachrichtigung als gelesen markieren; fremde IDs liefern `404` |
| `GET /api/v1/employee-portal/me/qualifications` | Nicht archivierte eigene Qualifikationen einschließlich Gültigkeits- und Ablaufdaten |
| `GET /api/v1/employee-portal/me/time-entries` | Eigene Zeitübersicht, standardmäßig die 100 neuesten Einträge |
| `GET /api/v1/employee-portal/me/absences` | Eigene Abwesenheitsanträge und deren Prüfstatus |
| `POST /api/v1/employee-portal/me/absences` | Abwesenheit beantragen; der Server setzt den Status verbindlich auf `pending` |
| `PATCH /api/v1/employee-portal/me/absences/{absence_id}` | Eigenen noch offenen Abwesenheitsantrag ändern; fremde IDs liefern `404`, entschiedene Anträge `409` |
| `GET /api/v1/employee-portal/me/availability-requests` | Eigene Verfügbarkeitswünsche und deren Status |
| `POST /api/v1/employee-portal/me/availability-requests` | Zeitraum als bevorzugt oder nicht verfügbar einreichen; der Server setzt den Status verbindlich auf `open` |
| `PATCH /api/v1/employee-portal/me/availability-requests/{request_id}` | Eigenen noch offenen Verfügbarkeitsantrag ändern; fremde IDs liefern `404`, entschiedene Anträge `409` |

Verfügbarkeitszeiten werden in der für die Dienstplanung konfigurierten IANA-Zeitzone erfasst (im Standard `Europe/Berlin`) und wie im bestehenden Dienstplan auf ungültige DST-Ortszeiten geprüft. Anträge werden dem verknüpften Mitarbeiterkonto zugeordnet und können über das Portal nicht selbst freigegeben werden. Die Prüfung und Entscheidung verbleibt bei den bestehenden Personal- beziehungsweise Dienstplan-Workflows. Im Portal wird der vorhandene Audit-Verlauf von Verfügbarkeitsanträgen mit Einreichung, Änderungen und vorhandener Entscheidung angezeigt; bei Abwesenheiten ist eine Entscheidung nur als aktueller Status erkennbar, da der bestehende Personal-Audit-Eintrag nicht mit der einzelnen Antrags-ID verknüpft ist. Rückfragen sind in den vorhandenen Antragsmodellen nicht speicherbar.

## Oberfläche und Grenzen des MVP

Die deutsche Portalnavigation umfasst Dienste, Aufgaben, Benachrichtigungen, Qualifikationen, Arbeitszeiten sowie Abwesenheits- und Verfügbarkeitsanträge. Lade-, Fehler- und Leerzustände sind vorhanden. Kontosicherheit bleibt über die separate Navigation erreichbar.

Nicht enthalten sind die Bearbeitung von Stammdaten oder Qualifikationen, Dateiabruf/-upload, Einsicht in interne Aufgabenkommentare, Dienständerungen, Zeiterfassungs-Korrekturen, Dokumente/Verträge, Lohnabrechnungen sowie das Zurückziehen bereits eingereichter Anträge. Rücknahmen erfordern eine persistente Statusänderung statt physischer Löschung; die bestehenden Status-Constraints der Antragstabellen kennen keinen Rücknahmezustand. Dafür müssen die Constraints von `employee_absences` und `schedule_availability_requests` um `withdrawn` erweitert und die Statusänderung mit Antrag-ID, handelndem Konto und Zeit im vorhandenen `AuditLog` protokolliert werden.

Die Migrationenkette ist für dieses PR nicht sicher erweiterbar: PR #43 basiert weiterhin auf `main` mit Head `0024_notification_outbox_worker`; PR #40 schlägt `0025_unique_incident_owks_event` vor, und das darauf gestapelte PR #42 führt mit `0026_customer_portal_access`, `0027_customer_document_grants` und `0028_customer_portal_requests` fort. Diese Revisionen sind nicht in `main`; PR-Base und Stack wurden nicht geändert. Eine Portal-Migration auf diesem Branch würde mit der offenen Kette kollidieren oder deren Übernahme voraussetzen. Daher gibt es hier keine Rücknahmefunktion und keine neue Migration. PR #42 ergänzt ausschließlich kundenbezogene Tabellen; es führt weder Mitarbeiter-Dokumentfreigaben noch Stammdatenänderungsanträge oder Mitarbeiter-Rückfragen ein. Für persönliche Dokumente fehlt weiterhin eine explizite Mitarbeiterfreigabe, für Stammdatenänderungen ein geeignetes Antragsmodell. Die Zeitübersicht ist keine Abrechnung und zeigt keine Zuschläge oder Geldbeträge. Die Oberfläche zeigt bis zu 100 neueste Zeit- und Benachrichtigungseinträge.

## Verifikation

Die Backendtests unter `backend/tests/test_employee_portal.py` decken fehlende Anmeldung, Rolle und aktiven Link, Objekt-/Employee-IDOR, fremde Benachrichtigungen, veröffentlichte Schichten, reduzierte Datenantworten sowie ausschließlich eigene und noch offene Anträge einschließlich Bearbeitung und Verlauf ab. Lokal prüfen:

```sh
cd backend
python -m pytest -q
ruff check app tests migrations
ruff format --check app tests migrations

cd ../frontend
npm test
npm run build
```
