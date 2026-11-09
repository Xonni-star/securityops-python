# In-App-Benachrichtigungen

## Umfang

Der Benachrichtigungskern speichert derzeit ausschließlich In-App-Ereignisse für den vorhandenen Aufgaben-Kern. Eine tatsächliche Neuzuweisung oder Statusänderung erzeugt ein Outbox-Ereignis; eine unveränderte PATCH-Anfrage erzeugt kein neues Ereignis. Aufgabenänderung, Historie, Audit und Outbox werden in derselben Transaktion geschrieben. Der separate Worker erzeugt die Empfängerzeilen anschließend transaktional mit dem Abschluss des Outbox-Ereignisses.

Neue Zuweisungen benachrichtigen die neue verantwortliche Person, nicht die zuvor verantwortliche Person. Eine Statusänderung benachrichtigt die aktuelle verantwortliche Person und die erstellende Person, soweit sie nicht selbst handelnde Person sind. Beim Abschluss bleibt ein bereits erzeugter Eintrag erhalten. Ein Empfänger kann ihn jedoch nur sehen, solange die bestehende Aufgabenberechtigung den Zugriff auf die Aufgabe erlaubt. Nach einer Neuzuweisung verliert eine frühere verantwortliche Person ohne anderweitigen Aufgabenzugriff auch die Sichtbarkeit zugehöriger Benachrichtigungen; die gespeicherten Einträge werden dadurch nicht gelöscht.

## API und Berechtigungen

- `GET /api/v1/notifications?limit=25&offset=0&unread_only=false` liefert eine paginierte Empfängersicht mit Gesamtzahl und ungelesener Anzahl. `limit` ist auf 100 begrenzt.
- `PATCH /api/v1/notifications/{id}/read` markiert eine eigene, sichtbare Benachrichtigung als gelesen. Wiederholte Aufrufe sind idempotent. Fremde, nicht mehr sichtbare oder unbekannte IDs antworten einheitlich mit `404`.
- Beide Endpunkte verlangen eine gültige Sitzung und `notifications.read_own`. Zusätzlich wird die Empfänger-ID mit der Aufgaben-Sichtbarkeit des Aufgaben-Kerns verknüpft; die Client-Oberfläche ersetzt diese Prüfung nicht.

Die Migration `0020_notifications` vergibt die Berechtigung an die vorhandenen Standardrollen. Berechtigungen, Lesestatus und Aufgabenereignisse werden nicht über Frontend-Daten autorisiert oder aus Benutzereingaben übernommen.

## Outbox und Folgearbeit

`notification_outbox` wird in derselben Transaktion wie das Aufgabenereignis geschrieben. Ein eindeutiger Schlüssel auf der Aufgabenhistorienzeile verhindert doppelte Ereignisse; `uq_notifications_event_recipient` verhindert doppelte In-App-Einträge. Migration `0024_notification_outbox_worker` ergänzt Lock-/Lease-Felder sowie eine append-only Attempt-Historie mit Ereignis, Nummer, Fehlercode und Zeitstempel.

Der separate Compose-Dienst `notification-worker` verarbeitet ausschließlich `task.assigned` und `task.status_changed` zu In-App-Benachrichtigungen. Er verwendet PostgreSQL-Claims mit `FOR UPDATE SKIP LOCKED`, Lease-/Token-Schutz und Wiederaufnahme abgelaufener Claims; Erzeugung der Empfängerzeilen und Abschluss des Outbox-Ereignisses erfolgen atomar. Temporäre Fehler verwenden exponentiellen Backoff bis zu einer Stunde; ungültige/nicht unterstützte Ereignisse sowie nach ausgeschöpften Versuchen fehlerhafte Ereignisse wechseln nach `dead_letter`. Versuchshistorie wird über einen PostgreSQL-Trigger gegen UPDATE/DELETE geschützt. Der lokale CLI-Inspektionsbefehl zeigt keine Payloads oder Nachrichtentexte; ein öffentliches Monitoring-Endpunkt ist nicht vorhanden.

PR #39 ist mit Merge-Commit `a8cc63b3eeef9cbcdc033e4156ca046c14e8c99a` in `main` integriert. Der Worker führt außerdem den OWKS-Prüfzyklus aus; dieser Zyklus wurde aus dem API-Lifespan verlagert und nutzt weiterhin PostgreSQL-Advisory-Locks. Es gibt keinen E-Mail-/Push-Provider, keine Task-Erinnerungen/Eskalationen und keine Ereignisse aus anderen Modulen. CI- und Merge-Checks belegen keinen produktiven Workerbetrieb, Alarmierung oder fachliche Abnahme.

## Migration und Rückbau

`0020_notifications` folgt linear auf `0019_tasks`. Ein Downgrade wird abgelehnt, sobald Outbox- oder Benachrichtigungsdaten oder Berechtigungszuordnungen zu benutzerdefinierten Rollen vorhanden sind. Diese Daten müssen vor einem Rückbau ausdrücklich gesichert beziehungsweise fachlich behandelt werden.
