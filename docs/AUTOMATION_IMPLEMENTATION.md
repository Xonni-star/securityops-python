# Automatisierungsregeln - Implementierungsdokumentation

Diese Dokumentation beschreibt die Implementierung der sicheren Automatisierungsregeln auf Basis der Outbox- und Worker-Infrastruktur gemäß Issue #51.

## Überblick

Die Implementierung bietet eine zentrale, nachvollziehbare Regelverwaltung basierend auf der bestehenden transaktionalen Outbox und Worker-Infrastruktur. Sie ermöglicht die Definition von Regeln mit Namen, Beschreibung, aktiviert/deaktiviert, fest registriertem Trigger, validierten typisierten Bedingungen und erlaubten Aktionen.

## Implementierte Funktionen

### 1. Regelsystem
- Regeln mit Name, Beschreibung, aktiviert/deaktiviert, fest registriertem Trigger
- Validierte typisierte Bedingungen (z.B. Aufgabenstatus)
- Erlaubte Aktionen (aktuell nur "notify_event_recipients")

### 2. Trigger-Unterstützung
Die folgenden Trigger sind implementiert:
- `task.assigned` - Aufgabe zugewiesen
- `task.status_changed` - Aufgabenstatus geändert
- `owks.missed_control` - Versäumte Kontrolle protokolliert
- `owks.deviation_reported` - OWKS-Auffälligkeit gemeldet
- `owks.offline_event_synced` - Offline-Ereignis synchronisiert
- `billing.invoice_approved` - Rechnung genehmigt
- `key.issued` - Schlüssel ausgegeben

### 3. Aktionen
- `notify_event_recipients` - Benachrichtigung an Ereignis-Empfänger

### 4. Sicherheitsfeatures
- Idempotente Ausführung über Outbox/Worker
- Eindeutiger Schlüssel je Regel und Quellereignis
- Sichere Retries/Dead-Letter
- Nachvollziehbare Ausführungsergebnisse
- Transaktionssichere parallele Worker-Tests

## Datenbankstruktur

### Tabellen

#### automation_rules
- id: UUID (Primary Key)
- name: String (100 Zeichen)
- description: String (500 Zeichen)
- trigger_type: String (Trigger-Typ)
- conditions: JSON (Validierte Bedingungen)
- action_type: String (Aktionstyp)
- is_active: Boolean
- created_by_id: UUID (Referenz auf Benutzer)
- updated_by_id: UUID (Referenz auf Benutzer)
- created_at: DateTime
- updated_at: DateTime
- deleted_at: DateTime (Soft Delete)

#### automation_runs
- id: UUID (Primary Key)
- rule_id: UUID (Referenz auf automation_rules)
- rule_name: String (Kopie für Performance)
- source_event_id: UUID (Referenz auf NotificationOutbox)
- action_event_id: UUID (Referenz auf NotificationOutbox)
- trigger_type: String (Trigger-Typ)
- status: String (Status des Runs)
- last_error: String (Fehlermeldung)
- manual_retry_count: Integer
- created_at: DateTime
- updated_at: DateTime

## API-Endpoints

### Regeln
- `GET /api/v1/automations/rules` - Liste aller Regeln
- `POST /api/v1/automations/rules` - Erstellen einer Regel
- `GET /api/v1/automations/rules/{rule_id}` - Einzelne Regel abrufen
- `PATCH /api/v1/automations/rules/{rule_id}` - Regel aktualisieren
- `DELETE /api/v1/automations/rules/{rule_id}` - Regel löschen (soft delete)

### Automatisierungsläufe
- `GET /api/v1/automations/runs` - Liste der Automatisierungsläufe
- `GET /api/v1/automations/outbox-events` - Liste der Dead-Letter-Ereignisse
- `POST /api/v1/automations/outbox-events/{event_id}/retry` - Wiederholung eines Dead-Letter-Ereignisses
- `POST /api/v1/automations/runs/{run_id}/retry` - Wiederholung eines Automatisierungslaufs

## Sicherheitsmechanismen

### Zugriffskontrolle
- Nur Benutzer mit der Berechtigung `automations.manage` können Regeln verwalten
- Jede Aktion wird in das Audit-System eingetragen
- Manipulierte Regel-/Ereignis-IDs können nicht gelesen/geändert werden

### Idempotenz
- Jede Regel wird nur einmal pro Quellereignis ausgeführt
- Parallele Worker werden transaktionssicher getestet
- Wiederholte Zustellung desselben Events führt höchstens zu einer effektiven Ausführung

## Implementierungsdetails

### 1. Regelverwaltung
Die Regelverwaltung ist vollständig implementiert mit:
- Validierung von Namen und Beschreibungen
- Prüfung von Bedingungen für spezielle Trigger-Typen
- Soft Delete für Regeln
- Audit Trail für alle Änderungen

### 2. Trigger-Verarbeitung
Die Trigger-Verarbeitung nutzt die bestehende Outbox-Infrastruktur:
- Ereignisse werden in die Outbox geschrieben
- Worker verarbeitet die Ereignisse und führt Regeln aus
- Ergebnisse werden in der AutomationRun-Tabelle protokolliert

### 3. Aktionen
Aktuell wird nur die Aktion `notify_event_recipients` unterstützt, die:
- Benachrichtigungen an die Empfänger des ursprünglichen Ereignisses sendet
- Die Benachrichtigungen über die bestehende Notification-Outbox-Infrastruktur sendet

## Testabdeckung

Die Implementierung ist mit Tests abgedeckt für:
- Triggerbedingungen
- Inaktivierung von Regeln
- Berechtigungen
- Idempotenz
- Retry/Dead-Letter
- Audit-Historie

## Produktionskonfiguration

### Sicherheitseinstellungen
- Im Produktionsmodus muss `AUTOMATIONS_ENABLED` gesetzt sein
- Secure-Cookies werden erzwungen
- Keine stille Klartext-Fallbacks
- Transaktionssichere Ausführung

### Empfohlene Praktiken
1. Regelmäßige Überprüfung der Automatisierungsläufe
2. Überwachung von Dead-Letter-Ereignissen
3. Testen von Regeländerungen in einer Testumgebung
4. Protokollierung aller Automatisierungsaktivitäten

## Fehlerbehandlung

### Häufige Fehler
- `AUTOMATIONS_ENABLED` nicht gesetzt
- Fehlende Berechtigungen für Automatisierungsoperationen
- Manipulierte Regel-IDs
- Ungültige Trigger-/Aktionstypen

### Diagnose
- Prüfe Konfigurationsdateien
- Überprüfe Audit-Logs für Berechtigungsfehler
- Prüfe Dead-Letter-Ereignisse für Ausführungsprobleme
- Überprüfe Protokolle für detaillierte Fehlermeldungen

## Compliance

### Datenschutz
- Alle Automatisierungsdaten werden serverseitig gespeichert
- Keine sensiblen Daten im Klartext gespeichert
- Authentifizierung aller Automatisierungsoperationen
- Audittrail für alle Automatisierungsaktionen

### Technische Sicherheit
- Authentifizierung aller API-Zugriffe
- Fail-closed-Design bei Sicherheitsfehlern
- Wiederherstellbarkeit bei Fehlern
- Transaktionssichere Ausführung