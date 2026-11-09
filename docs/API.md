# API-Referenz

## Quelle, Basis und Zugriff

| Methode | Pfad | Zugriff |
|---|---|---|
| GET | `/health/live` | öffentlich, Prozessstatus |
| GET | `/health/ready` | öffentlich, Datenbankverbindung und in Produktion Redis |
| POST | `/api/v1/auth/login` | öffentlich, 5/min je vertrauenswürdiger Client-IP; MFA- oder Wiederherstellungscode falls aktiviert, in Produktion gemeinsam über Redis |
| GET | `/api/v1/auth/me` | angemeldete Sitzung |
| POST | `/api/v1/auth/logout` | angemeldet + CSRF |
| POST | `/api/v1/auth/change-password` | angemeldet + CSRF; widerruft Sitzungen |
| GET | `/api/v1/auth/sessions` | angemeldet; eigene aktive Sitzungen |
| DELETE | `/api/v1/auth/sessions/{session_id}` | eigene Sitzung oder `sessions.manage`; CSRF und Audit |
| GET | `/api/v1/users/{user_id}/sessions` | `sessions.manage`; fremde aktive Sitzungen |
| GET | `/api/v1/auth/mfa` | angemeldet; eigener MFA-Status |
| POST | `/api/v1/auth/mfa/setup`, `/enable`, `/disable` | angemeldet + CSRF; Passwort-/TOTP-Prüfung; Recovery-Codes nur einmal bei Aktivierung |
| GET | `/api/v1/users` | `users.read` |
| POST | `/api/v1/users` | `users.manage`; Administratorvergabe zusätzlich `users.manage_admin` |
| PATCH | `/api/v1/users/{user_id}` | `users.manage`; Rechte außerhalb der eigenen Berechtigungen zusätzlich `users.manage_admin` |
| POST | `/api/v1/users/{user_id}/reset-password` | `users.manage` + `users.password_reset`; Zielkonto Administrator zusätzlich `users.manage_admin`; CSRF |
| GET | `/api/v1/roles` | `roles.read` |
| GET | `/api/v1/audit-logs` | `audit.read`; Limit 1–100 |
| GET | `/api/v1/customers` | `customers.read`; `q`, `status`, `include_archived`, `sort_by`, `sort_order`, `limit`, `offset` |
| POST | `/api/v1/customers` | `customers.create` + CSRF |
| GET | `/api/v1/customers/{customer_id}` | `customers.read` |
| PATCH | `/api/v1/customers/{customer_id}` | `customers.update` + CSRF |
| GET | `/api/v1/customers/{customer_id}/history` | `customers.read`; `limit`, `offset` |
| POST | `/api/v1/customers/{customer_id}/archive` | `customers.archive` + CSRF |
| POST | `/api/v1/customers/{customer_id}/reactivate` | `customers.archive` + CSRF |
| POST | `/api/v1/customers/{customer_id}/contacts` | `customers.update` + CSRF |
| PATCH | `/api/v1/customers/{customer_id}/contacts/{contact_id}` | `customers.update` + CSRF |
| DELETE | `/api/v1/customers/{customer_id}/contacts/{contact_id}` | `customers.update` + CSRF |
| GET/POST/PATCH/DELETE | `/api/v1/customer-portal/links` und `/links/{contact_id}` | `customers.portal.manage`; manuelle eindeutige Kontaktverknüpfung, Aktivierung/Deaktivierung und Lösen + CSRF bei Änderungen |
| GET | `/api/v1/customer-portal/management-options`, `/link-history`, `/access-history` | `customers.portal.manage`; passende Konten/Kontakte sowie Zugangshistorie/Portalabrufe nur mit Metadaten |
| GET | `/api/v1/customer-portal/me`, `/invoices`, `/documents` | `customer_portal.access`; ausschließlich Daten des serverseitig verknüpften aktiven Kontakts |
| GET | `/api/v1/customer-portal/invoices/{invoice_id}/pdf`, `/documents/{grant_id}/download` | `customer_portal.access`; eigene freigegebene Rechnungs-/Dokumentdatei |
| GET | `/api/v1/customer-portal/document-candidates`, `/document-grants` | `customer_portal.documents.manage`; aktuelle geeignete Dokumente und Freigabehistorie |
| POST/DELETE | `/api/v1/customer-portal/document-grants` und `/document-grants/{grant_id}` | `customer_portal.documents.manage` + CSRF; Freigabe beziehungsweise Widerruf mit Akteurhistorie |
| GET/POST | `/api/v1/customer-portal/requests` | `customer_portal.access`; eigene Rückfragen/Beschwerden anlegen und einsehen |
| GET/POST | `/api/v1/customer-portal/requests/{request_id}/messages` | `customer_portal.access`; nur eigener Vorgang, Kundennachrichten append-only |
| POST/GET | `/api/v1/customer-portal/requests/{request_id}/attachments` und `/attachments/{attachment_id}/download` | `customer_portal.access`; eigener Vorgang, PDF/PNG/JPEG bis 10 MiB und fail-closed Malwareprüfung |
| GET | `/api/v1/customer-portal/admin/requests` und `/admin/requests/{request_id}` | `customer_portal.requests.manage`; Kundenanfragenverwaltung |
| POST/PATCH/GET | `/api/v1/customer-portal/admin/requests/{request_id}/messages`, `/status` und `/attachments/{attachment_id}/download` | `customer_portal.requests.manage`; kundensichtbare Antwort, Statusänderung und sicherer Anhangabruf |
| GET | `/api/v1/objects` | `objects.read`; `q`, `customer_id`, `status`, `include_archived`, `sort_by`, `sort_order`, `limit`, `offset` |
| POST | `/api/v1/objects` | `objects.manage` und `objects.manage_all` + CSRF |
| GET | `/api/v1/objects/{object_id}` | `objects.read` und globales Leserecht oder Objektzuweisung |
| PATCH | `/api/v1/objects/{object_id}` | `objects.manage` und globales Verwaltungsrecht oder Objektzuweisung + CSRF |
| POST | `/api/v1/objects/{object_id}/archive` | `objects.manage` und globales Verwaltungsrecht oder Objektzuweisung + CSRF |
| POST | `/api/v1/objects/{object_id}/reactivate` | `objects.manage` und globales Verwaltungsrecht oder Objektzuweisung + CSRF |
| GET | `/api/v1/objects/{object_id}/history` | `objects.read` und globales Leserecht oder Objektzuweisung |
| POST | `/api/v1/objects/{object_id}/contacts` | `objects.manage` und globales Verwaltungsrecht oder Objektzuweisung + CSRF |
| PATCH/DELETE | `/api/v1/objects/{object_id}/contacts/{contact_id}` | `objects.manage` und globales Verwaltungsrecht oder Objektzuweisung + CSRF |
| GET | `/api/v1/objects/assignment-candidates` | `objects.assign`; aktive Mitarbeiter- und Objektleitungskonten |
| GET/PUT | `/api/v1/objects/{object_id}/assignments` | `objects.assign` und globales Verwaltungsrecht oder Objektzuweisung; PUT + CSRF |
| GET | `/api/v1/objects/{object_id}/security` | `objects.sensitive.read` und globales Leserecht oder Objektzuweisung |
| PATCH | `/api/v1/objects/{object_id}/security` | `objects.sensitive.manage` und globales Verwaltungsrecht oder Objektzuweisung + CSRF |
| GET | `/api/v1/inventory/assets` | `inventory.read`; Suche/Filter/Pagination, zusätzlich auf den Objektbereich begrenzt |
| POST | `/api/v1/inventory/assets` | `inventory.manage`; Objektbereich beziehungsweise globaler Zugriff für zentrales Inventar + CSRF |
| PATCH | `/api/v1/inventory/assets/{asset_id}` | `inventory.manage` und Objektzugriff + CSRF |
| POST | `/api/v1/inventory/assets/{asset_id}/archive` | `inventory.manage` und Objektzugriff + CSRF |
| POST | `/api/v1/inventory/assets/{asset_id}/events` | `inventory.move` und Objektzugriff; Ausgabe, Rückgabe, Übergabe, Meldungen, Wartung/Reparatur + CSRF |
| GET | `/api/v1/inventory/assets/{asset_id}/events` | `inventory.read` und Objektzugriff; append-only Ereignishistorie |
| GET | `/api/v1/inventory/objects` | `inventory.read`; aktive, im eigenen Bereich erreichbare Objekte |
| GET | `/api/v1/inventory/employees` | `inventory.read`; nur aktuell zugeordnete Mitarbeiter im eigenen Objektbereich |
| GET | `/api/v1/inventory/eligible-employees` | `inventory.move`; aktive Konten mit passender Objektzuweisung |
| GET | `/api/v1/employees` | `employees.read`; `q`, `status`, `include_archived`, `sort_by`, `sort_order`, `limit`, `offset` |
| POST | `/api/v1/employees` | `employees.manage` + CSRF |
| GET | `/api/v1/employees/{employee_id}` | `employees.read` |
| PATCH | `/api/v1/employees/{employee_id}` | `employees.manage` + CSRF |
| POST | `/api/v1/employees/{employee_id}/archive` und `/reactivate` | `employees.manage` + CSRF |
| GET | `/api/v1/employees/{employee_id}/history` | `employees.read`; `limit`, `offset` |
| GET | `/api/v1/employees/linked-user-candidates` | `employees.manage`; `employee_id` optional for editing the current link |
| GET | `/api/v1/employees/object-assignment-candidates` | `employees.manage` + `objects.assign`; only objects within the caller's write scope |
| GET | `/api/v1/employees/{employee_id}/objects` | `employees.read`; active assignments through the linked user account |
| GET | `/api/v1/employees/{employee_id}/object-assignment-history` | `employees.read`; `limit`, `offset` |
| POST/DELETE | `/api/v1/employees/{employee_id}/objects/{object_id}` | `employees.manage` + `objects.assign` and object write scope; CSRF; POST assigns, DELETE ends |
| GET/POST | `/api/v1/employees/{employee_id}/qualifications` | Lesen: `employees.read`; Schreiben: `employees.manage` + CSRF |
| PATCH | `/api/v1/employees/{employee_id}/qualifications/{qualification_id}` | `employees.manage` + CSRF |
| POST | `/api/v1/employees/{employee_id}/qualifications/{qualification_id}/archive` | `employees.manage` + CSRF |
| GET | `/api/v1/employees/{employee_id}/qualification-documents` | `employees.documents.read` |
| POST | `/api/v1/employees/{employee_id}/qualifications/{qualification_id}/documents` | `employees.documents.manage` + CSRF; PDF/PNG/JPEG, max. 10 MiB |
| GET | `/api/v1/employees/{employee_id}/qualifications/{qualification_id}/documents/{document_id}` | `employees.documents.read`; `download=true` forces attachment |
| GET | `/api/v1/employees/qualifications/expiring` | `employees.read`; `days` |
| GET/POST | `/api/v1/employees/{employee_id}/absences` | Lesen: `employees.absences.read`; Schreiben: `employees.absences.manage` + CSRF |
| PATCH | `/api/v1/employees/{employee_id}/absences/{absence_id}` | `employees.absences.manage` + CSRF |
| GET | `/api/v1/employees/{employee_id}/sensitive` | `employees.sensitive.read` |
| PATCH | `/api/v1/employees/{employee_id}/sensitive` | `employees.sensitive.manage` + CSRF |
| GET | `/api/v1/scheduling/settings` | `scheduling.read` |
| PATCH | `/api/v1/scheduling/settings` | `scheduling.manage` + CSRF |
| GET | `/api/v1/scheduling/shifts` | `scheduling.read`; `from_date`, `to_date`, `employee_id`, `object_id`, `include_cancelled`, `limit`, `offset` |
| POST | `/api/v1/scheduling/shifts` | `scheduling.manage` + Objektzugriff + CSRF; legt einen Entwurf an |
| PATCH | `/api/v1/scheduling/shifts/{shift_id}` | `scheduling.manage` + Objektzugriff + CSRF |
| POST | `/api/v1/scheduling/shifts/{shift_id}/publish` oder `/cancel` | `scheduling.manage` + Objektzugriff + CSRF |
| GET | `/api/v1/scheduling/shifts/{shift_id}/history` | `scheduling.read` und sichtbarer Objekt-/Personalbereich |
| POST | `/api/v1/time-tracking/start` | `time_tracking.create` oder `time_tracking.manage`; ordnet den aktuellen veröffentlichten Dienst zu |
| POST | `/api/v1/time-tracking/entries/{entry_id}/pause`, `/resume`, `/stop` | Berechtigter Eigentümer oder `time_tracking.manage`; CSRF |
| POST | `/api/v1/time-tracking/entries/manual` | `time_tracking.manage`; abgeschlossene UTC-Segmente als einreichungspflichtiger Nachtrag; CSRF |
| GET | `/api/v1/time-tracking/entries` | `time_tracking.read_own` oder `time_tracking.read_all`; optionale Filter `from_date`, `to_date`, `employee_id`, `object_id`, `customer_id`, `status` |
| POST | `/api/v1/time-tracking/entries/{entry_id}/corrections` | Eigentümer mit `time_tracking.correct_own` oder berechtigter Verwalter mit `time_tracking.correct_all`; Grund und neue Segmente erforderlich; CSRF |
| GET | `/api/v1/time-tracking/corrections` | `time_tracking.read_all`; `pending_only` standardmäßig `true` |
| POST | `/api/v1/time-tracking/entries/{entry_id}/approve` oder `/reject` | `time_tracking.approve` beziehungsweise `time_tracking.reject`; Ablehnung mit Grund; keine Selbstfreigabe; CSRF |
| POST | `/api/v1/time-tracking/corrections/{correction_id}/approve` oder `/reject` | `time_tracking.approve` beziehungsweise `time_tracking.reject`; Ablehnung mit Grund; CSRF |
| POST | `/api/v1/time-tracking/entries/{entry_id}/lock` | `time_tracking.manage`; nur freigegebene Buchungen; CSRF |
| GET | `/api/v1/time-tracking/reports` | `time_tracking.read_own` oder `time_tracking.read_all`; Zeitraum sowie optionale Mitarbeiter-/Objekt-/Kunden-/Statusfilter, `group_by=employee|object|customer|day|week|month` |
| GET | `/api/v1/time-tracking/reports/missing` | `time_tracking.read_all`; `from_date`, `to_date`; veröffentlichte Schichten ohne Buchung |
| GET | `/api/v1/time-tracking/export.csv` | `time_tracking.export`; Zeitraum sowie optionale Mitarbeiter-/Objekt-/Kundenfilter; nur freigegebene oder gesperrte Buchungen |
| GET/PATCH | `/api/v1/time-tracking/settings` | `time_tracking.surcharges.read` / `time_tracking.surcharges.manage`; Bundesland für Feiertagskalender |
| GET/POST | `/api/v1/time-tracking/surcharge-rules` | `time_tracking.surcharges.read` / `time_tracking.surcharges.manage`; unveränderliche Regeln mit Gültigkeit, Wert, Priorität und Kombinationsmodus |
| POST/GET | `/api/v1/time-tracking/entries/{entry_id}/surcharge-calculations` | `time_tracking.surcharges.manage` / `time_tracking.surcharges.read` und sichtbarer Eintrag; Berechnung versionieren/einsehen |
| GET | `/api/v1/time-tracking/reports/surcharges` | `time_tracking.surcharges.read` und `time_tracking.read_all`; aktueller, nicht veralteter Berechnungsnachweis je Buchung |
| GET | `/api/v1/time-tracking/export-surcharges.csv` | `time_tracking.export` und `time_tracking.surcharges.read`; freigegebene Zuschlagsnachweise |
| GET/POST | `/api/v1/time-tracking/periods` und `/periods/lock` | `time_tracking.periods.read` / `time_tracking.periods.lock`; endgültige Abrechnungsperiodensperren |
| GET | `/api/v1/owks/objects` | `owks.read`; nur aktive, berechtigte oder zugewiesene Objekte |
| GET/POST | `/api/v1/owks/objects/{object_id}/control-points` | Lesen: `owks.read`; Anlegen: `owks.manage`; Kennung wird nur bei Anlage einmal zurückgegeben |
| GET/POST | `/api/v1/owks/objects/{object_id}/routes` | Lesen: `owks.read`; Anlegen: `owks.manage`; Route darf nur Kontrollpunkte desselben Objekts enthalten |
| POST | `/api/v1/owks/objects/{object_id}/challenges` und `/api/v1/owks/scans` | `owks.write`; kurzlebige, benutzer-/objektgebundene Einmal-Challenge und QR-/NFC-Kontrollprüfung |
| GET | `/api/v1/owks/objects/{object_id}/events` | `owks.read`; Ereignisse, Übergaben, Kontrollen, Status und Konflikte |
| POST | `/api/v1/owks/events` und `/events/sync` | `owks.write`; Ereignis mit Idempotenzschlüssel; Offline-Kontrollscans werden als sichtbare Konflikte gespeichert, nicht als verifiziert gewertet |
| POST | `/api/v1/owks/events/{event_id}/status` und `/corrections` | `owks.manage`; Statusänderungen und begründete Korrekturen werden angehängt, Originalereignisse bleiben unverändert |
| POST/GET | `/api/v1/owks/events/{event_id}/attachments` und `/attachments/{attachment_id}` | Schreiben: `owks.write`; Lesen: `owks.read`; PDF/PNG/JPEG, maximal 10 MiB, Objektzugriff serverseitig geprüft |
| POST | `/api/v1/owks/routes/{route_id}/monitor` | `owks.manage`; löst dieselbe idempotente Prüfung wie der eingebaute Minuten-Monitor aus |
| GET | `/api/v1/dashboard` | `dashboard.read` |

## Kundenportal-Endpunkte (PR #42, in `main`)

| Methode | Pfad | Zugriff |
|---|---|---|
| GET | `/api/v1/customer-portal/me` | `customer_portal.access`; nur eigener verknüpfter Kontakt, Kunde und nicht archivierte Objekte |
| GET | `/api/v1/customer-portal/invoices` | `customer_portal.access`; höchstens 100 eigene, nicht archivierte Rechnungen mit Status `approved` |
| GET | `/api/v1/customer-portal/invoices/{invoice_id}/pdf` | `customer_portal.access`; eigene freigegebene Rechnung; Download wird auditiert |
| GET | `/api/v1/customer-portal/links` | `customers.portal.manage`; aktive Portalverknüpfungen |
| POST | `/api/v1/customer-portal/links` | `customers.portal.manage`; manuelle eindeutige Benutzer-/Kontaktverknüpfung |
| DELETE | `/api/v1/customer-portal/links/{contact_id}` | `customers.portal.manage`; Verknüpfung lösen, Historie und Audit bleiben erhalten |

Kundenlisten blenden archivierte Datensätze standardmäßig aus. Sie können nach Kundenstatus (`status`) und Vertragsstatus (`contract_status`) filtern. Die Sortierfelder sind `company_name`, `customer_number`, `created_at`, `status` und `contract_status`; die Sortierrichtung ist `asc` oder `desc`. Die Suche berücksichtigt Kunden-, Kontakt-, Anschrift- und Websitedaten.

Inventarwerte, zulässige Vorgänge und Objektbereichsregeln sind in [`INVENTORY.md`](INVENTORY.md) dokumentiert. Physische Einzelschlüssel bleiben im separaten Schlüsselregister; Inventarereignisse sind append-only.

Kunden können Geschäfts- und Rechnungsanschrift, Rechtsform, Website, Vertragsstatus, Umsatzsteuer-ID, Steuernummer und interne Notizen enthalten. Websites müssen HTTP- oder HTTPS-URLs sein. Vertragsstatuswerte: `none` (kein Vertrag), `draft` (in Vorbereitung), `active` (aktiv), `expired` (abgelaufen), `terminated` (beendet). Ansprechpartner werden separat verwaltet; pro Kunde kann höchstens einer als primär markiert sein. Kunden werden archiviert statt physisch gelöscht. Historieneinträge speichern Ereignis, Akteur, Zeitpunkt und geänderte Feldnamen; das Audit-Protokoll hält dieselben geänderten Bereiche fest, aber keine vorherigen/neuen Feldwerte.

Dieses API-Inventar ist eine historische Momentaufnahme vom 09.11.2026 auf Basis von `main` SHA `a8cc63b3eeef9cbcdc033e4156ca046c14e8c99a` (Main-Commit um 07:51 UTC, vor PR #40). Es wurde aus `backend/app/main.py`, den dort registrierten Routern und dem generierten FastAPI-OpenAPI-Schema erstellt. Versionierung: `/api/v1`. OpenAPI/Swagger: `/docs`. Das Schema enthält 190 Operationen unter `/api/v1` sowie zwei Health-Operationen außerhalb des Präfixes. OWKS (PR #23), Dokumente/Verträge (PR #24), Dienstplan-Verfügbarkeiten/Vertretungen (PR #26), Rechnungswesen (PR #27), MFA/Sitzungsverwaltung (PR #31), Upload-Prüfung (PR #33), Aufgaben (PR #34), In-App-Aufgabenbenachrichtigungen (PR #35), Schlüsselverwaltung (PR #36), Vorfallmanagement (PR #37), Leitstellenübersicht (PR #38) und Notification-/OWKS-Worker (PR #39) waren gemergt. Der Worker ist kein HTTP-Router und ändert die OpenAPI-Zählung nicht; PR #25 war zum damaligen Prüfzeitpunkt offen. Der aktuelle PR-Status steht in [`PROJECT_STATUS.md`](PROJECT_STATUS.md).

Außer `/health/live`, `/health/ready` und `/api/v1/auth/login` sind Endpunkte sitzungsgebunden. Schreibende authentifizierte Requests benötigen zusätzlich den CSRF-Cookie und `X-CSRF-Token` mit demselben Tokenwert; die Sitzung enthält nur Token-Hashes. „Scope“ meint eine zusätzliche serverseitige Bereichsprüfung, nicht ein Ersatzrecht. Die Rechtedaten werden aus Rollen im Backend geladen.

**Allgemeine Fehler:** fehlende/ungültige Sitzung `401`; fehlendes Recht oder CSRF-Fehler `403`; fehlende Ressource bzw. bei Scope-Schutz teils absichtlich verborgene Ressource `404`; Status-/Integritätskonflikt häufig `409`; Validierungsfehler `422`. Login-Limit `429`. Health-Readiness bei DB- oder Redis-Ausfall `503`. Uploads können bei Malware-Erkennung `422`, bei Überschreiten des Scannerlimits `413` sowie bei Scanner-/Protokollfehlern, Timeout oder Nichterreichbarkeit `503` liefern; Details: [`UPLOAD_SECURITY.md`](UPLOAD_SECURITY.md). Nicht jede dieser Antworten ist im OpenAPI-Schema als eigene Response modelliert; `HTTPValidationError`/`422` ist dort für viele validierte Parameter und Bodies ausgewiesen.

`GET /api/v1/...`-Antworten sind JSON, sofern unten nicht CSV/Datei steht. `[]` bedeutet JSON-Array, `Page` paginierte Antwort. Body-Namen verweisen auf Pydantic-Schemas in `backend/app/schemas.py`; Upload nutzt multipart/form-data. Erfolgsstatus und Response-Schema folgen dem OpenAPI-Output. Parameter in der Spalte **Eingabe** sind zusätzliche Queryparameter und JSON-/Multipart-Bodys; Pfad-IDs stehen im jeweiligen Pfad.

## Kundenportal (PR #42, in `main`)

Die folgenden Routen beschreiben die Portal-Erweiterung aus PR #42. Das historische API-Inventar oben bildet den damaligen Stand von `main` ab. Kundenendpunkte verwenden ausschließlich das serverseitig verknüpfte aktive Portal-Konto und den damit verbundenen Kontakt/Kunden. Ein vom Client übermittelter Kunden- oder Kontaktbezug begründet keinen Zugriff. Kundenkonten erhalten keine allgemeinen Kunden-, Dokument-, Vorfall- oder Personalrechte. Schreibende Requests benötigen Sitzung und CSRF-Token.

| Methode und Route | Recht / Bereich | Eingabe | Erfolg / Response |
|---|---|---|---|
| `GET /api/v1/customer-portal/me` | `customer_portal.access`; eigener verknüpfter Kontakt, Kunde und nicht archivierte Kundenobjekte | – | `200 CustomerPortalMeRead` |
| `GET /api/v1/customer-portal/invoices` | `customer_portal.access`; ausschließlich freigegebene Rechnungen des verknüpften Kunden | – | `200 CustomerPortalInvoiceRead[]` |
| `GET /api/v1/customer-portal/invoices/{invoice_id}/pdf` | `customer_portal.access`; ausschließlich freigegebene Rechnung des verknüpften Kunden | Pfad `invoice_id` | `200 application/pdf` |
| `GET /api/v1/customer-portal/documents` | `customer_portal.access`; explizit freigegebene aktuelle Versionen, begrenzt auf den verknüpften Kunden | – | `200 CustomerPortalDocumentRead[]` |
| `GET /api/v1/customer-portal/documents/{grant_id}/download` | `customer_portal.access`; aktive Freigabe und Kunden-/Objektzugehörigkeit werden serverseitig geprüft | Pfad `grant_id` | `200` Datei |
| `GET /api/v1/customer-portal/requests` | `customer_portal.access`; eigene Anfragen des verknüpften Kontakts | – | `200 CustomerPortalRequestRead[]` |
| `POST /api/v1/customer-portal/requests` | `customer_portal.access`; aktives Objekt desselben Kunden | `CustomerPortalRequestCreate` | `201 CustomerPortalRequestRead` |
| `GET /api/v1/customer-portal/requests/{request_id}` | `customer_portal.access`; eigene Anfrage | Pfad `request_id` | `200 CustomerPortalRequestRead` inklusive Nachrichten und Verlauf |
| `POST /api/v1/customer-portal/requests/{request_id}/messages` | `customer_portal.access`; eigene Anfrage | `CustomerPortalRequestMessageCreate` | `201 CustomerPortalRequestMessageRead` |
| `POST /api/v1/customer-portal/requests/{request_id}/attachments` | `customer_portal.access`; eigene Anfrage; privater Speicher, Typ-/Größenprüfung und fail-closed ClamAV | Multipart `file` | `201 CustomerPortalRequestAttachmentRead` |
| `GET /api/v1/customer-portal/requests/{request_id}/attachments/{attachment_id}/download` | `customer_portal.access`; eigener Anfrageanhang | Pfad-IDs | `200` Datei |
| `GET /api/v1/customer-portal/links` | `customers.portal.manage` | – | `200 CustomerPortalLinkRead[]` |
| `GET /api/v1/customer-portal/management-options` | `customers.portal.manage` | – | `200 CustomerPortalManagementOptions` |
| `GET /api/v1/customer-portal/link-history` | `customers.portal.manage` | – | `200 CustomerPortalLinkHistoryRead[]` |
| `GET /api/v1/customer-portal/access-history` | `customers.portal.manage`; notwendige Zugriff-Metadaten, keine Inhalte | – | `200 CustomerPortalAccessEventRead[]` |
| `POST /api/v1/customer-portal/links` | `customers.portal.manage`; eindeutige aktive Benutzer-/Kontakt-Verknüpfung | `CustomerPortalLinkCreate` | `201 CustomerPortalLinkRead` |
| `PATCH /api/v1/customer-portal/links/{contact_id}` | `customers.portal.manage`; Verknüpfung aktivieren/deaktivieren | `CustomerPortalLinkStateUpdate` | `200 CustomerPortalLinkRead` |
| `DELETE /api/v1/customer-portal/links/{contact_id}` | `customers.portal.manage`; Verknüpfung aufheben, Historie bleibt erhalten | Pfad `contact_id` | `204` |
| `GET /api/v1/customer-portal/document-candidates` | `customer_portal.documents.manage`; geeignete nicht-personenbezogene Dokumente | – | `200 CustomerPortalDocumentCandidateRead[]` |
| `GET /api/v1/customer-portal/document-grants` | `customer_portal.documents.manage` | Query `document_id` | `200 CustomerPortalDocumentGrantRead[]` |
| `POST /api/v1/customer-portal/document-grants` | `customer_portal.documents.manage`; explizite Freigabe aktueller geeigneter Version | `CustomerPortalDocumentGrantCreate` | `201 CustomerPortalDocumentGrantRead` |
| `DELETE /api/v1/customer-portal/document-grants/{grant_id}` | `customer_portal.documents.manage`; Freigabe widerrufen, Historie bleibt erhalten | Pfad `grant_id` | `200 CustomerPortalDocumentGrantRead` |
| `GET /api/v1/customer-portal/admin/requests` | `customer_portal.requests.manage` | – | `200 CustomerPortalRequestRead[]` |
| `GET /api/v1/customer-portal/admin/requests/{request_id}` | `customer_portal.requests.manage` | Pfad `request_id` | `200 CustomerPortalRequestRead` |
| `POST /api/v1/customer-portal/admin/requests/{request_id}/messages` | `customer_portal.requests.manage` | `CustomerPortalRequestMessageCreate` | `201 CustomerPortalRequestMessageRead` |
| `PATCH /api/v1/customer-portal/admin/requests/{request_id}/status` | `customer_portal.requests.manage`; nur unterstützte Statuswerte, append-only Verlauf | `CustomerPortalRequestStatusUpdate` | `200 CustomerPortalRequestRead` |
| `GET /api/v1/customer-portal/admin/requests/{request_id}/attachments/{attachment_id}/download` | `customer_portal.requests.manage` | Pfad-IDs | `200` Datei |

## System und Anmeldung

| Methode und Route | Recht / Bereich | Eingabe | Erfolg / Response | Wesentliche Fehler |
|---|---|---|---|---|
| `GET /health/live` | öffentlich | – | `200` JSON `{status}` | – |
| `GET /health/ready` | öffentlich | – | `200` JSON `{status}` | `503` DB oder Redis nicht verfügbar |
| `POST /api/v1/auth/login` | öffentlich; SlowAPI `5/minute` pro Client-IP; Redis-Speicher in Produktion | `LoginRequest` (`mfa_code` oder `recovery_code` optional, nicht kombinierbar) | `200 SessionRead`; setzt Session- und CSRF-Cookie, enthält `password_change_required` | `401` generische Anmeldedaten-/MFA-Meldung; `429`; `422` |
| `GET /api/v1/auth/me` | gültige Sitzung | – | `200 SessionRead` | `401` |
| `POST /api/v1/auth/logout` | gültige Sitzung + CSRF | – | `204` leer; Sitzung widerrufen | `401`, `403` |
| `POST /api/v1/auth/change-password` | gültige Sitzung + CSRF | `PasswordChange` | `204` leer; alle Sitzungen des Kontos werden widerrufen | `400` aktuelles Passwort falsch; `422` ungültige/neue gleiche Passphrase; `401`, `403` |
| `GET /api/v1/auth/sessions` | gültige Sitzung; eigene noch gültige Sitzungen | – | `200 UserSessionRead[]` mit Zeiten, IP/User-Agent und Kennzeichnung der aktuellen Sitzung | `401` |
| `DELETE /api/v1/auth/sessions/{session_id}` | gültige Sitzung; eigene Sitzung oder `sessions.manage` + CSRF | Pfad `session_id` | `204` leer; widerruft Sitzung und löscht aktuelle Cookies beim Widerruf der eigenen Sitzung | `401`, `403`, `404` |
| `GET /api/v1/users/{user_id}/sessions` | `sessions.manage` | Pfad `user_id` | `200 UserSessionRead[]` | `401`, `403`, `404` |
| `GET /api/v1/auth/mfa` | gültige Sitzung | – | `200 MFAStatusRead` | `401` |
| `POST /api/v1/auth/mfa/setup` | gültige Sitzung + CSRF; SlowAPI `5/minute` | `MFASetupRequest` (aktuelles Passwort) | `200 MFASetupRead` (TOTP-Secret und `otpauth_uri`) | `400` falsches Passwort; `401`, `403`, `409` bereits aktiviert, `422`, `429` |
| `POST /api/v1/auth/mfa/enable` | gültige Sitzung + CSRF; SlowAPI `5/minute` | `MFAEnableRequest` (6-stelliger TOTP-Code) | `200 MFARecoveryCodesRead`; Wiederherstellungscodes einmalig angezeigt | `400` ungültiger/abgelaufener Code; `401`, `403`, `409` Einrichtung fehlt, `422`, `429` |
| `POST /api/v1/auth/mfa/disable` | gültige Sitzung + CSRF; SlowAPI `5/minute` | `MFADisableRequest` (Passwort und 6-stelliger TOTP-Code) | `204` leer | `400` Passwort/Code ungültig; `401`, `403`, `409` MFA nicht aktiv, `422`, `429` |
| `POST /api/v1/users/{user_id}/reset-password` | `users.password_reset` + `users.manage`; bei Zielkonto mit Administratorrechten zusätzlich `users.manage_admin`; CSRF; SlowAPI `5/minute` | Pfad `user_id`, `AdminPasswordReset` (Übergangspasswort, 12–128 Zeichen) | `204` leer; setzt Passwortwechselpflicht und widerruft Sitzungen | `401`, `403`, `404`, `409` eigenes Konto, `422`, `429` |
| `GET /api/v1/roles` | `roles.read` | – | `200 RoleRead[]` | `401`, `403` |
| `GET /api/v1/users` | `users.read` | – | `200 UserRead[]` | `401`, `403` |
| `POST /api/v1/users` | `users.manage`; Administratorrolle zusätzlich `users.manage_admin`; CSRF | `UserCreate` | `201 UserRead` | `403`, `409` Benutzername/E-Mail belegt, `422` unbekannte Rolle/Validierung |
| `PATCH /api/v1/users/{user_id}` | `users.manage`; Änderungen an Administratorrechten zusätzlich `users.manage_admin`; CSRF | `UserUpdate` | `200 UserRead` | `404`, `403`, `409` eigenes Konto/letzter aktiver Admin, `422` |
| `GET /api/v1/audit-logs` | `audit.read` | `limit` (1–100, Standard 50) | `200 AuditLogRead[]` | `401`, `403`, `422` |
| `GET /api/v1/dashboard` | `dashboard.read` | – | `200 DashboardRead` | `401`, `403` |
| `GET /api/v1/control-room` | `control_room.read` und `objects.read`; zusätzlich je Datenquelle deren Fachrecht und Objekt-/Personenbereich | Query `object_id` (optional UUID), `from_date`/`to_date` (optionale ISO-Daten; Standard: UTC-heute −7 Tage bis UTC-heute +30 Tage) | `200 ControlRoomRead`: `generated_at`, Zeitraum, Zählwerte und erreichbare aktive Objekte; optionale Listen für laufende Schichten, offene OWKS-Ereignisse, Vorfälle ohne sensible Details, Aufgaben, Abwesenheiten, Qualifikationen und Rechnungsfreigaben. Je Liste max. 100 Einträge; Kennzahlen zählen alle passenden Datensätze | `401`, `403` fehlendes Recht, `404` nicht erreichbares Objekt, `422` ungültiger/umgekehrter Zeitraum oder mehr als 367 Tage |

Die Leitstelle berechnet eine Momentaufnahme und pollt nicht automatisch. Die konkrete Quellenauswahl, Rechte je Datenquelle und ausgeschlossene Kategorien sind in [`CONTROL_ROOM.md`](CONTROL_ROOM.md) dokumentiert. Die Migration `0023_control_room_permission` fügt das Recht hinzu, keine Tabelle.

## Kunden

| Methode und Route | Recht / Bereich | Eingabe | Erfolg / Response | Wesentliche Fehler |
|---|---|---|---|---|
| `GET /api/v1/customers` | `customers.read` | `q`, `status`, `contract_status`, `include_archived`, `sort_by`, `sort_order`, `limit` (1–100), `offset` | `200 CustomerPage` | `401`, `403`, `422` |
| `POST /api/v1/customers` | `customers.create` + CSRF | `CustomerCreate` | `201 CustomerRead` | `401`, `403`, `422` |
| `GET /api/v1/customers/{customer_id}` | `customers.read` | – | `200 CustomerRead` | `401`, `403`, `404` |
| `PATCH /api/v1/customers/{customer_id}` | `customers.update` + CSRF | `CustomerUpdate` | `200 CustomerRead` | `401`, `403`, `404`, `409` archivierter Kunde, `422` |
| `GET /api/v1/customers/{customer_id}/history` | `customers.read` | `limit` (1–100, Standard 50), `offset` | `200 CustomerHistoryRead[]` | `401`, `403`, `404`, `422` |
| `POST /api/v1/customers/{customer_id}/archive` | `customers.archive` + CSRF | – | `200 CustomerRead` | `401`, `403`, `404`, `409` bereits archiviert |
| `POST /api/v1/customers/{customer_id}/reactivate` | `customers.archive` + CSRF | – | `200 CustomerRead` | `401`, `403`, `404`, `409` nicht archiviert |
| `POST /api/v1/customers/{customer_id}/contacts` | `customers.update` + CSRF | `CustomerContactCreate` | `201 CustomerContactRead` | `401`, `403`, `404`, `422` |
| `PATCH /api/v1/customers/{customer_id}/contacts/{contact_id}` | `customers.update` + CSRF | `CustomerContactUpdate` | `200 CustomerContactRead` | `401`, `403`, `404`, `422` |
| `DELETE /api/v1/customers/{customer_id}/contacts/{contact_id}` | `customers.update` + CSRF | – | `204` leer | `401`, `403`, `404` |

Kundenlisten standardmäßig ohne archivierte Einträge. Sortierfelder: `company_name`, `customer_number`, `created_at`, `status`, `contract_status`; Richtung `asc|desc`. Kundennummern werden serverseitig erzeugt. Der Vertragsstatus ist ein Statusfeld, keine Vertragsverwaltung.

## Objekte

`objects.read`-Zugriff ohne `objects.read_all` wird auf zugewiesene Objekte beschränkt. Schreibzugriff erfordert zusätzlich den Objektbereich; neue Objekte können ausschließlich mit globalem `objects.manage_all` angelegt werden.

| Methode und Route | Recht / Bereich | Eingabe | Erfolg / Response | Wesentliche Fehler |
|---|---|---|---|---|
| `GET /api/v1/objects` | `objects.read`; Zuweisung falls kein `objects.read_all` | `q`, `customer_id`, `status`, `include_archived`, `sort_by`, `sort_order`, `limit` (1–100), `offset` | `200 ObjectPage` | `401`, `403`, `422` |
| `POST /api/v1/objects` | `objects.manage` + `objects.manage_all` + CSRF | `ObjectCreate` | `201 ObjectRead` | `401`, `403`, `404` Kunde, `409` archivierter Kunde/Code, `422` |
| `GET /api/v1/objects/{object_id}` | `objects.read` + Objekt-Scope | – | `200 ObjectRead` | `401`, `403`, `404` |
| `PATCH /api/v1/objects/{object_id}` | `objects.manage` + Schreib-Scope + CSRF | `ObjectUpdate` | `200 ObjectRead` | `401`, `403`, `404`, `409` archiviert/Code/Kunde, `422` |
| `POST /api/v1/objects/{object_id}/archive` | `objects.manage` + Schreib-Scope + CSRF | – | `200 ObjectRead` | `401`, `403`, `404`, `409` |
| `POST /api/v1/objects/{object_id}/reactivate` | `objects.manage` + Schreib-Scope + CSRF | – | `200 ObjectRead` | `401`, `403`, `404`, `409` |
| `GET /api/v1/objects/{object_id}/history` | `objects.read` + Objekt-Scope | `limit` (1–100, Standard 50), `offset` | `200 ObjectHistoryRead[]` | `401`, `403`, `404`, `422` |
| `GET /api/v1/objects/assignment-candidates` | `objects.assign` | – | `200 ObjectAssignmentCandidateRead[]` | `401`, `403` |
| `GET /api/v1/objects/{object_id}/assignments` | `objects.assign` + Objekt-Schreib-Scope | – | `200 ObjectAssignmentRead[]` | `401`, `403`, `404` |
| `PUT /api/v1/objects/{object_id}/assignments` | `objects.assign` + Objekt-Schreib-Scope + CSRF | `ObjectAssignmentUpdate` | `200 ObjectAssignmentRead[]` | `401`, `403`, `404`, `422` ungültige/inoffizielle Konten |
| `GET /api/v1/objects/{object_id}/security` | `objects.sensitive.read` + Objekt-Scope | – | `200 ObjectSecurityRead` | `401`, `403`, `404` |
| `PATCH /api/v1/objects/{object_id}/security` | `objects.sensitive.manage` + Schreib-Scope + CSRF | `ObjectSecurityUpdate` | `200 ObjectSecurityRead` | `401`, `403`, `404`, `409` archiviert, `422` |
| `POST /api/v1/objects/{object_id}/contacts` | `objects.manage` + Schreib-Scope + CSRF | `ObjectContactCreate` | `201 ObjectContactRead` | `401`, `403`, `404`, `409`, `422` |
| `PATCH /api/v1/objects/{object_id}/contacts/{contact_id}` | `objects.manage` + Schreib-Scope + CSRF | `ObjectContactUpdate` | `200 ObjectContactRead` | `401`, `403`, `404`, `409`, `422` |
| `DELETE /api/v1/objects/{object_id}/contacts/{contact_id}` | `objects.manage` + Schreib-Scope + CSRF | – | `204` leer | `401`, `403`, `404` |

`ObjectRead` und Listen enthalten keine Sicherheits-/Zutrittsdaten; diese sind auf die `/security`-Routen begrenzt. Such-/Sortierfelder sind im jeweiligen OpenAPI-Schema und in `api.py` definiert.

## Personal, Qualifikationen und Abwesenheiten

Mitarbeiter-Objektzuweisungen und deren Historie werden auf Objekte mit `objects.read_all` oder die dem aufrufenden Konto zugewiesenen Objekte beschränkt. Verwaltung benötigt `employees.manage` und `objects.assign`; das Zielobjekt muss im eigenen Objektbereich liegen, sofern nicht `objects.manage_all` vorliegt.

| Methode und Route | Recht / Bereich | Eingabe | Erfolg / Response | Wesentliche Fehler |
|---|---|---|---|---|
| `GET /api/v1/employees` | `employees.read` | `q`, `status`, `include_archived`, `sort_by`, `sort_order`, `limit` (1–100), `offset` | `200 EmployeePage` | `401`, `403`, `422` |
| `POST /api/v1/employees` | `employees.manage` + CSRF | `EmployeeCreate` | `201 EmployeeRead` | `401`, `403`, `409` Personalnummer/Verknüpfung, `422` |
| `GET /api/v1/employees/{employee_id}` | `employees.read` | – | `200 EmployeeRead` | `401`, `403`, `404` |
| `PATCH /api/v1/employees/{employee_id}` | `employees.manage` + CSRF | `EmployeeUpdate` | `200 EmployeeRead` | `401`, `403`, `404`, `409` Zuordnung/Personalnummer, `422` |
| `POST /api/v1/employees/{employee_id}/archive` | `employees.manage` + CSRF | – | `200 EmployeeRead`; beendet aktive Objektzuweisungen | `401`, `403`, `404`, `409` |
| `POST /api/v1/employees/{employee_id}/reactivate` | `employees.manage` + CSRF | – | `200 EmployeeRead` | `401`, `403`, `404`, `409` |
| `GET /api/v1/employees/{employee_id}/history` | `employees.read` | `limit` (1–100, Standard 50), `offset` | `200 EmployeeHistoryRead[]` | `401`, `403`, `404`, `422` |
| `GET /api/v1/employees/linked-user-candidates` | `employees.manage` | optional `employee_id` | `200 EmployeeAccountCandidateRead[]` | `401`, `403`, `404`, `422` |
| `GET /api/v1/employees/object-assignment-candidates` | `employees.manage` + `objects.assign`; `objects.manage_all` oder eigener Objektbereich | – | `200 EmployeeObjectCandidateRead[]` | `401`, `403` |
| `GET /api/v1/employees/{employee_id}/objects` | `employees.read` + Objekt-Scope | – | `200 EmployeeObjectAssignmentRead[]` (nur sichtbare Objekte) | `401`, `403`, `404` |
| `GET /api/v1/employees/{employee_id}/object-assignment-history` | `employees.read` + Objekt-Scope | `limit` (1–100, Standard 50), `offset` | `200 EmployeeObjectAssignmentHistoryRead[]` (nur sichtbare Objekte) | `401`, `403`, `404`, `422` |
| `POST /api/v1/employees/{employee_id}/objects/{object_id}` | `employees.manage` + `objects.assign`; `objects.manage_all` oder eigener Objektbereich + CSRF | – | `201 EmployeeObjectAssignmentRead[]` | `401`, `403`, `404`, `409` bereits zugeordnet/inaktiv, `422` |
| `DELETE /api/v1/employees/{employee_id}/objects/{object_id}` | `employees.manage` + `objects.assign`; `objects.manage_all` oder eigener Objektbereich + CSRF | – | `200 EmployeeObjectAssignmentRead[]` | `401`, `403`, `404` |
| `GET /api/v1/employees/qualifications/expiring` | `employees.read` | `days` (0–365, Standard 30) | `200 EmployeeQualificationExpiringRead[]` | `401`, `403`, `422` |
| `GET /api/v1/employees/{employee_id}/qualifications` | `employees.read` | `include_archived` | `200 EmployeeQualificationRead[]` | `401`, `403`, `404` |
| `POST /api/v1/employees/{employee_id}/qualifications` | `employees.manage` + CSRF | `EmployeeQualificationCreate` | `201 EmployeeQualificationRead` | `401`, `403`, `404`, `422` |
| `PATCH /api/v1/employees/{employee_id}/qualifications/{qualification_id}` | `employees.manage` + CSRF | `EmployeeQualificationUpdate` | `200 EmployeeQualificationRead` | `401`, `403`, `404`, `422` |
| `POST /api/v1/employees/{employee_id}/qualifications/{qualification_id}/archive` | `employees.manage` + CSRF | – | `200 EmployeeQualificationRead` | `401`, `403`, `404`, `409` |
| `GET /api/v1/employees/{employee_id}/qualification-documents` | `employees.documents.read` | – | `200 EmployeeQualificationDocumentRead[]` | `401`, `403`, `404` |
| `POST /api/v1/employees/{employee_id}/qualifications/{qualification_id}/documents` | `employees.documents.manage` + CSRF | multipart `file` (PDF/PNG/JPEG, max. 10 MiB) | `201 EmployeeQualificationDocumentRead` | `401`, `403`, `404`, `409`, `413`/`422` Uploadprüfung |
| `GET /api/v1/employees/{employee_id}/qualifications/{qualification_id}/documents/{document_id}` | `employees.documents.read` | `download` (bool) | `200` Binärdatei, autorisierte Auslieferung | `401`, `403`, `404`, `422` |
| `GET /api/v1/employees/{employee_id}/absences` | `employees.absences.read` | – | `200 EmployeeAbsenceRead[]` | `401`, `403`, `404` |
| `POST /api/v1/employees/{employee_id}/absences` | `employees.absences.manage` + CSRF | `EmployeeAbsenceCreate` | `201 EmployeeAbsenceRead` | `401`, `403`, `404`, `422` |
| `PATCH /api/v1/employees/{employee_id}/absences/{absence_id}` | `employees.absences.manage` + CSRF | `EmployeeAbsenceUpdate` | `200 EmployeeAbsenceRead` | `401`, `403`, `404`, `409`, `422` |
| `GET /api/v1/employees/{employee_id}/sensitive` | `employees.sensitive.read` | – | `200 EmployeeSensitiveRead` | `401`, `403`, `404` |
| `PATCH /api/v1/employees/{employee_id}/sensitive` | `employees.sensitive.manage` + CSRF | `EmployeeSensitiveUpdate` | `200 EmployeeSensitiveRead` | `401`, `403`, `404`, `422` |

Allgemeine Personalantworten enthalten keine Anschrift, Notfallkontakt- oder internen Notizfelder. Datei-Uploadvalidierung prüft Größe, Dateiendung, gemeldeten MIME-Typ und Signatur; neue Qualifikationsdateien werden zusätzlich fail-closed mit ClamAV gescannt. Anwendungsebene-Verschlüsselung und rückwirkender Bestandsscan fehlen.

## Dienstplanung

| Methode und Route | Recht / Bereich | Eingabe | Erfolg / Response | Wesentliche Fehler |
|---|---|---|---|---|
| `GET /api/v1/scheduling/settings` | `scheduling.read` | – | `200 ScheduleSettingsRead` | `401`, `403` |
| `PATCH /api/v1/scheduling/settings` | `scheduling.manage` + CSRF | `ScheduleSettingsUpdate` | `200 ScheduleSettingsRead` | `401`, `403`, `422` ungültige IANA-Zeitzone/Einstellungen |
| `GET /api/v1/scheduling/shifts` | `scheduling.read` + Personal-/Objekt-Scope | `from_date`, `to_date` (gemeinsam, max. 367 Kalendertage), `employee_id`, `object_id`, `include_cancelled`, `limit` (1–500), `offset` | `200 ScheduleShiftRead[]` | `401`, `403`, `422` |
| `POST /api/v1/scheduling/shifts` | `scheduling.manage` + Objekt-/Personal-Scope + CSRF | `ScheduleShiftCreate` (lokale Datumszeiten, fold-Werte, Mitarbeiter/Objekt) | `201 ScheduleShiftRead` | `401`, `403`, `404`, `409` Konflikt, `422` Zeit/Regelverletzung |
| `PATCH /api/v1/scheduling/shifts/{shift_id}` | `scheduling.manage` + Objekt-/Personal-Scope + CSRF | `ScheduleShiftUpdate` | `200 ScheduleShiftRead` | `401`, `403`, `404`, `409`, `422` |
| `POST /api/v1/scheduling/shifts/{shift_id}/publish` | `scheduling.manage` + Objekt-/Personal-Scope + CSRF | – | `200 ScheduleShiftRead` | `401`, `403`, `404`, `409` Konflikt, `422` |
| `POST /api/v1/scheduling/shifts/{shift_id}/cancel` | `scheduling.manage` + Objekt-/Personal-Scope + CSRF | – | `200 ScheduleShiftRead` | `401`, `403`, `404`, `422` |
| `GET /api/v1/scheduling/shifts/{shift_id}/history` | `scheduling.read` + Objekt-/Personal-Scope | `limit` (1–100, Standard 50), `offset` | `200 ScheduleShiftHistoryRead[]` | `401`, `403`, `404`, `422` |
| `GET /api/v1/scheduling/employees/{employee_id}/availability` | `scheduling.read` + Mitarbeiter-Scope | Pfad `employee_id` | `200 EmployeeAvailabilityWindowRead[]` | `401`, `403`, `404` |
| `PUT /api/v1/scheduling/employees/{employee_id}/availability` | `scheduling.manage` + CSRF | Pfad `employee_id`, `EmployeeAvailabilityUpdate` | `200 EmployeeAvailabilityWindowRead[]` | `401`, `403`, `404`, `409` bestehende Dienste, `422` |
| `GET /api/v1/scheduling/availability-requests` | `scheduling.read`; eigene Anträge, außer mit `employees.read` oder `scheduling.manage` | `from_date`, `to_date` (gemeinsam), `employee_id`, `limit` (1–500), `offset` | `200 ScheduleAvailabilityRequestRead[]` | `401`, `403`, `422` |
| `POST /api/v1/scheduling/availability-requests` | `scheduling.availability.request` + CSRF; eigener Mitarbeiter oder mit `scheduling.manage` anderer Mitarbeiter | `ScheduleAvailabilityRequestCreate` (lokale Datumszeiten/Fold, Typ, optional Mitarbeiter) | `201 ScheduleAvailabilityRequestRead` | `401`, `403`, `404`, `409` archiviert, `422` |
| `PATCH /api/v1/scheduling/availability-requests/{request_id}` | `scheduling.manage` + CSRF | Pfad `request_id`, `ScheduleAvailabilityRequestUpdate` | `200 ScheduleAvailabilityRequestRead` | `401`, `403`, `404`, `409` Sperrzeit kollidiert mit Schicht, `422` |
| `POST /api/v1/scheduling/shifts/{shift_id}/replacement` | `scheduling.manage` + Objekt-/Personal-Scope + CSRF | Pfad `shift_id`, `ScheduleShiftReplacementCreate` (Vertretung, Begründung) | `200 ScheduleShiftRead`; Historieneintrag mit Vertretungsdetails | `401`, `403`, `404`, `409` Konflikt/abgesagt, `422` |

Die Eingabe lokaler Zeiten verwendet eine konfigurierte Zeitzone. Nicht existierende lokale Zeiten werden abgewiesen; doppelte Zeiten sind mit Fold-Auswahl eindeutig zu machen. Konflikte können unter anderem Besetzung, Abwesenheit, Qualifikation, Zuweisung, Überlappung und Ruhezeit betreffen. Das ist keine Rechtskonformitätsprüfung.

Wöchentliche Verfügbarkeitsfenster werden als lokale Wochentage/-zeiten gespeichert. Dienstwünsche und Sperrzeiten verwenden konfigurierte lokale Eingabe und werden UTC-zeitbewusst gespeichert; Anträge sind offen, angenommen oder abgelehnt. Änderungen der Verfügbarkeit und Entscheidungen werden auditiert. Eine bestätigte Sperrzeit kann nicht angenommen werden, solange geplante Dienste kollidieren.

## Rechnungswesen

| Methode und Route | Recht / Bereich | Eingabe | Erfolg / Response | Wesentliche Fehler |
|---|---|---|---|---|
| `GET /api/v1/billing/rates` | `billing.invoices.read` | – | `200 BillingRateRead[]` (aktive Preise) | `401`, `403` |
| `POST /api/v1/billing/rates` | `billing.rates.manage` + CSRF | `BillingRateCreate` | `201 BillingRateRead` | `401`, `403`, `409` Preisschlüssel belegt, `422` |
| `GET /api/v1/billing/invoices` | `billing.invoices.read` | `customer_id`, `invoice_status` (`draft`, `approved`, `archived`); max. 500 | `200 InvoiceRead[]` | `401`, `403`, `422` |
| `POST /api/v1/billing/invoices` | `billing.invoices.create` + CSRF | `InvoiceCreate` | `201 InvoiceRead`; Idempotenzschlüssel | `401`, `403`, `404`, `409` Schlüssel/Integrität/Zeitbuchung bereits abgerechnet, `422` |
| `POST /api/v1/billing/invoices/{invoice_id}/corrections` | `billing.invoices.create` + CSRF | Pfad `invoice_id`, `InvoiceCorrectionCreate` | `201 InvoiceRead`; neuer Storno-/Korrekturbeleg, Original bleibt unverändert | `401`, `403`, `404`, `409` Original nicht freigegeben/Schlüsselkonflikt, `422` |
| `POST /api/v1/billing/invoices/{invoice_id}/approve` | `billing.invoices.approve` + CSRF | Pfad `invoice_id` | `200 InvoiceRead` | `401`, `403`, `404`, `409` kein Entwurf, `422` |
| `POST /api/v1/billing/invoices/{invoice_id}/archive` | `billing.invoices.archive` + CSRF | Pfad `invoice_id`, `ArchiveInvoice` | `200 InvoiceRead` | `401`, `403`, `404`, `409` nicht freigegeben, `422` |
| `GET /api/v1/billing/invoices/{invoice_id}/payments` | `billing.invoices.read` | Pfad `invoice_id` | `200 BillingPaymentRead[]` | `401`, `403`, `404` |
| `POST /api/v1/billing/invoices/{invoice_id}/payments` | `billing.payments.manage` + CSRF | Pfad `invoice_id`, `PaymentCreate` | `201 BillingPaymentRead`; Zahlung und Zahlungsstatus | `401`, `403`, `404`, `409` Status-/Idempotenzkonflikt, `422` Betrag/Validierung |
| `PATCH /api/v1/billing/invoices/{invoice_id}/dunning` | `billing.payments.manage` + CSRF | Pfad `invoice_id`, `DunningUpdate` | `200 InvoiceRead` | `401`, `403`, `404`, `409` nicht mahnfähig, `422` |
| `POST /api/v1/billing/invoices/{invoice_id}/exports` | `billing.exports.create` + CSRF | Pfad `invoice_id`, Query `idempotency_key` (8–100 Zeichen) | `201 BillingExportRead`; versionierter JSON-Snapshot und SHA-256 | `401`, `403`, `404`, `409` Status-/Versionskonflikt, `422` |
| `GET /api/v1/billing/invoices/{invoice_id}/pdf` | `billing.invoices.read` | Pfad `invoice_id` | `200 application/pdf`, `private, no-store` | `401`, `403`, `404`, `409` Rechnung nicht freigegeben |

Die Preis- und Steuerwerte sind konfigurierte Eingaben. Beträge werden mit `Decimal`/`NUMERIC` gerechnet; Positionsrundung und Summenbildung folgen dem Implementierungsstand, ersetzen aber weder fachliche Freigabe noch Steuer-/Buchhaltungsprüfung. Ein Export ist keine zertifizierte Buchhaltungsintegration.

## Zeiterfassung

| Methode und Route | Recht / Bereich | Eingabe | Erfolg / Response | Wesentliche Fehler |
|---|---|---|---|---|
| `POST /api/v1/time-tracking/start` | `time_tracking.create` oder `time_tracking.manage`; Personal-/Objekt-Scope + CSRF | `TimeEntryStart` | `201 TimeEntryRead` | `401`, `403`, `404`, `409` laufende Buchung/kein eindeutiger Dienst, `422` |
| `POST /api/v1/time-tracking/entries/manual` | `time_tracking.manage`; Personal-/Objekt-Scope + CSRF | `TimeEntryManualCreate` (Mitarbeiter, Objekt, Segmente, optional Dienst) | `201 TimeEntryRead` | `401`, `403`, `404`, `409` Zeit-/Periodenkonflikt, `422` |
| `POST /api/v1/time-tracking/entries/{entry_id}/pause` | Eigentümer oder `time_tracking.manage`; Scope + CSRF | – | `200 TimeEntryRead` | `401`, `403`, `404`, `409` ungültiger Status/Periode |
| `POST /api/v1/time-tracking/entries/{entry_id}/resume` | Eigentümer oder `time_tracking.manage`; Scope + CSRF | – | `200 TimeEntryRead` | `401`, `403`, `404`, `409` |
| `POST /api/v1/time-tracking/entries/{entry_id}/stop` | Eigentümer oder `time_tracking.manage`; Scope + CSRF | – | `200 TimeEntryRead` | `401`, `403`, `404`, `409` |
| `GET /api/v1/time-tracking/entries` | `time_tracking.read_own` oder `time_tracking.read_all`; Objekt-Scope | `from_date`, `to_date` (gemeinsam), `employee_id`, `object_id`, `customer_id`, `status` | `200 TimeEntryRead[]` | `401`, `403`, `422` |
| `POST /api/v1/time-tracking/entries/{entry_id}/corrections` | Eigentümer: `time_tracking.correct_own`; sonst `time_tracking.correct_all`; Scope + CSRF | `TimeCorrectionCreate` (Grund + vollständige Segmente) | `201 TimeEntryCorrectionRead` | `401`, `403`, `404`, `409` Status/Pending-Korrektur/gesperrte Periode, `422` |
| `GET /api/v1/time-tracking/corrections` | `time_tracking.read_all` + Objekt-Scope | `pending_only` (bool, Standard `true`) | `200 TimeEntryCorrectionRead[]` | `401`, `403`, `422` |
| `POST /api/v1/time-tracking/entries/{entry_id}/approve` | `time_tracking.approve`; keine Selbstfreigabe; Scope + CSRF | – | `200 TimeEntryRead` | `401`, `403`, `404`, `409` Status/Selbstfreigabe |
| `POST /api/v1/time-tracking/entries/{entry_id}/reject` | `time_tracking.reject`; Scope + CSRF | `TimeEntryDecision` mit Begründung | `200 TimeEntryRead` | `401`, `403`, `404`, `409`, `422` |
| `POST /api/v1/time-tracking/corrections/{correction_id}/approve` | `time_tracking.approve`; Scope + CSRF | – | `200 TimeEntryRead` | `401`, `403`, `404`, `409` |
| `POST /api/v1/time-tracking/corrections/{correction_id}/reject` | `time_tracking.reject`; Scope + CSRF | `TimeEntryDecision` mit Begründung | `200 TimeEntryRead` | `401`, `403`, `404`, `409`, `422` |
| `POST /api/v1/time-tracking/entries/{entry_id}/lock` | `time_tracking.manage`; Scope + CSRF | – | `200 TimeEntryRead` | `401`, `403`, `404`, `409` Status/gesperrte Periode |
| `GET /api/v1/time-tracking/reports` | `time_tracking.read_own` oder `time_tracking.read_all`; Objekt-Scope | erforderlich `from_date`, `to_date`; optional `employee_id`, `object_id`, `customer_id`, `status`, `group_by` (`employee|object|customer|day|week|month`) | `200 TimeEntrySummaryRead` | `401`, `403`, `422` |
| `GET /api/v1/time-tracking/reports/missing` | `time_tracking.read_all` + Objekt-Scope | erforderlich `from_date`, `to_date` | `200 MissingShiftRead[]` | `401`, `403`, `422` |
| `GET /api/v1/time-tracking/export.csv` | `time_tracking.export` + Objekt-Scope | erforderlich `from_date`, `to_date`; optional `employee_id`, `object_id`, `customer_id` | `200 text/csv` | `401`, `403`, `422` |

Nur freigegebene bzw. gesperrte Zeitbuchungen sind exportierbar. Der Export maskiert Tabellenformeln. Statusänderungen, Zeitkorrekturen und Sperren sind keine direkte Überschreibung der freigegebenen Originalsegmente.

## Zuschlagszeit und Perioden

| Methode und Route | Recht / Bereich | Eingabe | Erfolg / Response | Wesentliche Fehler |
|---|---|---|---|---|
| `GET /api/v1/time-tracking/settings` | `time_tracking.surcharges.read` | – | `200 TimeTrackingSettingsRead` | `401`, `403` |
| `PATCH /api/v1/time-tracking/settings` | `time_tracking.surcharges.manage` + CSRF | `TimeTrackingSettingsUpdate` (Bundesland) | `200 TimeTrackingSettingsRead` | `401`, `403`, `409` Periodenkonflikt, `422` |
| `GET /api/v1/time-tracking/surcharge-rules` | `time_tracking.surcharges.read` | – | `200 TimeSurchargeRuleRead[]` | `401`, `403` |
| `POST /api/v1/time-tracking/surcharge-rules` | `time_tracking.surcharges.manage` + CSRF | `TimeSurchargeRuleCreate` | `201 TimeSurchargeRuleRead` | `401`, `403`, `409` Regelcode/Bundesland/Periode, `422` |
| `POST /api/v1/time-tracking/entries/{entry_id}/surcharge-calculations` | `time_tracking.surcharges.manage` + `time_tracking.read_all` + Scope + CSRF | – | `201 TimeSurchargeCalculationRead` | `401`, `403`, `404`, `409`, `422` |
| `GET /api/v1/time-tracking/entries/{entry_id}/surcharge-calculations` | `time_tracking.surcharges.read` + `time_tracking.read_all` + Scope | – | `200 TimeSurchargeCalculationRead[]` | `401`, `403`, `404` |
| `GET /api/v1/time-tracking/reports/surcharges` | `time_tracking.surcharges.read` + `time_tracking.read_all` + Scope | erforderlich `from_date`, `to_date` | `200 TimeSurchargeCalculationRead[]` | `401`, `403`, `422` |
| `GET /api/v1/time-tracking/export-surcharges.csv` | `time_tracking.export` + `time_tracking.surcharges.read` + Scope | erforderlich `from_date`, `to_date` | `200 text/csv` | `401`, `403`, `422` |
| `GET /api/v1/time-tracking/periods` | `time_tracking.periods.read` | – | `200 TimeTrackingPeriodRead[]` | `401`, `403` |
| `POST /api/v1/time-tracking/periods/lock` | `time_tracking.periods.lock` + CSRF | `TimeTrackingPeriodLockCreate` | `201 TimeTrackingPeriodRead` | `401`, `403`, `409` unvollständig, überschneidend oder noch nicht abgelaufen, `422` |

Zuschlagsregeln und Snapshots dokumentieren qualifizierbare Arbeitszeit, Regelwerte und Berechnungskontext. Es wird kein Geldbetrag errechnet. Eine gesperrte Periode hat keinen Entsperr-Endpunkt.

## OWKS und Kontrollgänge

OWKS-Routen erfordern zusätzlich zu den Modulrechten einen serverseitigen Objekt-Scope (globale Objektberechtigung oder Zuweisung). Schreibereignisse benötigen `owks.write` oder `owks.manage` und eine aktive, mit dem Konto verknüpfte Personalakte. Verwaltung von Kontrollpunkten/Routen, Status, Korrekturen und Monitoring erfordert `owks.manage`. Änderungen an OWKS-Ereignissen und Anhängen werden nicht überschrieben; Korrekturen werden als neue Ereignisse protokolliert.

| Methode und Route | Recht / Bereich | Eingabe | Erfolg / Response | Wesentliche Fehler |
|---|---|---|---|---|
| `GET /api/v1/owks/objects` | `owks.read`; nur erreichbare aktive Objekte | – | `200` JSON-Objektliste | `401`, `403` |
| `GET /api/v1/owks/objects/{object_id}/control-points` | `owks.read` + Objekt-Scope | Pfad `object_id` | `200` JSON-Liste | `401`, `403`, `404` |
| `POST /api/v1/owks/objects/{object_id}/control-points` | `owks.manage` + Schreib-Scope + CSRF | `OWKSControlPointCreate` | `201 OWKSControlPointRead` | `401`, `403`, `404`, `409`, `422` |
| `GET /api/v1/owks/objects/{object_id}/routes` | `owks.read` + Objekt-Scope | Pfad `object_id` | `200 OWKSRouteRead[]` | `401`, `403`, `404` |
| `POST /api/v1/owks/objects/{object_id}/routes` | `owks.manage` + Schreib-Scope + CSRF | `OWKSRouteCreate` | `201 OWKSRouteRead` | `401`, `403`, `404`, `409`, `422` |
| `POST /api/v1/owks/objects/{object_id}/challenges` | `owks.write` oder `owks.manage` + Objekt-Scope + CSRF | Pfad `object_id` | `200 OWKSChallengeRead` | `401`, `403`, `404`, `409`, `422` |
| `POST /api/v1/owks/scans` | `owks.write` oder `owks.manage` + aktive Personalakte und Objekt-Scope + CSRF | `OWKSScanCreate` | `201 OWKSEventRead` | `401`, `403`, `404`, `409`, `422` |
| `GET /api/v1/owks/objects/{object_id}/events` | `owks.read` + Objekt-Scope | `limit`, `offset` | `200` JSON-Ereignisliste | `401`, `403`, `404`, `422` |
| `POST /api/v1/owks/routes/{route_id}/monitor` | `owks.manage` + Objekt-Scope + CSRF | Pfad `route_id` | `200` JSON-Liste neu protokollierter Versäumnisse | `401`, `403`, `404`, `409` |
| `POST /api/v1/owks/events` | `owks.write` oder `owks.manage` + aktive Personalakte und Objekt-Scope + CSRF | `OWKSEventCreate` | `201 OWKSEventRead` | `401`, `403`, `404`, `409`, `422` |
| `POST /api/v1/owks/events/sync` | `owks.write` oder `owks.manage` + aktive Personalakte; Objekt-Scope pro Ereignis + CSRF | Ereignisliste `OWKSSyncEventCreate` | `200` JSON-Ergebnisse je synchronisiertem Ereignis | `401`, `403`, `404`, `409`, `422` |
| `POST /api/v1/owks/events/{event_id}/status` | `owks.manage` + Objekt-Scope + CSRF | `OWKSEventStateUpdate` | `200 OWKSEventRead` | `401`, `403`, `404`, `409`, `422` |
| `POST /api/v1/owks/events/{event_id}/corrections` | `owks.manage` + Objekt-Scope + CSRF | `OWKSEventCorrectionCreate` | `201 OWKSEventRead` | `401`, `403`, `404`, `409`, `422` |
| `POST /api/v1/owks/events/{event_id}/attachments` | `owks.write` oder `owks.manage` + Objekt-Scope + CSRF | multipart `file` (PDF/PNG/JPEG, max. 10 MiB) | `201 OWKSAttachmentRead` | `401`, `403`, `404`, `413`, `422` |
| `GET /api/v1/owks/events/{event_id}/attachments` | `owks.read` + Objekt-Scope | Pfad `event_id` | `200 OWKSAttachmentRead[]` | `401`, `403`, `404` |
| `GET /api/v1/owks/events/{event_id}/attachments/{attachment_id}` | `owks.read` + Objekt-Scope | `download` (bool) | `200` autorisierte Binärdatei oder Metadaten | `401`, `403`, `404`, `422` |

Ein erfolgreicher Scan-Eintrag beweist bei statischen Kennungen keine physische Präsenz; `presence_verified` darf daher nicht als tatsächliche Anwesenheitsbestätigung verstanden werden. Der Hintergrundmonitor läuft zusätzlich automatisiert im Prozess; der manuelle Endpunkt ist eine separate Auslösung.

## Dokumente, Verträge und Erinnerungen

Dokument- und Vertragsrouten erfordern jeweils das genannte Modulrecht und zusätzlich serverseitige Bereichsfilter für Objekt-, Kunden- und Personaldaten. Schreibende Requests benötigen CSRF. Neue Dokumente und Versionen werden vor Speicherung fail-closed mit ClamAV geprüft. Dateien werden über geschützte Endpunkte ausgeliefert; ein Datei-Hash belegt Integrität, nicht Verschlüsselung oder rückwirkende Malwarefreiheit.

| Methode und Route | Recht / Bereich | Eingabe | Erfolg / Response | Wesentliche Fehler |
|---|---|---|---|---|
| `GET /api/v1/documents` | `documents.read` + Scope | `q`, `status`, `category`, `customer_id`, `object_id`, `employee_id`, `include_archived`, `limit`, `offset` | `200 DocumentPage` | `401`, `403`, `422` |
| `POST /api/v1/documents` | `documents.create` + CSRF | multipart Metadaten und `file` | `201 DocumentRead` | `401`, `403`, `409`, `413`, `422` |
| `GET /api/v1/documents/{document_id}` | `documents.read` + Scope | Pfad `document_id` | `200 DocumentDetailRead` | `401`, `403`, `404` |
| `PATCH /api/v1/documents/{document_id}` | `documents.update` + Scope + CSRF | `DocumentUpdate` | `200 DocumentRead` | `401`, `403`, `404`, `409`, `422` |
| `POST /api/v1/documents/{document_id}/versions` | `documents.update` + Scope + CSRF | multipart `file` | `201 DocumentVersionRead` | `401`, `403`, `404`, `409`, `413`, `422` |
| `POST /api/v1/documents/{document_id}/archive` | `documents.archive` + Scope + CSRF | – | `200 DocumentRead` | `401`, `403`, `404`, `409` |
| `POST /api/v1/documents/{document_id}/restore` | `documents.archive` + Scope + CSRF | – | `200 DocumentRead` | `401`, `403`, `404`, `409` |
| `GET /api/v1/documents/{document_id}/versions/{version_id}/download` | `documents.download` + Scope | Pfad-IDs | `200` autorisierte Binärdatei | `401`, `403`, `404` |
| `POST /api/v1/documents/versions/{version_id}/approvals` | `documents.update` + Scope + CSRF | Pfad `version_id` | `201 DocumentApprovalRead` | `401`, `403`, `404`, `409` |
| `PATCH /api/v1/documents/approvals/{approval_id}` | `documents.approve` + CSRF | `ApprovalDecision` | `200 DocumentApprovalRead` | `401`, `403`, `404`, `409`, `422` |
| `GET /api/v1/document-approvals` | `documents.read` + Scope | – | `200 DocumentApprovalQueueItem[]` | `401`, `403` |
| `POST /api/v1/documents/versions/{version_id}/read-receipt` | `documents.read` + Scope + CSRF | Pfad `version_id` | `200 DocumentReadReceiptRead` | `401`, `403`, `404`, `409` |
| `GET /api/v1/contracts` | `contracts.read` + Scope | `q`, `status`, `contract_type`, `customer_id`, `object_id`, `include_archived`, `limit`, `offset` | `200 ContractPage` | `401`, `403`, `422` |
| `POST /api/v1/contracts` | `contracts.create` + CSRF | `ContractCreate` | `201 ContractRead` | `401`, `403`, `404`, `409`, `422` |
| `GET /api/v1/contracts/{contract_id}` | `contracts.read` + Scope | Pfad `contract_id` | `200 ContractRead` | `401`, `403`, `404` |
| `PATCH /api/v1/contracts/{contract_id}` | `contracts.update` + Scope + CSRF | `ContractUpdate` | `200 ContractRead` | `401`, `403`, `404`, `409`, `422` |
| `POST /api/v1/contracts/{contract_id}/archive` | `contracts.archive` + Scope + CSRF | – | `200 ContractRead` | `401`, `403`, `404`, `409` |
| `POST /api/v1/contracts/{contract_id}/restore` | `contracts.archive` + Scope + CSRF | – | `200 ContractRead` | `401`, `403`, `404`, `409` |
| `GET /api/v1/reminders/settings` | `contracts.manage_reminders` | – | `200 ReminderSettingsRead` | `401`, `403` |
| `PUT /api/v1/reminders/settings` | `contracts.manage_reminders` + CSRF | `ReminderSettingsUpdate` | `200 ReminderSettingsRead` | `401`, `403`, `422` |
| `POST /api/v1/reminders/generate` | `contracts.manage_reminders` + CSRF | – | `200` JSON-Zähler generierter Erinnerungen | `401`, `403`, `409` |
| `GET /api/v1/reminders` | `contracts.read` + Scope | `status`, `due_before` | `200 ReminderRead[]` | `401`, `403`, `422` |
| `PATCH /api/v1/reminders/{reminder_id}` | `contracts.manage_reminders` + CSRF | `ReminderStatusUpdate` | `200 ReminderRead` | `401`, `403`, `404`, `409`, `422` |

Die zulässigen Dokumentdateitypen sind PDF, PNG, JPEG, DOCX und XLSX; die konfigurierte Uploadgrenze ist im Backend festgelegt. Erinnerungen werden nicht automatisch täglich generiert oder per E-Mail/Push zugestellt. Die vollständigen Felder und Enums der Schema-Referenzen liefert OpenAPI.

## Aufgaben

| Methode und Route | Recht / Bereich | Eingabe | Erfolg / Response | Wesentliche Fehler |
|---|---|---|---|---|
| `GET /api/v1/tasks` | `tasks.read_own`, `tasks.read_all` oder `tasks.manage_all`; Ergebnis zusätzlich nach Aufgaben-/Objektbereich gefiltert | `q` (max. 200), `status`, `priority`, `assigned_to_id`, `customer_id`, `object_id`, `overdue`, `limit` (1–100, Standard 25), `offset` | `200 TaskPage` | `401`, `403`, `422` |
| `POST /api/v1/tasks` | `tasks.create` + CSRF; Kunden-/Objektzuordnung und verantwortliche Person serverseitig geprüft | `TaskCreate` | `201 TaskRead`; ohne Verantwortlichen wird der Ersteller zugewiesen | `401`, `403`, `422` |
| `GET /api/v1/tasks/{task_id}` | `tasks.read_own`, `tasks.read_all` oder `tasks.manage_all`; Bereichsprüfung, nicht sichtbare Aufgabe wird verborgen | UUID-Pfad `task_id` | `200 TaskDetail` einschließlich Kommentaren und Verlauf | `401`, `403`, `404` |
| `PATCH /api/v1/tasks/{task_id}` | `tasks.update_own`, `tasks.manage` oder `tasks.manage_all` sowie zusätzliche Aufgaben-/Objektbereichsprüfung + CSRF | UUID-Pfad `task_id`, `TaskUpdate` | `200 TaskRead`; Statuswechsel zu `completed` verlangt Erledigungsnachweis. Tatsächliche Neuzuweisung und Statusänderung erzeugen Benachrichtigungen transaktional | `401`, `403`, `404`, `422` |
| `POST /api/v1/tasks/{task_id}/comments` | dieselben Bearbeitungsrechte und Bereichsprüfung wie Aufgabenänderung + CSRF | UUID-Pfad `task_id`, `TaskCommentCreate` | `201 TaskCommentRead` | `401`, `403`, `404`, `422` |
| `GET /api/v1/tasks/locations` | `tasks.create`; Auswahlwerte nach Bereich gefiltert | – | `200 TaskLocationsRead` | `401`, `403` |
| `GET /api/v1/tasks/assignees` | `tasks.assign`; optionale Query `object_id`, Auswahl aktiver Benutzer nach Bereich gefiltert | – | `200 TaskAssigneeRead[]` | `401`, `403`, `422` |

Aufgaben-, Kommentar-, Verlauf-, Audit- und die erfassten Benachrichtigungsänderungen werden in Datenbanktransaktionen gespeichert. Fälligkeiten müssen eine Zeitzone enthalten und werden auf UTC normalisiert. Der generische Kern löst keine automatischen Aufgaben aus anderen Fachmodulen aus und enthält keine Anhänge, externen Zustellkanäle, Hintergrundjobs oder Eskalationen; siehe [`TASKS.md`](TASKS.md).

## In-App-Benachrichtigungen

| Methode und Route | Recht / Bereich | Eingabe | Erfolg / Response | Wesentliche Fehler |
|---|---|---|---|---|
| `GET /api/v1/notifications` | `notifications.read_own` und ein Task- oder OWKS-Leserecht; zusätzlich Empfänger-ID sowie Aufgaben- oder aktuelle Objektzuweisung | `unread_only` (bool, Standard `false`), `limit` (1–100, Standard 25), `offset` (Standard 0) | `200 NotificationPage` mit Items, Gesamtzahl und ungelesener Anzahl; `task_id`/`object_id` kennzeichnen genau einen Bezug | `401`, `403`, `422` |
| `PATCH /api/v1/notifications/{notification_id}/read` | `notifications.read_own` und ein Task- oder OWKS-Leserecht; nur eigene, aktuell sichtbare Einträge + CSRF | UUID-Pfad `notification_id` | `200 NotificationRead`; wiederholtes Markieren ist idempotent | `401`, `403`, `404` fremder/nicht sichtbarer/unbekannter Eintrag |

Die Inbox enthält Aufgaben-Zuweisungs- und Statusänderungsereignisse sowie daraus erzeugte sichere Automatisierungsbenachrichtigungen. Aufgabenänderung, Historie, Audit und Outbox-Ereignis werden transaktional gespeichert; der separate Worker erzeugt Empfänger-Inbox-Einträge anschließend idempotent und schließt das Outbox-Ereignis atomar ab. OWKS-Automationsbenachrichtigungen sind objektgebunden, werden nur an aktive Benutzer mit aktueller Objektzuweisung ausgeliefert und enthalten keine OWKS-Beschreibung oder Hergangsdaten. Migration `0024_notification_outbox_worker` ergänzt Claim-/Lease-Felder und append-only Attempt-Historie. E-Mail/Push und Task-Erinnerungen/Eskalationen sind nicht enthalten. Details: [`NOTIFICATIONS.md`](NOTIFICATIONS.md).

## Automatisierungen

| Methode und Route | Recht / Bereich | Eingabe | Erfolg / Response | Wesentliche Fehler |
|---|---|---|---|---|
| `GET /api/v1/automations/rules` | `automations.manage`; standardmäßig Administrator | – | `200 AutomationRuleRead[]` | `401`, `403` |
| `POST /api/v1/automations/rules` | `automations.manage` + CSRF | Name, Beschreibung, registrierter Aufgaben- oder OWKS-Trigger, optionale Statusbedingung nur für Aufgaben, festes `notify_event_recipients` | `201 AutomationRuleRead`; Regel anfangs deaktiviert | `401`, `403`, `422` |
| `GET/PATCH/DELETE /api/v1/automations/rules/{rule_id}` | `automations.manage`; Schreibzugriffe + CSRF | UUID und typisierte Regeländerung / leer | `200 AutomationRuleRead`; DELETE deaktiviert weich und antwortet `204` | `401`, `403`, `404`, `422` |
| `GET /api/v1/automations/runs` | `automations.manage`; `limit` 1–100, `offset` | – | `200 AutomationRunPage`, inklusive bereinigter Outbox-Versuchshistorie | `401`, `403`, `422` |
| `GET /api/v1/automations/outbox-events` | `automations.manage`; `limit` 1–100 | – | `200 AutomationOutboxEventPage` für registrierte Dead-Letter-Ereignisse | `401`, `403`, `422` |
| `POST /api/v1/automations/runs/{run_id}/retry` | `automations.manage` + CSRF | UUID eines fehlgeschlagenen Laufs | `202`; Aktion erneut eingereiht | `401`, `403`, `404`, `409` |
| `POST /api/v1/automations/outbox-events/{event_id}/retry` | `automations.manage` + CSRF | UUID eines fehlgeschlagenen registrierten Outbox-Ereignisses | `202`; Ereignis erneut eingereiht | `401`, `403`, `404`, `409` |

Registriert sind `task.assigned`, `task.status_changed`, `owks.missed_control`, `owks.deviation_reported` und `owks.offline_event_synced`; die optionale Bedingung vergleicht nur bei Aufgaben-Triggern den Aufgabenstatus. OWKS-Empfänger stammen ausschließlich aus aktiven Objektzuweisungen. OWKS-Payloads sind versioniert und strikt validiert; Automationsbenachrichtigungen enthalten keine OWKS-Beschreibungen oder Hergangsdaten und lösen keine weitere Regel aus. Kontrollgangstart/-ende, unvollständige Rundgänge, weitere Fachtrigger, freie Regeln/Ausdrücke, externe Kanäle und rechtlich oder finanziell relevante Zustandsänderungen sind nicht implementiert. Wiederholungen sind je Outbox-Ereignis auf drei manuelle Versuche begrenzt. Siehe [`AUTOMATIONS.md`](AUTOMATIONS.md).

## Schlüsselverwaltung

| Methode und Route | Recht / Bereich | Eingabe | Erfolg / Response | Wesentliche Fehler |
|---|---|---|---|---|
| `GET /api/v1/keys` | `keys.read`; zusätzlich Objektbereich, sofern kein globales Objektleserecht besteht | `q`, `status`, `object_id`, `employee_id`, `include_archived`, `limit` (1–100, Standard 25), `offset` | `200 PhysicalKeyPage` | `401`, `403`, `422` |
| `POST /api/v1/keys` | `keys.manage` plus Objektzugriff und objektbezogenes Verwaltungsrecht + CSRF | `PhysicalKeyCreate` (`key_number`, `description`, `object_id`) | `201 PhysicalKeyRead` | `401`, `403`, `404`, `409` doppelte Nummer/archiviertes Objekt, `422` |
| `PATCH /api/v1/keys/{key_id}` | `keys.manage` plus Objektbereich und objektbezogenes Verwaltungsrecht + CSRF | UUID-Pfad `key_id`, `PhysicalKeyUpdate` (Beschreibung) | `200 PhysicalKeyRead` | `401`, `403`, `404`, `409` archivierter Schlüssel, `422` |
| `POST /api/v1/keys/{key_id}/archive` | `keys.manage` plus Objektbereich und objektbezogenes Verwaltungsrecht + CSRF | UUID-Pfad `key_id` | `200 PhysicalKeyRead` | `401`, `403`, `404`, `409` bereits archiviert/noch ausgegeben |
| `GET /api/v1/keys/objects` | `keys.read`; Auswahl aktiver Objekte des erlaubten Objektbereichs | – | `200 KeyObjectCandidate[]` | `401`, `403` |
| `GET /api/v1/keys/eligible-employees` | `keys.move` plus Objektbereich | Query `object_id` | `200 KeyEmployeeCandidate[]`; aktive Beschäftigte mit aktivem Benutzerkonto und Zuweisung zum Objekt | `401`, `403`, `404`, `422` |
| `POST /api/v1/keys/{key_id}/movements` | `keys.move` plus Objektbereich + CSRF | UUID-Pfad `key_id`, `KeyMovementCreate` (`movement_type`, optional `employee_id`, Quittierung und Notiz) | `201 KeyMovementRead` | `401`, `403`, `404`, `409` unzulässiger Zustandswechsel, `422` fehlende Notiz/Quittierung oder nicht berechtigte Person |
| `GET /api/v1/keys/{key_id}/movements` | `keys.read` plus Objektbereich | UUID-Pfad `key_id`, `limit` (1–100, Standard 25), `offset` | `200 KeyMovementPage` | `401`, `403`, `404`, `422` |

Die verfügbaren Bewegungsarten sind `issued`, `returned`, `lost`, `defective` und `inventory`. Rechte sind `keys.read`, `keys.manage` und `keys.move`; Rollenrechte ersetzen die zusätzliche Objektbereichsprüfung nicht. Ausgabe, Statusänderung, Bewegung und Audit werden gemeinsam transaktional gespeichert. Eine Quittierung dokumentiert die Bestätigung im angemeldeten Benutzerkontext, ist aber keine qualifizierte elektronische Signatur und belegt weder physische Verwahrung noch tatsächliche Sicherung. Bestehende Freitext-Zutrittsangaben werden nicht migriert oder als Schlüsselregister interpretiert. Details: [`KEY_MANAGEMENT.md`](KEY_MANAGEMENT.md).

## Vorfall- und Beschwerdemanagement

| Methode und Route | Recht / Bereich | Eingabe | Erfolg / Response | Wesentliche Fehler |
|---|---|---|---|---|
| `GET /api/v1/incidents/choices` | Vorfall-Leserecht; Objekte/Verantwortliche nach Objektbereich gefiltert | optional `object_id` | `200 IncidentChoices` | `401`, `403`, `404`, `422` |
| `GET /api/v1/incidents` | `incidents.read`, `incidents.read_all` oder `incidents.manage_all`; Ergebnis zusätzlich objektgefiltert | `status`, `object_id`, `overdue`, `limit` (1–100, Standard 25), `offset` | `200 IncidentPage` | `401`, `403`, `404`, `422` |
| `POST /api/v1/incidents` | `incidents.create` und schreibbarer Objektbereich + CSRF | `IncidentCreate` | `201 IncidentRead` | `401`, `403`, `404`, `422` unzulässige Objekt-/OWKS-/Verantwortlichenbezüge |
| `GET /api/v1/incidents/{incident_id}` | Vorfall-Leserecht und Objektbereich | UUID-Pfad `incident_id` | `200 IncidentDetail`; sensible Details, Personen und Dateimetadaten nur mit `incidents.sensitive.read` | `401`, `403`, `404` |
| `PATCH /api/v1/incidents/{incident_id}` | `incidents.update` oder `incidents.manage_all`, plus Objektbereich und CSRF | UUID-Pfad, `IncidentUpdate` | `200 IncidentRead` | `401`, `403`, `404`, `409` abgeschlossener Vorgang, `422` |
| `POST /api/v1/incidents/{incident_id}/status` | Vorfall-Schreibrecht, Objektbereich + CSRF; Abschluss zusätzlich `incidents.sensitive.manage` | UUID-Pfad, `IncidentStatusUpdate` | `200 IncidentRead` | `401`, `403`, `404`, `409` offene Maßnahmen, `422` unzulässiger Übergang/fehlender Abschlussbericht |
| `PATCH /api/v1/incidents/{incident_id}/sensitive` | `incidents.sensitive.manage` und Vorfall-Schreibrecht, Objektbereich + CSRF | UUID-Pfad, `IncidentSensitiveUpdate` | `200 IncidentSensitiveRead` | `401`, `403`, `404`, `409`, `422` |
| `POST /api/v1/incidents/{incident_id}/measures` | Vorfall-Schreibrecht und Objektbereich + CSRF | UUID-Pfad, `IncidentMeasureCreate` | `201 IncidentMeasureRead` | `401`, `403`, `404`, `409`, `422` |
| `PATCH /api/v1/incidents/{incident_id}/measures/{measure_id}` | Vorfall-Schreibrecht und Objektbereich + CSRF | UUID-Pfade, `IncidentMeasureUpdate` | `200 IncidentMeasureRead` | `401`, `403`, `404`, `409`, `422` |
| `POST /api/v1/incidents/{incident_id}/people` | `incidents.sensitive.manage` und Vorfall-Schreibrecht, Objektbereich + CSRF | UUID-Pfad, `IncidentPersonCreate` | `201 IncidentPersonRead` | `401`, `403`, `404`, `409`, `422` |
| `POST /api/v1/incidents/{incident_id}/attachments` | `incidents.sensitive.manage` und Vorfall-Schreibrecht, Objektbereich + CSRF | UUID-Pfad, Multipart-Datei | `201 IncidentAttachmentRead` | `401`, `403`, `404`, `409`, `413` Größenlimit, `415` Typ, `422` Scannererkennung, `503` Scannerfehler |
| `GET /api/v1/incidents/{incident_id}/attachments/{attachment_id}/download` | `incidents.sensitive.read` und Vorfall-Leserecht, Objektbereich | UUID-Pfade | `200` geschützte Datei als Attachment | `401`, `403`, `404`, `503` Datei oder privater Speicher nicht verfügbar |

Die granularen Rechte lauten `incidents.read`, `incidents.read_all`, `incidents.create`, `incidents.update`, `incidents.manage_all`, `incidents.sensitive.read` und `incidents.sensitive.manage`. Objektbereichsprüfung gilt zusätzlich zum Modulrecht; nicht erreichbare Vorgänge werden verborgen. Der Kurzbericht bleibt Teil der normalen Vorfallantwort; Hergang, Abschlussbericht, Beteiligte/Zeugen und Dateiinhalte sind separat sensitiv geschützt. Dateianhänge akzeptieren PDF/PNG/JPEG bis 10 MiB, werden über private Speicherung mit ClamAV fail-closed geprüft und nur autorisiert ausgeliefert. OWKS wird optional referenziert, aber nicht geändert. Es gibt keine automatische Aufgaben-/Benachrichtigungsintegration, Fristerinnerung oder automatische Eskalation. Details: [`INCIDENTS.md`](INCIDENTS.md).

## Router- und Schemaprüfung

Zum Inventar gehören 190 API-Operationen unter `/api/v1` sowie zwei Health-Operationen außerhalb des Präfixes. Jede Tabellenzeile referenziert Methode, Pfad, Zugriffsregel, Parameter oder Body-Schema, Erfolgsschema und relevante Fehlerklassen. Die vollständigen Feldtypen/Enums der Bodies und Antworten werden von FastAPI unter `/openapi.json` bzw. `/docs` aus dem Quellcode generiert; diese Dokumentation ergänzt dort nicht ausmodellierte Rechte- und Fehlerbedingungen aus den Endpunktimplementierungen.

Änderungen an Routern, Pydantic-Schemas, Rechten oder Fehlersemantik müssen sowohl OpenAPI als auch diese Referenz aktualisieren. Der Umfang wird aus dem Quellcode auf `main` erhoben; die API-Dokumentation stellt keine Produktionsfreigabe dar.

PR #33 (fail-closed ClamAV-Uploadscan), PR #34 (Aufgaben-Kern), PR #35 (In-App-Benachrichtigungen), PR #36 (Schlüsselverwaltung), PR #37 (Vorfallmanagement), PR #38 (Leitstellenübersicht) und PR #39 (Notification-/OWKS-Worker) sind in der dokumentierten `main`-Momentaufnahme gemergt. Die betreffenden Uploadrouten, sieben Task-, zwei Notification-, acht Schlüsselverwaltungs-, zwölf Vorfall- und eine Leitstellenoperation sind in der Zählung enthalten. Neue Uploads werden synchron geprüft; vorhandene Dateien sind nicht rückwirkend geprüft. Incident-Anhänge werden privat gespeichert und separat anhand Vorfall-/Sensitivitätsrechten ausgeliefert. Issue #7 bleibt für die fachliche Abnahme des Rechnungswesens offen; Issues #8–#10 sind trotz gemergter Funktionen ebenfalls offen. PR #39 fügt keine API-Routen hinzu, weshalb die Main-Zählung bei 190 `/api/v1`-Operationen bleibt. TOTP-MFA bietet keine E-Mail-basierte Selbstwiederherstellung; ein berechtigter administrativer Passwortreset setzt eine Passwortwechselpflicht und widerruft Sitzungen.
