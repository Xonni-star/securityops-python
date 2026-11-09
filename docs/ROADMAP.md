# Roadmap

Die verbindliche Priorisierung, Abhängigkeiten und der aktuelle `main`-/PR-Status stehen in [`IMPLEMENTATION_ROADMAP.md`](IMPLEMENTATION_ROADMAP.md) und [`PROJECT_STATUS.md`](PROJECT_STATUS.md).

## Reihenfolge nach fachlichen Abhängigkeiten

1. Sicherheits- und Betriebsgrundlagen: Authentifizierung/RBAC prüfen und ausbauen, Backup/Restore, TLS/Reverse Proxy, Monitoring, Auditgrenzen und Datenschutz.
2. Fachliche Abnahme der in `main` implementierten Module und Nachverfolgung offener Akzeptanzthemen. Bei der Live-Prüfung am 09.11.2026 waren #7, #9, #51 und #56 offen; #8 und #10 waren geschlossen (aktueller Status: [`PROJECT_STATUS.md`](PROJECT_STATUS.md)).
3. OWKS (gemergter PR #23, Issue #3 geschlossen) auf Objekten, Personal und Zuweisungen fachlich weiter prüfen; statische QR/NFC-Kennungen sind kein physischer Präsenznachweis.
4. Dokumenten-/Vertragsverwaltung (gemergter PR #24) sowie geschützte Dateiablage/Vertragsregeln anhand fachlicher Akzeptanz prüfen.
5. Rechnungswesen (Issue #7, PR #27 gemergt) auf fachlich freigegebenen Verträgen und Leistungsnachweisen fachlich abnehmen; Steuer-/Buchhaltungsrichtigkeit ist nicht belegt.
6. E2E-/Last-/Sicherheits-/Restoretests und eine eigenständige Betriebsabnahme.

PR #26 ist gemergt und hat wöchentliche Verfügbarkeiten, Dienstwünsche/Sperrzeiten und Vertretungen in `main` ergänzt; Issue #10 wurde nach Abgleich der Issue-Akzeptanzkriterien geschlossen. Das bestätigt keine gesetzliche Ruhezeitkonformität oder externe arbeitsrechtliche Abnahme. PR #27 ist gemergt; Migration `0017_billing` folgt auf `0016_scheduling_availability` und Rechnungswesen ist in `main`. Issue #7 bleibt trotz Merge offen, bis die fachlichen Kriterien abgeglichen sind.

PR #28 ist gemergt und hat Produktions-Compose, Redis-Rate-Limiting, separate Release-Migrationen, verschlüsselte Backup-/Restorewerkzeuge und Security-Scanning ergänzt. PR #31 ist ebenfalls gemergt und ergänzt optionales TOTP-MFA, Recovery-Codes, Sitzungsliste/-widerruf und administrativen Passwortreset. PR #33 ergänzt fail-closed ClamAV-Scans für neue Dokument-/Vertragsdateien, Versionen, OWKS-Anhänge und Personal-Qualifikationsdateien; bestehende Dateien werden nicht rückwirkend geprüft. PR #34 ergänzt Aufgaben mit Revision `0019_tasks`; der Kern ist nicht automatisch mit Fachmodulen verknüpft. Issue #9 bleibt offen. CI- und synthetische Restoreprüfungen sind keine produktive Betriebsabnahme oder regelmäßige Restoreübung; MFA und Uploadscan sind keine unabhängige Sicherheitsabnahme.

PR #35 ist in `main` gemergt und `0020_notifications` ergänzt In-App-Benachrichtigungen bei Aufgaben-Neuzuweisung und Statuswechsel. PR #39 ist mit `0024_notification_outbox_worker` ebenfalls in `main` integriert: ein separater Worker verarbeitet diese Task-Ereignisse mit Lease, Retry/Backoff, Dead-Letter-Status und Attempt-Historie und führt den OWKS-Prüfzyklus aus. E-Mail-/Push-Versand, Task-Erinnerungen/Eskalationen und Ereignisse aus anderen Modulen sind nicht enthalten. PR #38 und PR #25 sind gemergt; PR #40 ist mit `0025_unique_incident_owks_event` ebenfalls Bestandteil von `main` (aktueller PR-Status: [`PROJECT_STATUS.md`](PROJECT_STATUS.md)).

PR #36 ist mit `0021_key_management` ebenfalls in `main` gemergt. Das objektgebundene Register protokolliert Schlüsselbewegungen append-only und verlangt bei Ausgabe eine aktive, dem Objekt zugewiesene Person sowie Quittierung. Die digitale Quittierung ist keine qualifizierte elektronische Signatur oder ein Nachweis physischer Verwahrung; Freitext-Zutrittsangaben werden nicht migriert.

PR #37 ist mit `0022_incident_management` in `main` gemergt. Das Incident-Modul ist objektgebunden, trennt Vorfall-/Schreibrechte von Sensitivitätsrechten für Hergang, Abschlussbericht, Beteiligte und Dateien und prüft diesen Scope serverseitig. PDF-/Bildanhänge werden vor Ablage fail-closed mit ClamAV geprüft, privat gespeichert und nur autorisiert ausgeliefert; History, Personen- und Dateireferenzen haben Append-only-Trigger. Es gibt keine automatische Aufgaben-/Benachrichtigungsintegration, Fristerinnerung oder Eskalationsregel.

PR #38 wurde mit Migration `0023_control_room_permission` in `main` integriert. Die Leitstellenübersicht berechnet eine Momentaufnahme aus bestehenden Quellen, begrenzt Listen auf 100 Elemente und prüft das neue Recht `control_room.read` sowie Objekt- und Fachbereichsrechte. Es werden keine neuen Fachdatentabellen angelegt, keine Alarmmeldungen simuliert und keine sensiblen Vorfalldetails/Anhänge ausgegeben. Auf dem geprüften `main`-Stand ist `0035_worker_monitoring` der aktuelle Alembic-Head; die Leitstellenmigration `0023` und `0024_notification_outbox_worker` sind historische Revisionen der Kette (aktueller Stand: [`PROJECT_STATUS.md`](PROJECT_STATUS.md)). Issue #9 und die fachlichen Akzeptanzfragen bleiben davon getrennt.

Reihenfolge stellt keinen Implementierungs- oder Rechtsstatus dar. Keine Produktions-, Rechts- oder Steuerfreigabe wird behauptet.
