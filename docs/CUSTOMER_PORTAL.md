# Kundenportal – gestapelte Erweiterung

Diese Dokumentation beschreibt die Kundenportal-Erweiterungen auf dem
Feature-Branch. Sie ist kein Nachweis einer Integration in `main`, fachlichen
Abnahme oder Produktionsfreigabe. Im PR-Stack folgt die Alembic-Migration
`0026_customer_portal_access` linear auf `0025_unique_incident_owks_event` aus PR #40.
`0027_customer_document_grants` und `0028_customer_portal_requests` folgen linear
aufeinander. Die PRs sind nicht Teil des
gemergten `main`.

## Zugang und Verknüpfung

Ein vorhandenes Login wird ausschließlich manuell mit genau einem vorhandenen
`CustomerContact` verknüpft. Es gibt kein E-Mail-Matching. Die Datenbank erzwingt
höchstens eine aktive Verknüpfung je Benutzerkonto und je Kundenkontakt. Das Login
muss aktiv sein und ausschließlich die Rolle `customer_portal` besitzen. Diese
Rolle erhält nur `customer_portal.access`; für Portal-Konten begrenzt die
Authentifizierung die wirksamen Rechte zusätzlich auf dieses eine Recht.

Die Verknüpfungen werden ausschließlich durch Endpunkte mit
`customers.portal.manage` angelegt oder gelöst. Die Migration weist dieses Recht
nur der Administrator-Rolle zu:

| Methode | Pfad | Zweck |
|---|---|---|
| `GET` | `/api/v1/customer-portal/links` | Verknüpfungen einschließlich Aktivierungsstatus auflisten |
| `POST` | `/api/v1/customer-portal/links` | `{ "user_id": "...", "contact_id": "..." }` manuell verknüpfen |
| `PATCH` | `/api/v1/customer-portal/links/{contact_id}` | Zugang mit `{ "is_active": false }` deaktivieren oder erneut aktivieren |
| `DELETE` | `/api/v1/customer-portal/links/{contact_id}` | Verknüpfung lösen |
| `GET` | `/api/v1/customer-portal/link-history` | Append-only Verknüpfungs- und Aktivierungshistorie |
| `GET` | `/api/v1/customer-portal/access-history` | Portalaktivitäten als notwendige Metadaten ohne Inhalte |
| `GET` | `/api/v1/customer-portal/management-options` | Geeignete Portal-Konten und aktive Kundenkontakte für manuelle Verknüpfungen |

Verknüpfung, append-only Verknüpfungshistorie und Audit-Eintrag werden gemeinsam
transaktional geschrieben. Beim Lösen bleibt der Historieneintrag erhalten.
Konflikte bei bereits zugewiesenen Konten oder Kontakten werden abgelehnt. Die
Deaktivierung lässt die Verknüpfung und Historie bestehen, sperrt aber unmittelbar
den Portalzugriff. Reaktivierung erfordert weiterhin ein aktives Konto mit
ausschließlicher Kundenportal-Rolle sowie einen aktiven Kunden. Jede Änderung wird
zusätzlich auditiert. Die deutschsprachige Administrationsoberfläche ist nur mit
`customers.portal.manage` erreichbar; die serverseitige Berechtigungsprüfung bleibt
maßgeblich.

## Verfügbare Kundenansichten

Alle Portal-Endpunkte ermitteln den Kunden serverseitig aus
`angemeldeter Benutzer → aktive Verknüpfung → exakter Kundenkontakt → Kunde`.
Ein Kunde oder Kontakt kann nicht aus einem Request-Parameter gewählt werden.
Antworten mit Kundenbezug werden mit `Cache-Control: private, no-store` ausgeliefert.

| Methode | Pfad | Umfang |
|---|---|---|
| `GET` | `/api/v1/customer-portal/me` | Zugeordneter Ansprechpartner, ausgewählte Kundenstammdaten, Geschäfts-/Rechnungsanschrift sowie nicht archivierte Objekte desselben Kunden |
| `GET` | `/api/v1/customer-portal/invoices` | Höchstens 100 nicht archivierte Rechnungen dieses Kunden mit Status `approved`, einschließlich freigegebener Rechnungspositionen |
| `GET` | `/api/v1/customer-portal/invoices/{invoice_id}/pdf` | PDF nur bei passendem Kunden, Status `approved` und nicht archiviert |
| `GET` | `/api/v1/customer-portal/documents` | Nur ausdrücklich freigegebene, weiterhin aktive aktuelle Versionen von nicht personenbezogenen Kundendokumenten |
| `GET` | `/api/v1/customer-portal/documents/{grant_id}/download` | Private Datei nur für das verknüpfte aktive Portal-Konto des zugeordneten Kunden |

Die Administration verwaltet Dokumentfreigaben mit `customer_portal.documents.manage`:
`GET /customer-portal/document-candidates` liefert nur aktive, nicht personenbezogene
Kundendokumente samt aktueller Version; `POST /customer-portal/document-grants`
veröffentlicht die benannte Version explizit und
`DELETE /customer-portal/document-grants/{grant_id}` widerruft sie. Aktionshistorie,
Akteur und Zeit werden append-only gespeichert. Nach Upload einer neueren Version
ist eine bisherige Freigabe nicht mehr sichtbar; die neue Version muss separat
freigegeben werden. Dokumente ohne Kundenbezug, Personalunterlagen, inaktive oder
archivierte Dokumente sowie Dokumente zu einem fremden/inaktiven Objekt sind nicht
freigabefähig. Interne Dokumentfreigaben sind davon unabhängig.

Nicht ausgeliefert werden interne Kundennotizen, Steuer-/Umsatzsteuerkennungen,
Objektbeschreibungen, Personalbesetzungsanforderungen, Sicherheits- und
Zutrittsinformationen, andere Kundenkontakte sowie Rechnungsentwürfe, archivierte
Rechnungen und interne Korrekturbegründungen. Rechnungen sind nur dann sichtbar,
wenn die bestehende Rechnungsfreigabe den Status `approved` gesetzt hat; ein
Dokumentenstatus oder `documents.approve` ist keine Kundenfreigabe.

## Noch nicht umgesetzt

- Anfragen, Rückfragen und Beschwerden einschließlich Nachrichten, Status,
  Kundenanhängen und Admin-Bearbeitung.
- Freigegebene Berichte/Leistungsnachweise außerhalb freigegebener
  Rechnungspositionen.
- Ansprechpartnerverwaltung oder zusätzliche Objektkontakte im Portal.

Kundenkonten erhalten keine generischen `customers.read`, `documents.read`,
`incidents.read` oder `employees.*`-Rechte. Kundenportal-Zugriffsprotokolle
enthalten nur Aktion, Datensatzkennung und erforderliche Akteur-/Kontakt-Metadaten,
keine Inhalte oder Dateiwerte.

## Kundenanfragen und Beschwerden

Portal-Kontakte können unter `/api/v1/customer-portal/requests` Anfragen
(`request`), Rückfragen (`question`) oder Beschwerden (`complaint`) zu einem aktiven Objekt ihres eigenen
Kunden anlegen. Ein Fremdkunden- oder inaktives Objekt wird serverseitig abgelehnt;
Kunden- und Kontakt-ID stammen ausschließlich aus der Portalverknüpfung.
Nachrichten und Statushistorie sind append-only. Es gibt keine internen Notizfelder;
Nachrichten in diesem Vorgang sind für den zugeordneten Kontakt sichtbar.

Anhänge sind auf PDF/PNG/JPEG und höchstens 10 MiB begrenzt, werden anhand von
Dateiendung, MIME-Typ und Signatur geprüft und vor privater Speicherung fail-closed
durch den Malware-Scanner geprüft. Admin-Verwaltung und Statusänderungen erfordern
`customer_portal.requests.manage`; die Migration weist dieses Recht nur der
Administrator-Rolle zu. Statuswerte sind `submitted`, `in_progress`,
`waiting_customer`, `resolved` und `closed`; sie definieren keine SLA- oder
Eskalationsregeln.
