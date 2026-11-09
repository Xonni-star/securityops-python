# Sichere Automatisierungsregeln

## Umfang

Das Regelwerk wertet nur explizit registrierte Ereignisse der bestehenden Transactional Outbox aus:

| Auslöser | Quelle | Typisierte Bedingung |
|---|---|---|
| Aufgabe zugewiesen | `task.assigned` | optionaler Aufgabenstatus |
| Aufgabenstatus geändert | `task.status_changed` | optionaler Aufgabenstatus |
| Kontrollpunkt nicht kontrolliert | `owks.missed_control` aus dem idempotenten Routenmonitor | keine |
| OWKS-Auffälligkeit gemeldet | `owks.deviation_reported` bei einem persistierten OWKS-Ereignis vom Typ `deviation` | keine |
| Offline-Ereignis synchronisiert | `owks.offline_event_synced` nur für erfolgreich gespeicherte Offline-Ereignisse mit `sync_status=synced` | keine |

Die einzige Aktion lautet `notify_event_recipients`: Sie erzeugt eine zusätzliche In-App-Benachrichtigung für Empfänger der Quelle. Bei OWKS werden Empfänger zum Schreibzeitpunkt ausschließlich aus aktiven Benutzerkonten mit vorhandener Zuweisung zum nicht archivierten Objekt abgeleitet und beim Worker erneut geprüft. Bei später entfallener Objektzuweisung wird keine OWKS-Benachrichtigung an das Konto zugestellt; der Benachrichtigungsabruf prüft die aktuelle Zuweisung erneut.

OWKS-Outbox-Nutzdaten enthalten ausschließlich `schema_version=1`, OWKS-Ereignis-ID, Objekt-ID und die abgeleiteten Empfänger-IDs. Payloads werden gegen den zentralen Ereigniskatalog typisiert und mit zusätzlichen Feldern verboten validiert. Titel und Nachricht einer OWKS-Automationsbenachrichtigung stammen aus festen Texten und enthalten weder OWKS-Beschreibung noch Hergang, Kontrollpunkt- oder Routennamen. Ein Lauf ist eindeutig pro Regel und Quellereignis; erzeugte `automation.notification`-Ereignisse sind Aktionen und keine Trigger. Sie werden nicht erneut als Quellereignisse ausgewertet.

Regeln werden nach einer Neuanlage zunächst deaktiviert. Konfigurationen enthalten nur den festen Trigger, optional einen Statusvergleich aus dem Aufgabenstatus-Katalog und die registrierte Aktion. Regeländerungen, Aktivierung und Löschung werden im Audit protokolliert. Eine Löschung deaktiviert die Regel und blendet sie aus; Ausführungshistorie und referenzierte Outbox-Ereignisse bleiben erhalten.

## Noch nicht verfügbare Auslöser und Aktionen

Kontrollgang gestartet/beendet oder unvollständig, Qualifikationsablauf, unbesetzte Dienste, Vorfälle, Schlüssel/Inventar, Dokumente/Verträge, Rechnungen, allgemeine Aufgabenfristen und Worker-Ausfall veröffentlichen aktuell keine geeigneten registrierten Outbox-Ereignisse. Insbesondere wird ein OWKS-`control`-Scan nicht als Rundgangstart, Rundgangende oder bestätigte Anwesenheit interpretiert; eine manuelle „unvollständig“-Bewertung ist nicht implementiert. Diese Trigger sind in der Oberfläche nicht auswählbar. Es gibt keine zeitgesteuerten Auslöser und keine automatische Änderung von Personal-, Dienstplan-, OWKS-, Vertrags-, Rechnungs- oder Aufgabenstatus. Rechtlich oder finanziell relevante Aktionen werden nicht ausgeführt.

## HTTP-API und Berechtigung

Alle Endpunkte benötigen eine gültige Sitzung. Zusätzlich verlangt jeder Endpunkt `automations.manage`, das standardmäßig nur der Administratorrolle zugeordnet ist. Schreibanfragen unterliegen dem bestehenden CSRF-Schutz.

| Methode | Pfad | Zweck |
|---|---|---|
| GET/POST | `/api/v1/automations/rules` | aktive und deaktivierte Regeln einsehen / deaktivierte Regel anlegen |
| GET/PATCH/DELETE | `/api/v1/automations/rules/{rule_id}` | einzelne Regel lesen, ändern/aktivieren/deaktivieren oder weich löschen |
| GET | `/api/v1/automations/runs` | paginierte Automatisierungshistorie und Outbox-Versuche |
| GET | `/api/v1/automations/outbox-events` | fehlgeschlagene registrierte Ereignisse mit bereinigter Versuchshistorie |
| POST | `/api/v1/automations/runs/{run_id}/retry` | fehlgeschlagene Automatisierungsaktion kontrolliert wiederholen |
| POST | `/api/v1/automations/outbox-events/{event_id}/retry` | fehlgeschlagenes Aufgaben-, OWKS- oder Automatisierungsereignis kontrolliert wiederholen |

Unbekannte IDs werden nicht offengelegt. Historienendpunkte geben keine Ereignis-Payloads, Aufgabentitel oder Empfänger aus, sondern nur Regel-/Triggerbezeichnung, Status, Fehlercode und Versuchsdaten.

## Idempotenz, Wiederholungen und Fehler

Regel und Quellereignis identifizieren einen Lauf eindeutig. Die eindeutige Datenbankbedingung auf `(rule_id, source_event_id)` verhindert doppelte Lauferfassung. Die eindeutige Outbox-Kennung `automation:{rule_id}:{source_event_id}` sowie die bestehende Eindeutigkeit von Outbox-Empfänger-Benachrichtigungen schützen die Aktion bei erneuter Zustellung. OWKS-Quelle und versionierter Outbox-Eintrag werden in derselben Datenbanktransaktion geschrieben; die Quellzustellung, Auswertung und Anlage von Lauf/Aktions-Outbox erfolgen transaktional. PostgreSQL-Worker verwenden weiterhin Claims mit `FOR UPDATE SKIP LOCKED`.

Die bereits vorhandene automatische Wiederholung verwendet exponentiellen Backoff (5 Sekunden bis höchstens eine Stunde). Der Zähler für fehlgeschlagene Ausführungen ist getrennt vom Claim-Zähler, damit abgestürzte/verwaiste Claims nicht als fehlgeschlagene Zustellungen zählen; beim Upgrade wird er aus vorhandenen `retry_scheduled`-/`dead_lettered`-Versuchen übernommen. Ungültige oder nicht unterstützte Ereignisse kommen direkt in `dead_letter`; temporäre Fehler werden nach Erreichen des konfigurierten Worker-Limits (Standard: acht fehlgeschlagene Versuche) dorthin verschoben. Ein Administrator kann einen Dead-Letter höchstens dreimal manuell erneut einreihen. Frühere Outbox-Attempt-Datensätze bleiben erhalten; Wiederholungen werden in den Audit-Logs festgehalten. Ein erfolgreich abgeschlossener Lauf kann nicht wiederholt werden.

## Aufbewahrung und Grenzen

Es gibt keine automatische Bereinigung oder zeitliche Aufbewahrungsfrist. Regeln werden weich gelöscht; Lauf- und Outbox-Referenzen bleiben erhalten. Attempt-Historien sind in PostgreSQL append-only. Laufstatus und Fehlercodes sind betriebliche Zustandsdaten und keine manipulationssichere Beweiskette gegen privilegierte Datenbankänderungen. Die Administratoroberfläche und API sind kein Nachweis für produktiven Workerbetrieb, Alarmierung oder fachliche Abnahme.
