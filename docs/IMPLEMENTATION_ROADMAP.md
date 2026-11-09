# Priorisierte Implementierungs-Roadmap

Diese Roadmap basiert auf dem geprüften `main`-Stand vom 09.11.2026 (SHA `0b32db6809d763dc58d003ce0657d1af03666a52`), Alembic-Head `0035_worker_monitoring` und der Live-Abfrage der Issues und Pull Requests. Die aktuelle Momentaufnahme steht in [`PROJECT_STATUS.md`](PROJECT_STATUS.md). Prioritäten unterscheiden Implementierung, CI, fachliche Entscheidungen/Abnahme und produktiven Nachweis.

## P0 – Betreiberabnahme und produktiven Betrieb belegen

1. **Issue #56 – sehr hohe Priorität, offen.** PR #57 hat versionierte AES-256-GCM-Verschlüsselung, externen Schlüsselring und ein explizites, wiederaufnehmbares Rekey-Werkzeug in `main` integriert (Migration `0033_encrypted_document_storage`). Die Migration selbst verschlüsselt vorhandene Dateien nicht. Betreiber-Schlüsselbereitstellung, Bestandsmigration/Rotation in der Zielumgebung und Abnahme sind nicht nachgewiesen. Produktionsbetrieb darf bei fehlendem/ungültigem Schlüssel nicht auf Klartext zurückfallen; Bestandsdateien nur kontrolliert, wiederaufnehmbar und nicht-destruktiv umschlüsseln.
2. **Issue #9 bleibt offen.** Die Repository-Konfiguration enthält getrennte PostgreSQL-Rollen, Redis-Rate-Limits, statische Frontend-Auslieferung, Release-Migrationen, ClamAV und Backup-/Restore-Hilfen. PR #58 hat Worker-/Outbox-Monitoring in `main` integriert (Migration `0035_worker_monitoring`). Das implementierte Heartbeat-/Monitoring ersetzt weder produktiven Rollout noch TLS-/Proxy-/DNS-Konfiguration, Secret-Verwaltung, externe Alarmierung/Incident-Abläufe oder regelmäßig ausgeführte Wiederherstellung aus echten Betreiber-Sicherungen. CI-Restoreläufe ersetzen diese Nachweise nicht.
3. Backupziel, Verschlüsselung, Schlüsseltrennung, Aufbewahrung/Löschung, Wiederanlaufplan und Restoreübungen für den jeweiligen Betrieb festlegen und nachweisen. Keine Bestandsdateien rückwirkend als gescannt behandeln; ClamAV prüft neue unterstützte Uploads fail-closed.
4. Audit-/Datenbankrollen, MFA/Sitzungsverwaltung, Scopes und Uploadpfade unabhängig sicherheitsprüfen. Die Audit-Hashkette schützt nicht gegen privilegierte Änderungen durch Datenbank-Owner/Superuser; Prüfpunkte und Sicherungen müssen dafür außerhalb der Datenbank getrennt vorliegen.

## P1 – Fachentscheidungen und Portalgrenzen

1. **Issue #7 bleibt offen.** Für das implementierte Rechnungswesen müssen fachlich bestätigte Tarif-, Zuschlags-, Rundungs-, Steuer-, Korrektur- und Buchhaltungsexportregeln festgelegt und anhand der Akzeptanzkriterien geprüft werden. `Decimal`/`NUMERIC`, PDF und Export belegen keine Steuer- oder Buchhaltungskonformität.
2. **Issue #52 ist geschlossen.** PR #55 integriert die Rücknahme eigener offener Abwesenheits-/Verfügbarkeitsanträge sowie eine explizite, widerrufbare Freigabe von Qualifikationsdateien. Allgemeine Personal-/Vertragsdokumente bleiben ausgeschlossen; vertrauliche interne Personalunterlagen dürfen nicht generisch sichtbar werden.
3. Issue #10 ist laut GitHub am 09.11.2026 nach Integration der Planungs-/Vertretungsfunktionen geschlossen. Das bestätigt die Issue-Akzeptanzkriterien, nicht die gesetzliche Konformität konfigurierter Ruhezeiten oder eine externe arbeitsrechtliche Abnahme.

## P2 – Sichere Automatisierungsregeln

**Issue #51 ist offen.** PR #54 integriert ein eingeschränktes Regelwerk für `task.assigned` und `task.status_changed`, mit typisierter Aufgabenstatus-Bedingung, In-App-Benachrichtigungsaktion, Admin-Oberfläche, Ausführungshistorie und Dead-Letter-Wiederholung. PR #59 ergänzt begrenzte OWKS-Auslöser (`owks.missed_control`, `owks.deviation_reported`, `owks.offline_event_synced`). Das Issue bleibt offen, bis der weitere Umfang und die fachlichen Akzeptanzkriterien abgestimmt sind. Keine beliebigen SQL-Ausdrücke, Skripte oder dynamische Codeausführung ergänzen.

## P3 – Betriebsqualität und vollständiger Nachweis

1. E2E-, Berechtigungs-, Race-/PostgreSQL-, Upload-/Malware-, Last- und Wiederherstellungstests dort ergänzen, wo Risiko und reale Integrationsgrenzen es erfordern.
2. Datenschutz-/Aufbewahrung, externe Audit-Prüfpunkte, Monitoring/Incident-Prozess und Betreiberverantwortung konkret festlegen und nachweisen. Worker-/Outbox-Monitoring ist in `main` implementiert; externe Alarmierung und produktiver Betrieb sind nicht nachgewiesen.
3. Fachbereiche wie Kundenportal, Mitarbeiterportal, globale Suche, Inventar, Leitstelle und Rechnungswesen anhand ihrer tatsächlichen Nutzerrollen und Datenbereichsgrenzen abnehmen. Grüne CI oder ein geschlossener GitHub-Vorgang ersetzt keine unabhängige fachliche, rechtliche, steuerliche oder produktive Prüfung.

## GitHub-Lage am Prüftag

- PRs #40, #42, #43, #44, #46, #47, #49, #50, #54, #55, #57, #58 und #59 sind gemergt; der aktuelle `main`-SHA ist `0b32db6809d763dc58d003ce0657d1af03666a52`, Alembic-Head `0035_worker_monitoring`. PR #53 ist der einzige offene PR.
- Issues #7, #9, #51 und #56 sind offen; #10 und #52 sind geschlossen. Für die integrierten PR-Änderungen waren die angezeigten CI-Prüfungen erfolgreich. Diese Nachweise belegen weder fachliche Abnahme noch Betreiber-Schlüsselkonfiguration, produktive Dateimigration/Rotation, externe Alarmierung oder Betreiber-Restore.
- CI, fachliche Abnahme und produktive Prüfung sind unterschiedliche Nachweise. Insbesondere belegen Merge und CI weder Betreiber-Restore noch Produktionsfreigabe oder Rechts-/Steuerkonformität.

## Abhängigkeiten und Abschlusskriterien

- Kunden → Objekte → Personal/Qualifikationen → Dienstplanung → Zeiterfassung/OWKS → Dokumente/Verträge → Abrechnung bleibt die fachliche Datenabhängigkeit.
- Jede Datenbankerweiterung erhält eine Alembic-Migration und passende Schema-, API-, Rechte-, UI- und Integrationstests. Bestehende Geschäfts- und Auditdaten nicht stillschweigend überschreiben; Korrekturen müssen nachvollziehbar sein.
- Geldwerte verwenden bestätigte Rechenregeln und `Decimal`/`NUMERIC`; Zeitpunkte werden UTC gespeichert. Lokale Dienstzeiten benötigen IANA-Zeitzonen und geprüfte DST-Fälle.
- „Implementiert“, „CI-grün“, „fachlich abgenommen“ und „produktiv geprüft/freigegeben“ sind getrennte Zustände. Keine Produktionsreife oder Rechts-/Steuerkonformität ohne konkreten und unabhängig geprüften Nachweis behaupten.
