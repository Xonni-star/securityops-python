# Mitarbeiterportal

Das Mitarbeiterportal stellt angemeldeten Mitarbeitenden eine getrennte Self-Service-Oberfläche unter `/employee-portal/me` bereit. Diese Dokumentation beschreibt den Erweiterungsstand mit Migration `0032_employee_portal_requests_and_documents`, gestapelt auf `0031_safe_automations`; dieser Stand ist erst nach Merge der zugehörigen Pull Requests Teil von `main`.

## Zugriff und Datenschutz

Jeder Portal-Endpunkt prüft serverseitig die Rolle `employee` und ermittelt den Datensatz über `Employee.user_id` des angemeldeten Kontos. Das Profil muss aktiv und nicht archiviert sein. Dienste und Arbeitszeiten sind zusätzlich auf das Konto zugewiesene Objekte begrenzt. Eine vom Client gelieferte Mitarbeiter-ID wird bei Anträgen nicht als Scope verwendet. Fremde Antrags- und Dokument-IDs liefern `404`; abgeschlossene Anträge können nicht geändert oder zurückgezogen werden und liefern `409`.

Das Mitarbeiterkonto erhält keine allgemeinen `documents.read`- oder `documents.download`-Berechtigungen. Ein Download über den bestehenden privaten Qualifikationsdatei-Endpunkt ist für ein Mitarbeiterkonto nur erlaubt, wenn Mitarbeiter, Qualifikation, Datei und aktives Konto zusammenpassen und eine nicht widerrufene Freigabe für genau dieses Konto vorliegt. Die Personalverwaltung benötigt für Freigaben weiterhin `employees.documents.manage`. Freigaben sind standardmäßig nicht vorhanden. Das Portal bietet keine Freigabe für allgemeine, untypisierte Personal- oder Vertragsdokumente, weil deren Kategorien keine sichere Klassifizierung erlauben.

Portalantworten enthalten weiterhin keine Kontakt-/Adressdaten, Personalakte, Gehaltsdaten, Objektadressen oder Sicherheitsdetails, Kundeninformationen, Aufgabenkommentare/-historien, interne Aufgabenbeschreibungen, Erledigungsnachweise oder Zeiterfassungs-Korrekturgründe.

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
| `PATCH /api/v1/employee-portal/me/absences/{absence_id}` | Eigenen noch offenen Abwesenheitsantrag ändern |
| `POST /api/v1/employee-portal/me/absences/{absence_id}/withdraw` | Eigenen offenen Abwesenheitsantrag nachvollziehbar zurückziehen |
| `GET /api/v1/employee-portal/me/availability-requests` | Eigene Verfügbarkeitswünsche und deren Status |
| `POST /api/v1/employee-portal/me/availability-requests` | Zeitraum als bevorzugt oder nicht verfügbar einreichen; der Server setzt den Status verbindlich auf `open` |
| `PATCH /api/v1/employee-portal/me/availability-requests/{request_id}` | Eigenen noch offenen Verfügbarkeitsantrag ändern |
| `POST /api/v1/employee-portal/me/availability-requests/{request_id}/withdraw` | Eigenen offenen Verfügbarkeitsantrag nachvollziehbar zurückziehen |
| `GET /api/v1/employee-portal/me/documents` | Nur ausdrücklich freigegebene, nicht widerrufene Qualifikationsdateien des angemeldeten Kontos |
| `GET /api/v1/employees/{employee_id}/qualifications/{qualification_id}/documents/{document_id}?download=true` | Bestehender privater Datei-Endpunkt; Mitarbeiterzugriff wird zusätzlich gegen die aktive Einzel-Freigabe geprüft und protokolliert |
| `GET /api/v1/employee-portal/document-grants?employee_id=…` | Freigaben einer Mitarbeiterin oder eines Mitarbeiters für berechtigte Personalverwaltung anzeigen |
| `POST /api/v1/employee-portal/document-grants` | Aktuelle Qualifikationsdatei ausdrücklich für das verknüpfte aktive Mitarbeiterkonto freigeben |
| `DELETE /api/v1/employee-portal/document-grants/{grant_id}` | Freigabe widerrufen; Status bleibt erhalten und wird historisiert |

Rücknahmen ändern ausschließlich den Status von `pending` beziehungsweise `open` auf `withdrawn`; Datensätze werden nicht gelöscht. Antrag-ID, Konto, Zeitpunkt und Statuswechsel werden im Audit-Verlauf festgehalten. Freigabe und Widerruf werden zusätzlich in einer append-only Historientabelle protokolliert. Eine Freigabe bleibt an das bei ihrer Erteilung verknüpfte Konto gebunden und wird bei einer späteren Kontoverknüpfung nicht übertragen.

Verfügbarkeitszeiten werden in der für die Dienstplanung konfigurierten IANA-Zeitzone erfasst (im Standard `Europe/Berlin`) und wie im bestehenden Dienstplan auf ungültige DST-Ortszeiten geprüft. Anträge werden dem verknüpften Mitarbeiterkonto zugeordnet und können über das Portal nicht selbst freigegeben werden. Die Prüfung und Entscheidung verbleibt bei den bestehenden Personal- beziehungsweise Dienstplan-Workflows. Rückfragen sind in den vorhandenen Antragsmodellen nicht speicherbar.

## Oberfläche und Grenzen

Die deutsche Portalnavigation umfasst Dienste, Aufgaben, Benachrichtigungen, Qualifikationen, freigegebene Dokumente, Arbeitszeiten sowie Abwesenheits- und Verfügbarkeitsanträge. Lade-, Fehler- und Leerzustände sind vorhanden. Kontosicherheit bleibt über die separate Navigation erreichbar.

Nicht enthalten sind strukturierte Stammdatenänderungsanträge, das Bearbeiten von Qualifikationen, Datei-Upload, Einsicht in interne Aufgabenkommentare, Dienständerungen, Zeiterfassungs-Korrekturen, allgemeine Personal- und Vertragsdokumente sowie Lohnabrechnungen. Das vorhandene Modell speichert Mitarbeiter-Stammdatenänderungen nicht als prüfbare Anträge; daher werden Änderungen nicht automatisch angewandt oder selbst genehmigt. Die Zeitübersicht ist keine Abrechnung und zeigt keine Zuschläge oder Geldbeträge. Die Oberfläche zeigt bis zu 100 neueste Zeit- und Benachrichtigungseinträge.

## Verifikation

Die Backendtests unter `backend/tests/test_employee_portal.py` decken Authentifizierung, Rollen, aktive Kontoverknüpfungen, Objekt-/Employee-IDOR, Antragsrücknahmen und -verläufe, explizite Dokumentfreigaben, Widerruf, Konto-Neuverknüpfung sowie nicht freigegebene/fremde Downloads ab. Die PostgreSQL-CI prüft die Migration einschließlich vorhandener Daten und Append-only-Trigger. Lokal prüfen:

```sh
cd backend
python -m pytest -q
ruff check app tests migrations
ruff format --check app tests migrations

cd ../frontend
npm test
npm run build
```
