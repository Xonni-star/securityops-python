# Kundenportal – erste Zugriffsbasis

Diese Dokumentation beschreibt die erste vertikale Kundenportal-Basis auf dem
Feature-Branch. Sie ist kein Nachweis einer Integration in `main`, fachlichen
Abnahme oder Produktionsfreigabe. Die Alembic-Migration `0025_customer_portal_access`
folgt linear auf `0024_notification_outbox_worker`.

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
| `GET` | `/api/v1/customer-portal/links` | Aktive Verknüpfungen als interne IDs auflisten |
| `POST` | `/api/v1/customer-portal/links` | `{ "user_id": "...", "contact_id": "..." }` manuell verknüpfen |
| `DELETE` | `/api/v1/customer-portal/links/{contact_id}` | Verknüpfung lösen |

Verknüpfung, append-only Verknüpfungshistorie und Audit-Eintrag werden gemeinsam
transaktional geschrieben. Beim Lösen bleibt der Historieneintrag erhalten.
Konflikte bei bereits zugewiesenen Konten oder Kontakten werden abgelehnt. Die
Administration hat in dieser ersten Basis noch keine eigene Oberfläche; sie erfolgt
über die geschützte API.

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

Nicht ausgeliefert werden interne Kundennotizen, Steuer-/Umsatzsteuerkennungen,
Objektbeschreibungen, Personalbesetzungsanforderungen, Sicherheits- und
Zutrittsinformationen, andere Kundenkontakte sowie Rechnungsentwürfe, archivierte
Rechnungen und interne Korrekturbegründungen. Rechnungen sind nur dann sichtbar,
wenn die bestehende Rechnungsfreigabe den Status `approved` gesetzt hat; ein
Dokumentenstatus oder `documents.approve` ist keine Kundenfreigabe.

## Noch nicht umgesetzt

- Dokumente und Dateien: Es existiert noch keine gesonderte Kundenveröffentlichung.
  Interne Dokumentfreigaben oder Lesebestätigungen werden nicht als Portal-Freigabe
  interpretiert.
- Freigegebene Berichte/Leistungsnachweise außerhalb freigegebener
  Rechnungspositionen.
- Rückfragen, Beschwerden und Vorgangsstatus. Die internen Vorfall-Endpunkte bleiben
  ohne Kundenportal-Rechte; es gibt keine Weiterleitung an
  `incidents.create`/`incidents.read`.
- Ansprechpartnerverwaltung oder zusätzliche Objektkontakte im Portal.
- Administrationsoberfläche für die Verknüpfung.

Diese Bereiche benötigen eigene Freigabe-, Sichtbarkeits- und
Änderungsregeln, bevor sie ergänzt werden. Kundenkonten erhalten keine generischen
`customers.read`, `documents.read`, `incidents.read` oder `employees.*`-Rechte.
