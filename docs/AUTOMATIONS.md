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
| Rechnung manuell freigegeben | `billing.invoice_approved` nach erfolgreicher manueller Freigabe über den berechtigten Billing-Endpunkt | keine |
| Schlüssel ausgegeben | `key.issued` nach bestätigter Ausgabe und append-only gespeicherter Schlüsselbewegung | keine |

Die einzige Aktion lautet `notify_event_recipients`: Sie erzeugt eine zusätzliche In-App-Benachrichtigung für Empfänger der Quelle. Bei OWKS werden Empfänger zum Schreibzeitpunkt ausschließlich aus aktiven Benutzerkonten mit vorhandener Zuweisung zum nicht archivierten Objekt abgeleitet und beim Worker erneut geprüft. Bei später entfallener Objektzuweisung wird keine OWKS-Benachrichtigung an das Konto zugestellt; der Benachrichtigungsabruf prüft die aktuelle Zuweisung erneut. Rechnungsbenachrichtigungen gehen nur an aktive Konten mit `billing.invoices.read` und `notifications.read_own`; der Worker prüft beide Rechte vor der Aktion erneut und der Benachrichtigungsabruf verlangt aktuelle Rechnungsleseberechtigung.

Schlüsselbenachrichtigungen gehen nur an aktive Konten mit `keys.read` und `notifications.read_own`, die dem nicht archivierten Schlüsselobjekt zugewiesen sind. Der Worker prüft Objektzuweisung und beide Rechte erneut; der Benachrichtigungsabruf verlangt weiterhin `keys.read` und dieselbe Objektzuweisung. Die Payload enthält nur `schema_version=1`, Schlüsselbewegungs-ID, Objekt-ID und Empfänger-IDs; Schlüsselnummer, Mitarbeiter, Quittierung und Bewegungsnotiz werden nicht kopiert. Die Benachrichtigung nennt ausschließlich die bestätigte Ausgabe und enthält keine Schlüssel- oder Personendaten.

OWKS-Outbox-Nutzdaten enthalten ausschließlich `schema_version=1`, OWKS-Ereignis-ID, Objekt-ID und die abgeleiteten Empfänger-IDs. `billing.invoice_approved` enthält ausschließlich `schema_version=1`, Rechnungs-ID und abgeleitete Empfänger-IDs; Beträge, Rechnungspositionen, Kundennarrative, Rechnungsnummer und sonstige Finanz-/Personendaten werden nicht kopiert. Alle Payloadtypen werden gegen den zentralen Ereigniskatalog typisiert und mit zusätzlichen Feldern verboten validiert. Titel und Nachricht einer OWKS-Automationsbenachrichtigung stammen aus festen Texten und enthalten weder OWKS-Beschreibung noch Hergang, Kontrollpunkt- oder Routennamen. Die Rechnungsaktion verwendet ebenfalls ausschließlich feste neutrale Texte; eine Regelbezeichnung wird nicht in die Nachricht übernommen. Ein Lauf ist eindeutig pro Regel und Quellereignis; erzeugte `automation.notification`-Ereignisse sind Aktionen und keine Trigger. Die Benachrichtigung speichert den registrierten Quelltrigger für die Berechtigungsprüfung, wertet ihn aber nicht erneut aus.

Die Rechnungsfreigabe und das versionierte `billing.invoice_approved`-Outbox-Ereignis werden in derselben Transaktion gespeichert. Ein eindeutiger Outbox-Schlüssel pro Rechnung und die bestehende Eindeutigkeit von Regel-/Quellereignisläufen sowie Empfängerbenachrichtigungen sichern Wiederholungen ab. Bei nicht mehr berechtigten Empfängern wird das Quellereignis fail-closed in die Fehlerablage verschoben; der Worker stellt die Aktion nur aktuellen Lesern zu. Die Benachrichtigung ist rein informativ und ändert weder Rechnungsstatus noch Zahlung/Mahnung, erzeugt keine Rechnung und erteilt keine Freigabe.

Regeln werden nach einer Neuanlage zunächst deaktiviert. Konfigurationen enthalten nur den festen Trigger, optional einen Statusvergleich aus dem Aufgabenstatus-Katalog und die registrierte Aktion. Regeländerungen, Aktivierung und Löschung werden im Audit protokolliert. Eine Löschung deaktiviert die Regel und blendet sie aus; Ausführungshistorie und referenzierte Outbox-Ereignisse bleiben erhalten.

## Offener Umfang von Issue #51

Der aktuelle `main`-Stand registriert ausschließlich die sieben oben aufgeführten Auslöser. Eine weitere sichere Implementierung lässt sich aus dem Issue nicht ableiten: Für die übrigen gewünschten Arbeitsabläufe fehlen entweder ein belegbares Quellereignis oder fachliche Regeln, die ein eindeutiges Ereignis und eine sichere Aktion festlegen. Das gilt insbesondere für Qualifikationsablauf, unbesetzte Dienste, Vorfälle, Schlüsselrückgabe/Überfälligkeit, Dokumente/Verträge, Rechnungszahlung/Mahnung, Aufgabenfristen und zeitgesteuerte Erinnerungen. Das Schlüsselmodell enthält keine Rückgabefrist; `key.issued` belegt nur eine bestätigte Ausgabe.

Vor der Umsetzung jedes weiteren Auslösers müssen mindestens der konkrete Geschäftsablauf und sein Quellsystem, die genaue Ereignisbedingung und ihr Zeitpunkt, berechtigte Empfänger und Datenbereich, erlaubte Aktion einschließlich nötiger menschlicher Freigaben sowie Retry- und Aufbewahrungsverhalten festgelegt werden. Bei zeitbezogenen Auslösern sind zusätzlich Frist, Zeitzone und der Umgang mit Änderungen oder Stornierungen zu spezifizieren. Bis diese Entscheidungen und ein passendes transaktionales Quellereignis vorliegen, bleiben solche Auslöser nicht auswählbar und werden nicht simuliert.

## Noch nicht verfügbare Auslöser und Aktionen

Kontrollgang gestartet/beendet oder unvollständig, Qualifikationsablauf, unbesetzte Dienste, Vorfälle, ausbleibende Schlüsselrückgabe/Inventar, Dokumente/Verträge, Rechnungszahlung/Mahnung, allgemeine Aufgabenfristen und Worker-Ausfall veröffentlichen aktuell keine geeigneten registrierten Outbox-Ereignisse. `key.issued` meldet nur eine bestätigte Ausgabe; das Schlüsselmodell enthält keine Rückgabefrist, daher gibt es keine Überfälligkeits- oder Rückgabeerinnerung. Insbesondere wird ein OWKS-`control`-Scan nicht als Rundgangstart, Rundgangende oder bestätigte Anwesenheit interpretiert; eine manuelle „unvollständig“-Bewertung ist nicht implementiert. Diese Trigger sind in der Oberfläche nicht auswählbar. Es gibt keine zeitgesteuerten Auslöser und keine automatische Änderung von Personal-, Dienstplan-, OWKS-, Vertrags-, Rechnungs-, Schlüssel- oder Aufgabenstatus. Rechtlich oder finanziell relevante Aktionen werden nicht ausgeführt; die Rechnungsregel reagiert ausschließlich nach einer menschlichen Freigabe und bleibt informativ.

## HTTP-API und Berechtigung

Alle Endpunkte benötigen eine gültige Sitzung. Zusätzlich verlangt jeder Endpunkt `automations.manage`, das standardmäßig nur der Administratorrolle zugeordnet ist. Schreibanfragen unterliegen dem bestehenden CSRF-Schutz.

| Methode | Pfad | Zweck |
|---|---|---|
| GET/POST | `/api/v1/automations/rules` | aktive und deaktivierte Regeln einsehen / deaktivierte Regel anlegen |
| GET/PATCH/DELETE | `/api/v1/automations/rules/{rule_id}` | einzelne Regel lesen, ändern/aktivieren/deaktivieren oder weich löschen |
| GET | `/api/v1/automations/runs` | paginierte Automatisierungshistorie und Outbox-Versuche |
| GET | `/api/v1/automations/outbox-events` | fehlgeschlagene registrierte Ereignisse mit bereinigter Versuchshistorie |
| POST | `/api/v1/automations/runs/{run_id}/retry` | fehlgeschlagene Automatisierungsaktion kontrolliert wiederholen |
| POST | `/api/v1/automations/outbox-events/{event_id}/retry` | fehlgeschlagenes Aufgaben-, OWKS-, Rechnungsfreigabe-, Schlüssel-Ausgabe- oder Automatisierungsereignis kontrolliert wiederholen |

Unbekannte IDs werden nicht offengelegt. Historienendpunkte geben keine Ereignis-Payloads, Aufgabentitel oder Empfänger aus, sondern nur Regel-/Triggerbezeichnung, Status, Fehlercode und Versuchsdaten.

## Idempotenz, Wiederholungen und Fehler

Regel und Quellereignis identifizieren einen Lauf eindeutig. Die eindeutige Datenbankbedingung auf `(rule_id, source_event_id)` verhindert doppelte Lauferfassung. Die eindeutige Outbox-Kennung `automation:{rule_id}:{source_event_id}` sowie die bestehende Eindeutigkeit von Outbox-Empfänger-Benachrichtigungen schützen die Aktion bei erneuter Zustellung. OWKS-Quelle und versionierter Outbox-Eintrag werden in derselben Datenbanktransaktion geschrieben; die Quellzustellung, Auswertung und Anlage von Lauf/Aktions-Outbox erfolgen transaktional. PostgreSQL-Worker verwenden weiterhin Claims mit `FOR UPDATE SKIP LOCKED`.

Die bereits vorhandene automatische Wiederholung verwendet exponentiellen Backoff (5 Sekunden bis höchstens eine Stunde). Der Zähler für fehlgeschlagene Ausführungen ist getrennt vom Claim-Zähler, damit abgestürzte/verwaiste Claims nicht als fehlgeschlagene Zustellungen zählen; beim Upgrade wird er aus vorhandenen `retry_scheduled`-/`dead_lettered`-Versuchen übernommen. Ungültige oder nicht unterstützte Ereignisse kommen direkt in `dead_letter`; temporäre Fehler werden nach Erreichen des konfigurierten Worker-Limits (Standard: acht fehlgeschlagene Versuche) dorthin verschoben. Ein Administrator kann einen Dead-Letter höchstens dreimal manuell erneut einreihen. Frühere Outbox-Attempt-Datensätze bleiben erhalten; Wiederholungen werden in den Audit-Logs festgehalten. Ein erfolgreich abgeschlossener Lauf kann nicht wiederholt werden.

## Aufbewahrung und Grenzen

Es gibt keine automatische Bereinigung oder zeitliche Aufbewahrungsfrist. Regeln werden weich gelöscht; Lauf- und Outbox-Referenzen bleiben erhalten. Attempt-Historien sind in PostgreSQL append-only. Laufstatus und Fehlercodes sind betriebliche Zustandsdaten und keine manipulationssichere Beweiskette gegen privilegierte Datenbankänderungen. Die Administratoroberfläche und API sind kein Nachweis für produktiven Workerbetrieb, Alarmierung oder fachliche Abnahme.
