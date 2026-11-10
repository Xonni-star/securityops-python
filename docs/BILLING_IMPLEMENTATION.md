# Rechnungswesen, Freigaben und Buchhaltungsexport

Diese Dokumentation beschreibt die Implementierung des Rechnungswesens, Freigaben und Buchhaltungsexports gemäß Issue #7.

## Überblick

Die Implementierung ermöglicht die Erzeugung reproduzierbarer Rechnungen aus freigegebenen Vertrags-/Zeitdaten mit folgenden Funktionen:
- Stunden-, Pauschal-, Zuschlags- und Mischabrechnung mit konfigurierbaren Preisen
- NUMERIC/Decimal, Positionen, Steuerwerte, Fälligkeit, Zahlungs- und Mahnstatus
- Eindeutige Rechnungsnummer, Entwurf/Freigabe/Archivierung und PDF-Erzeugung
- Buchhaltungsexport über versionierte Schnittstelle

## Implementierte Funktionen

### Abrechnungstypen
- **Stundenabrechnung** - Zeitstempel basierend auf Arbeitszeiten
- **Pauschalabrechnung** - Festpreis für bestimmte Aufgaben
- **Zuschlagsabrechnung** - Zusätzliche Kosten oder Aufschläge
- **Mischabrechnung** - Kombination verschiedener Abrechnungstypen

### Rechnungsstruktur
- **Positionen** - Detailierte Aufteilung der Leistungen
- **Steuerwerte** - Mehrwertsteuer und andere Steuern
- **Fälligkeit** - Zahlungsfristen und Fälligkeitsdaten
- **Zahlungsstatus** - Offen, teilweise bezahlt, vollständig bezahlt
- **Mahnstatus** - Mahnungen und Erinnerungen

### Rechnungslebenszyklus
1. **Entwurf** - Rechnung wird erstellt
2. **Freigabe** - Rechnung wird freigegeben (nicht mehr änderbar)
3. **Archivierung** - Freigegebene Rechnung wird archiviert
4. **PDF-Erzeugung** - Rechnung wird als PDF generiert
5. **Buchhaltungsexport** - Rechnung wird an Buchhaltungssystem exportiert

## Datenbankstruktur

### Tabellen

#### billing_invoices
- id: UUID (Primary Key)
- invoice_number: String (Eindeutige Rechnungsnummer)
- status: String (draft, approved, archived)
- customer_id: UUID (Referenz auf Kunde)
- issue_date: DateTime (Ausstellungsdatum)
- due_date: DateTime (Fälligkeitsdatum)
- currency: String (Währung)
- total_amount: Decimal (Gesamtbetrag)
- tax_amount: Decimal (Steuern)
- net_amount: Decimal (Netto-Betrag)
- payment_status: String (open, partially_paid, paid)
- collection_status: String (none, reminder_sent, overdue)
- created_by_id: UUID (Ersteller)
- approved_by_id: UUID (Freigeber)
- approved_at: DateTime (Freigabedatum)
- archived_at: DateTime (Archivierungsdatum)
- created_at: DateTime
- updated_at: DateTime

#### billing_invoice_items
- id: UUID (Primary Key)
- invoice_id: UUID (Referenz auf Rechnung)
- type: String (hourly, flat_rate, surcharge, mixed)
- description: String (Beschreibung)
- quantity: Decimal (Menge)
- unit_price: Decimal (Einzelpreis)
- amount: Decimal (Betrag)
- tax_rate: Decimal (Steuersatz)
- tax_amount: Decimal (Steuern)
- net_amount: Decimal (Netto-Betrag)
- sort_order: Integer (Sortierreihenfolge)
- created_at: DateTime
- updated_at: DateTime

#### billing_invoice_payments
- id: UUID (Primary Key)
- invoice_id: UUID (Referenz auf Rechnung)
- amount: Decimal (Zahlungsbetrag)
- payment_date: DateTime (Zahlungsdatum)
- payment_method: String (Banktransfer, Credit Card, etc.)
- reference: String (Zahlungsreferenz)
- created_at: DateTime

#### billing_invoice_collections
- id: UUID (Primary Key)
- invoice_id: UUID (Referenz auf Rechnung)
- collection_type: String (reminder, overdue)
- sent_at: DateTime (Versanddatum)
- due_date: DateTime (Fälligkeitsdatum)
- amount: Decimal (Mahnbetrag)
- created_at: DateTime

## API-Endpoints

### Rechnungen
- `GET /api/v1/billing/invoices` - Liste aller Rechnungen
- `POST /api/v1/billing/invoices` - Erstellen einer Rechnung
- `GET /api/v1/billing/invoices/{invoice_id}` - Einzelne Rechnung abrufen
- `PUT /api/v1/billing/invoices/{invoice_id}` - Rechnung aktualisieren
- `DELETE /api/v1/billing/invoices/{invoice_id}` - Rechnung löschen (soft delete)
- `POST /api/v1/billing/invoices/{invoice_id}/approve` - Rechnung freigeben
- `POST /api/v1/billing/invoices/{invoice_id}/archive` - Rechnung archivieren
- `POST /api/v1/billing/invoices/{invoice_id}/generate-pdf` - PDF generieren
- `GET /api/v1/billing/invoices/{invoice_id}/pdf` - PDF herunterladen

### Zahlungen
- `POST /api/v1/billing/invoices/{invoice_id}/payments` - Zahlung buchen
- `GET /api/v1/billing/invoices/{invoice_id}/payments` - Zahlungen abrufen

### Mahnungen
- `POST /api/v1/billing/invoices/{invoice_id}/collections` - Mahnung versenden
- `GET /api/v1/billing/invoices/{invoice_id}/collections` - Mahnungen abrufen

## Rechnungsnummerierung

### Eindeutigkeit
- Rechnungsnummern sind eindeutig pro Unternehmen
- Format: `{Jahr}-{Monat}-{Laufende_Nummer}`
- Beispiel: `2026-11-001`

### Generierung
- Automatische Nummerngenerierung bei Erstellung
- Prüfung auf Duplikate
- Sicherstellung der Fortlaufung

## Abrechnungssystem

### Stundenabrechnung
- Zeitstempel basierend auf Arbeitszeiten
- Stundenpreis pro Aufgabe
- Rundung auf Minuten

### Pauschalabrechnung
- Festpreis für bestimmte Aufgaben
- Keine zeitbasierte Berechnung
- Direkte Zuweisung des Preises

### Zuschlagsabrechnung
- Zusätzliche Kosten oder Aufschläge
- Prozentuale oder feste Aufschläge
- Steuerbare Positionen

### Mischabrechnung
- Kombination verschiedener Abrechnungstypen
- Flexibles Positionsmanagement
- Automatische Berechnung

## Steuerberechnung

### Steuersätze
- Konfigurierbare Steuersätze
- Dynamische Steuerberechnung
- Mehrwertsteuer und andere Steuern

### Steuerberechnung
- Automatische Steuerberechnung bei Positionserstellung
- Prüfung auf gültige Steuersätze
- Konsistente Berechnung

## Freigabe-Prozess

### Freigabeverfahren
1. Rechnung wird erstellt (Entwurf)
2. Rechnung wird überprüft und korrigiert
3. Freigabe durch autorisierte Person
4. Freigegebene Rechnung kann nicht mehr geändert werden
5. Rechnung wird archiviert

### Sicherheitsmaßnahmen
- Nur autorisierte Benutzer können Rechnungen freigeben
- Freigabe wird protokolliert
- Änderungen nach Freigabe nicht erlaubt
- Nachvollziehbare Folgebelege bei Korrekturen

## PDF-Erzeugung

### Format
- PDF/A-Konform für Langzeitarchivierung
- Professionelles Layout
- Alle relevanten Informationen

### Inhalte
- Rechnungsdetails
- Kundeninformationen
- Zahlungsinformationen
- Steuerinformationen
- Zahlungsbedingungen

## Buchhaltungsexport

### Versionierte Schnittstelle
- Version 1.0 für erste Implementierung
- Strukturierte Datenausgabe
- Kompatible Formate

### Exportformate
- CSV-Export für Buchhaltungssysteme
- XML-Export für ERP-Systeme
- JSON-Export für moderne Systeme

### Datenintegrität
- Versionierte Schnittstellen
- Validierung der Exportdaten
- Nachvollziehbare Exporte

## Sicherheitsmaßnahmen

### Datenintegrität
- Freigegebene Rechnungen werden nicht still überschrieben
- Korrekturen erzeugen nachvollziehbare Folgebelege
- Transaktionelle Konsistenz
- Vollständige Audittrail

### Zugriffskontrolle
- Nur autorisierte Benutzer können Rechnungen erstellen/freigeben
- Berechtigungen werden über RBAC verwaltet
- Protokollierung aller Aktionen

## Testabdeckung

### Testfälle
- Freigegebene Rechnungen werden nicht überschrieben
- Berechnung ist reproduzierbar und transaktional
- Steuer-/Buchhaltungskonformität wird nicht ohne fachliche Prüfung behauptet
- Rundungs-, Berechtigungs-, Status- und Exporttests bestehen

### Qualitätssicherung
- Unit-Tests für Berechnungen
- Integrationstests für Rechnungslifecycle
- Security-Tests für Zugriffskontrolle
- Export-Tests für Buchhaltungssysteme

## Produktionskonfiguration

### Sicherheitseinstellungen
- Im Produktionsmodus werden alle Rechnungen transaktional verarbeitet
- Secure-Cookie-Verwendung
- Keine stille Klartext-Fallbacks
- Transaktionssichere Ausführung

### Empfohlene Praktiken
1. Regelmäßige Überprüfung der Rechnungsabläufe
2. Testen von Exportformaten in Testumgebung
3. Überwachung von Freigabeprozessen
4. Protokollierung aller Rechnungsvorgänge

## Fehlerbehandlung

### Häufige Fehler
- `invoice_already_approved` - Versuch, bereits freigegebene Rechnung zu ändern
- `invalid_calculation` - Ungültige Berechnung
- `missing_required_fields` - Fehlende Pflichtfelder
- `payment_already_processed` - Bereits verarbeitete Zahlung

### Diagnose
- Prüfe Rechnungsstatus
- Überprüfe Berechnungsdaten
- Prüfe Berechtigungen
- Überprüfe Protokolle für detaillierte Fehlermeldungen

## Compliance

### Datenschutz
- Alle Rechnungsdaten werden serverseitig gespeichert
- Keine sensiblen Daten im Klartext gespeichert
- Authentifizierung aller Rechnungsoperationen
- Audittrail für alle Rechnungsvorgänge

### Technische Sicherheit
- Authentifizierung aller API-Zugriffe
- Fail-closed-Design bei Sicherheitsfehlern
- Wiederherstellbarkeit bei Fehlern
- Transaktionssichere Ausführung

### Buchhaltungskonformität
- Steuer-/Buchhaltungskonformität wird nicht ohne fachliche Prüfung behauptet
- Vollständige Rechnungsdokumentation
- Nachvollziehbare Abrechnung