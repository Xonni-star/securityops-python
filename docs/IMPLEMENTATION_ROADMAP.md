# Priorisierte Implementierungs-Roadmap

Diese Roadmap basiert auf dem geprüften `main`-Stand vom 09.11.2026 (SHA `463ddba0fa1173d5c8a068362cd2f6af96018820`), Alembic-Head `0030_inventory_management` und der Live-Abfrage der Issues und Pull Requests. Die aktuelle Momentaufnahme steht in [`PROJECT_STATUS.md`](PROJECT_STATUS.md). Prioritäten unterscheiden Implementierung, CI, fachliche Entscheidungen/Abnahme und produktiven Nachweis.

## P0 – Betreiberabnahme und produktiven Betrieb belegen

1. **Issue #56 – sehr hohe Priorität, offen.** Verschlüsselung ruhender Nutzdaten im gemeinsamen privaten Dateispeicher sowie explizite Bestandsmigration und sichere Schlüsselrotation fehlen in `main`. PR #57 schlägt versionierte AES-256-GCM-Verschlüsselung, externen Schlüsselring und einen wiederaufnehmbaren Rekey-Prozess vor; er ist offen, auf PR #55 gestapelt und seine CI ist grün. Das ist kein Nachweis einer Implementierung in `main` oder einer produktiven Migration. Schlüssel müssen aus externer Konfiguration kommen; Produktionsbetrieb darf bei fehlendem/ungültigem Schlüssel nicht auf Klartext zurückfallen. Bestandsdateien nur über einen geprüften, wiederaufnehmbaren und nicht-destruktiven Vorgang umschlüsseln.
2. **Issue #9 bleibt offen.** Die Repository-Konfiguration enthält getrennte PostgreSQL-Rollen, Redis-Rate-Limits, statische Frontend-Auslieferung, Release-Migrationen, ClamAV und Backup-/Restore-Hilfen. PR #58 schlägt Worker-/Outbox-Monitoring vor, ist jedoch ein Draft und nicht Bestandteil von `main`. Auch nach Integration eines Monitoring-Endpunkts wären produktiver Rollout, TLS-/Proxy-/DNS-Konfiguration, Secret-Verwaltung, Alarmierung/Incident-Abläufe und regelmäßig ausgeführte Wiederherstellung aus echten Betreiber-Sicherungen gesondert nachzuweisen. CI-Restoreläufe ersetzen diese Nachweise nicht.
3. Backupziel, Verschlüsselung, Schlüsseltrennung, Aufbewahrung/Löschung, Wiederanlaufplan und Restoreübungen für den jeweiligen Betrieb festlegen und nachweisen. Keine Bestandsdateien rückwirkend als gescannt behandeln; ClamAV prüft neue unterstützte Uploads fail-closed.
4. Audit-/Datenbankrollen, MFA/Sitzungsverwaltung, Scopes und Uploadpfade unabhängig sicherheitsprüfen. Die Audit-Hashkette schützt nicht gegen privilegierte Änderungen durch Datenbank-Owner/Superuser; Prüfpunkte und Sicherungen müssen dafür außerhalb der Datenbank getrennt vorliegen.

## P1 – Fachentscheidungen und Portalgrenzen

1. **Issue #7 bleibt offen.** Für das implementierte Rechnungswesen müssen fachlich bestätigte Tarif-, Zuschlags-, Rundungs-, Steuer-, Korrektur- und Buchhaltungsexportregeln festgelegt und anhand der Akzeptanzkriterien geprüft werden. `Decimal`/`NUMERIC`, PDF und Export belegen keine Steuer- oder Buchhaltungskonformität.
2. **Issue #52 bleibt offen.** PR #55 schlägt die Rücknahme eigener offener Abwesenheits-/Verfügbarkeitsanträge sowie eine explizite, widerrufbare Freigabe von Qualifikationsdateien vor. PR #55 ist offen und auf PR #54 gestapelt, daher ist die Folgearbeit noch nicht Bestandteil von `main`. Laut Beschreibung bleiben allgemeine Personal-/Vertragsdokumente ausgeschlossen; vertrauliche interne Personalunterlagen dürfen nicht generisch sichtbar werden.
3. Issue #10 ist laut GitHub am 09.11.2026 nach Integration der Planungs-/Vertretungsfunktionen geschlossen. Das bestätigt die Issue-Akzeptanzkriterien, nicht die gesetzliche Konformität konfigurierter Ruhezeiten oder eine externe arbeitsrechtliche Abnahme.

## P2 – Sichere Automatisierungsregeln

**Issue #51 ist offen.** PR #54 schlägt ein eingeschränktes Regelwerk für die vorhandenen Auslöser `task.assigned` und `task.status_changed` vor, mit typisierter Aufgabenstatus-Bedingung, In-App-Benachrichtigungsaktion, Admin-Oberfläche, Ausführungshistorie und Dead-Letter-Wiederholung. PR #54 ist offen und nicht Bestandteil von `main`; laut aktueller PR-Prüfung sind die CI-Checks erfolgreich und das Security-Review fand keine Findings. Das Issue bleibt offen, bis der vorgeschlagene Umfang integriert und mit den Issue-Akzeptanzkriterien abgeglichen ist. Keine beliebigen SQL-Ausdrücke, Skripte oder dynamische Codeausführung ergänzen.

## P3 – Betriebsqualität und vollständiger Nachweis

1. E2E-, Berechtigungs-, Race-/PostgreSQL-, Upload-/Malware-, Last- und Wiederherstellungstests dort ergänzen, wo Risiko und reale Integrationsgrenzen es erfordern.
2. Datenschutz-/Aufbewahrung, externe Audit-Prüfpunkte, Monitoring/Incident-Prozess und Betreiberverantwortung konkret festlegen und nachweisen. PR #58 deckt nur vorgeschlagenes Worker-/Outbox-Monitoring ab; es ist ein Draft mit grüner CI, kein integriertes oder produktiv betriebenes Monitoring.
3. Fachbereiche wie Kundenportal, Mitarbeiterportal, globale Suche, Inventar, Leitstelle und Rechnungswesen anhand ihrer tatsächlichen Nutzerrollen und Datenbereichsgrenzen abnehmen. Grüne CI oder ein geschlossener GitHub-Vorgang ersetzt keine unabhängige fachliche, rechtliche, steuerliche oder produktive Prüfung.

## GitHub-Lage am Prüftag

- PRs #40, #42, #43, #44, #46, #47, #49 und #50 sind gemergt und ihre Änderungen sind in `main` enthalten; für diese PRs waren die angezeigten CI-Prüfungen erfolgreich. #50 war auf #47 gestapelt und brachte die letzte Inventarmigration `0030_inventory_management` ein.
- Offen sind PR #54 auf `main`, darauf gestapelt PR #55 und darauf gestapelt PR #57. PR #58 ist ein offener Draft auf `main`. Für #54, #55, #57 und #58 waren jeweils alle acht angezeigten CI-Checks erfolgreich; diese Ergebnisse gelten für die PR-Heads und sind keine Main- oder Betriebsnachweise. Issues #7, #9, #51, #52 und #56 sind offen. Die Vorschläge zu #56 und #9 sind nicht in `main`; insbesondere belegt #57 weder produktive Dateiverschlüsselung noch Schlüsselrotation und #58 keine produktive Überwachung. Issue #10 wurde geschlossen; Issues #45 und #48 sind nach Integration der Audit-/Rollen- beziehungsweise Inventarfunktionen geschlossen.
- CI, fachliche Abnahme und produktive Prüfung sind unterschiedliche Nachweise. Insbesondere belegen Merge und CI weder Betreiber-Restore noch Produktionsfreigabe oder Rechts-/Steuerkonformität.

## Abhängigkeiten und Abschlusskriterien

- Kunden → Objekte → Personal/Qualifikationen → Dienstplanung → Zeiterfassung/OWKS → Dokumente/Verträge → Abrechnung bleibt die fachliche Datenabhängigkeit.
- Jede Datenbankerweiterung erhält eine Alembic-Migration und passende Schema-, API-, Rechte-, UI- und Integrationstests. Bestehende Geschäfts- und Auditdaten nicht stillschweigend überschreiben; Korrekturen müssen nachvollziehbar sein.
- Geldwerte verwenden bestätigte Rechenregeln und `Decimal`/`NUMERIC`; Zeitpunkte werden UTC gespeichert. Lokale Dienstzeiten benötigen IANA-Zeitzonen und geprüfte DST-Fälle.
- „Implementiert“, „CI-grün“, „fachlich abgenommen“ und „produktiv geprüft/freigegeben“ sind getrennte Zustände. Keine Produktionsreife oder Rechts-/Steuerkonformität ohne konkreten und unabhängig geprüften Nachweis behaupten.
