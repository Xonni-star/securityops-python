# Sichere Automatisierungsregeln

## Umfang

Die erste Ausbaustufe wertet ausschließlich persistierte Aufgabenereignisse der bestehenden Transactional Outbox aus:

| Auslöser | Quelle | Typisierte Bedingung |
|---|---|---|
| Aufgabe zugewiesen | `task.assigned` | optionaler Aufgabenstatus |
| Aufgabenstatus geändert | `task.status_changed` | optionaler Aufgabenstatus |

Die einzige Aktion lautet `notify_event_recipients`: Sie erzeugt eine zusätzliche In-App-Benachrichtigung für die bereits im Quellereignis festgelegten Empfänger. Eine Regel kann keine Empfänger-IDs, Nachrichten, SQL, Skripte oder freien Ausdrücke vorgeben. Die vorhandene Aufgaben-Sichtbarkeit schützt den Abruf von Benachrichtigungen weiterhin serverseitig.

Regeln werden nach einer Neuanlage zunächst deaktiviert. Konfigurationen enthalten nur den festen Trigger, optional einen Statusvergleich aus dem Aufgabenstatus-Katalog und die registrierte Aktion. Regeländerungen, Aktivierung und Löschung werden im Audit protokolliert. Eine Löschung deaktiviert die Regel und blendet sie aus; Ausführungshistorie und referenzierte Outbox-Ereignisse bleiben erhalten.

## Noch nicht verfügbare Auslöser und Aktionen

Qualifikationsablauf, unbesetzte Dienste, fehlende Kontrollen, Vorfälle, Schlüssel/Inventar, Dokumente/Verträge, Rechnungen, allgemeine Aufgabenfristen und Worker-Ausfall veröffentlichen aktuell keine geeigneten registrierten Outbox-Ereignisse. Sie sind deshalb in der Oberfläche nicht als auswählbare Regeln angeboten. Insbesondere gibt es keine zeitgesteuerten Auslöser und keine automatische Änderung von Personal-, Dienstplan-, OWKS-, Vertrags-, Rechnungs- oder Aufgabenstatus. Rechtlich oder finanziell relevante Aktionen werden nicht ausgeführt.

## HTTP-API und Berechtigung

Alle Endpunkte benötigen eine gültige Sitzung. Zusätzlich verlangt jeder Endpunkt `automations.manage`, das standardmäßig nur der Administratorrolle zugeordnet ist. Schreibanfragen unterliegen dem bestehenden CSRF-Schutz.

| Methode | Pfad | Zweck |
|---|---|---|
| GET/POST | `/api/v1/automations/rules` | aktive und deaktivierte Regeln einsehen / deaktivierte Regel anlegen |
| GET/PATCH/DELETE | `/api/v1/automations/rules/{rule_id}` | einzelne Regel lesen, ändern/aktivieren/deaktivieren oder weich löschen |
| GET | `/api/v1/automations/runs` | paginierte Automatisierungshistorie und Outbox-Versuche |
| GET | `/api/v1/automations/outbox-events` | fehlgeschlagene registrierte Ereignisse mit bereinigter Versuchshistorie |
| POST | `/api/v1/automations/runs/{run_id}/retry` | fehlgeschlagene Automatisierungsaktion kontrolliert wiederholen |
| POST | `/api/v1/automations/outbox-events/{event_id}/retry` | fehlgeschlagenes Aufgaben- oder Automatisierungsereignis kontrolliert wiederholen |

Unbekannte IDs werden nicht offengelegt. Historienendpunkte geben keine Ereignis-Payloads, Aufgabentitel oder Empfänger aus, sondern nur Regel-/Triggerbezeichnung, Status, Fehlercode und Versuchsdaten.

## Idempotenz, Wiederholungen und Fehler

Regel und Quellereignis identifizieren einen Lauf eindeutig. Die eindeutige Datenbankbedingung auf `(rule_id, source_event_id)` verhindert doppelte Lauferfassung. Die eindeutige Outbox-Kennung `automation:{rule_id}:{source_event_id}` sowie die bestehende Eindeutigkeit von Outbox-Empfänger-Benachrichtigungen schützen die Aktion bei erneuter Zustellung. Die Quellzustellung, Auswertung und Anlage von Lauf/Aktions-Outbox erfolgen transaktional. PostgreSQL-Worker verwenden weiterhin Claims mit `FOR UPDATE SKIP LOCKED`.

Die bereits vorhandene automatische Wiederholung verwendet exponentiellen Backoff (5 Sekunden bis höchstens eine Stunde). Der Zähler für fehlgeschlagene Ausführungen ist getrennt vom Claim-Zähler, damit abgestürzte/verwaiste Claims nicht als fehlgeschlagene Zustellungen zählen; beim Upgrade wird er aus vorhandenen `retry_scheduled`-/`dead_lettered`-Versuchen übernommen. Ungültige oder nicht unterstützte Ereignisse kommen direkt in `dead_letter`; temporäre Fehler werden nach Erreichen des konfigurierten Worker-Limits (Standard: acht fehlgeschlagene Versuche) dorthin verschoben. Ein Administrator kann einen Dead-Letter höchstens dreimal manuell erneut einreihen. Frühere Outbox-Attempt-Datensätze bleiben erhalten; Wiederholungen werden in den Audit-Logs festgehalten. Ein erfolgreich abgeschlossener Lauf kann nicht wiederholt werden.

## Aufbewahrung und Grenzen

Es gibt keine automatische Bereinigung oder zeitliche Aufbewahrungsfrist. Regeln werden weich gelöscht; Lauf- und Outbox-Referenzen bleiben erhalten. Attempt-Historien sind in PostgreSQL append-only. Laufstatus und Fehlercodes sind betriebliche Zustandsdaten und keine manipulationssichere Beweiskette gegen privilegierte Datenbankänderungen. Die Administratoroberfläche und API sind kein Nachweis für produktiven Workerbetrieb, Alarmierung oder fachliche Abnahme.
