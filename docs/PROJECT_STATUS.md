# SecurityOps – Projektstatus

**Historische Live-Prüfung:** 09.11.2026, 19:40 Uhr CET · Checkout und `origin/main` stimmten bei dieser Prüfung überein · **Alembic-Head:** `0035_worker_monitoring` · **Alembic-Migrationen:** 35 · **Offene Pull Requests zu diesem Zeitpunkt:** #62, #64, #65, #66, #68–#77.

**Aktueller Main-/GitHub-Abgleich:** 10.11.2026 · **Alembic-Head:** `0039_unique_billing_corrections` · **Alembic-Migrationen:** 39 · PR #85 ist in `main` integriert. PR #88 wird nach dem Merge seines Basis-PRs auf `main` neu gestapelt; PR #89 bleibt auf dem bisherigen #88-Head. Die detaillierte GitHub-Statusaufnahme weiter unten bleibt eine ausdrücklich datierte historische Momentaufnahme.

**Vorgeschlagener Stand von PR #88:** **Alembic-Head:** `0040_key_issue_automation` · Vorgängerrevision `0039_unique_billing_corrections`. Issue #51 bleibt offen, bis der Gesamtumfang fachlich abgeglichen ist.

**Historische GitHub-Nachprüfung:** 09.11.2026, 20:53 Uhr CET · zu diesem Zeitpunkt keine offenen Pull Requests · offene Issues: #7, #9, #51 und #56. Issue #63 war geschlossen. Der Repository-Owner meldete dort am 09.11.2026 die Aktivierung von Dependabot alerts und automated security fixes und deren Verifikation über die REST API. Das in jener Sitzung verfügbare Konto hatte keine Admin-Rechte; seine REST-Abfragen konnten die Einstellungen nicht unabhängig bestätigen. In jener Sitzung wurden keine Repository-Sicherheitseinstellungen geändert.

Diese Momentaufnahme wurde mit dem `main`-Quellcode und einer Live-Abfrage von GitHub abgeglichen. Die Momentaufnahme enthält absichtlich keinen Commit-SHA, der nach dem nächsten Merge veraltet wäre. Implementierung, erfolgreiche CI, fachliche Abnahme und produktiver Betrieb sind getrennte Nachweise. Ein Merge oder grüner CI-Lauf belegt für sich weder fachliche, rechtliche oder steuerliche Abnahme noch einen produktiven Rollout. Der CI-Validator prüft lokale Projektfakten; er fragt GitHub nicht ab. GitHub-Statusangaben müssen bei einer Aktualisierung erneut live geprüft werden.

Die mit PR #77 eingeführten Objektqualifikationsanforderungen und digitalen Dienstanweisungen sind durch die Revisionen `0037_object_qual_requirements` und `0038_digital_policies` in `main` enthalten.

## Tatsächlich in `main`

`backend/app/main.py` registriert Fach- und Portalrouter für Personal, Mitarbeiterportal, Dienstplanung, Zeiterfassung/Zuschläge, Aufgaben, Automatisierungen, Benachrichtigungen, Worker-Monitoring, Schlüssel, Inventar, Dokumente/Verträge, Rechnungswesen, Dienstanweisungen/Unterweisungen, Identität, Vorfälle, OWKS, Leitstelle, Kundenportal und globale Suche. Das vollständige Routerinventar aus der Registrierung in `backend/app/main.py` lautet: **Registrierte API-Router:** `api, automations_api, billing_api, control_room_api, customer_portal_api, documents_contracts_api, employee_portal_api, identity_api, incidents_api, inventory_api, key_management_api, notification_monitoring, notifications_api, owks_api, personnel_api, policies_api, scheduling_api, search_api, tasks_api, time_tracking_api, time_tracking_surcharges`. Die lineare Alembic-Kette hat 38 Revisionen, von `0001_customers` bis zum einzigen Head `0038_digital_policies`. Revision `0037_object_qual_requirements` ergänzt normalisierte Qualifikationsanforderungen je Objekt; `0038_digital_policies` ergänzt Versionen, Zuweisungen und Lese-/Bestätigungsnachweise für Dienstanweisungen und Unterweisungen. Für diese Aktualisierung wurden keine aggregierten Tabellen-/API-Zahlen neu aufgenommen.

- **Identität und Berechtigungen:** Anmeldung, Rollen/Rechte, serverseitig widerrufbare Sitzungen, optionales TOTP-MFA, Recovery-Codes, administrative Passwortzurücksetzung und Audit-Lesezugriff. Ein nutzerinitiierter E-Mail-Passwortreset und Mailzustellung sind nicht implementiert.
- **Kunden, Objekte und Personal:** Kunden- und Objektverwaltung, objektbezogene Zugriffsgrenzen, Personalakten, Qualifikationen, Abwesenheiten und nachvollziehbare Zuweisungsverläufe. Personal-Objektzuweisungen berücksichtigen serverseitig den Objektzugriff.
- **Dienstplanung und Zeiterfassung:** Schichten, Verfügbarkeiten, Anträge und Vertretungen mit serverseitigen Konfliktprüfungen, konfigurierbarer IANA-Zeitzone/Mindestruhezeit und Datenbankabsicherung gegen Überschneidungen. Zeitnachweise, Korrekturen, Freigaben, Zuschlagszeit-Regeln und Periodensperren sind vorhanden. Diese Konfigurationen belegen keine arbeitsrechtliche Konformität; Zuschlags-Geldbeträge werden nicht berechnet.
- **OWKS, Vorfälle und Schlüssel:** Wachbuch, Kontrollgänge und Anhänge; objektgebundene Vorfälle/Beschwerden mit getrennten Rechten für sensible Inhalte; physische Schlüssel mit protokolliertem Bewegungsverlauf. Statische QR-/NFC-Kennungen belegen keine physische Anwesenheit. Neue relevante Uploads werden fail-closed mit ClamAV geprüft; vorhandene Dateien werden nicht rückwirkend geprüft.
- **Aufgaben und Automatisierungen:** Der generische Aufgaben-Kern und die Outbox sind mit PR #54 um beschränkte Regeln erweitert: registrierte Task-Auslöser (`task.assigned`, `task.status_changed`), validierte Statusbedingung, In-App-Benachrichtigung, Admin-Verwaltung, Ausführungshistorie und kontrollierte Dead-Letter-Wiederholung. PR #59 registriert zusätzlich `owks.missed_control`, `owks.deviation_reported` und `owks.offline_event_synced`; `billing.invoice_approved` ist ebenfalls auf `main` registriert. Dieser Arbeitsbranch ergänzt als PR-Kandidat `key.issued` aus der bestätigten, append-only Schlüsselbewegung. Empfänger benötigen aktive Konten, eine aktuelle Objektzuweisung sowie `keys.read` und `notifications.read_own`; Nachricht und Payload enthalten keine Schlüssel- oder Personendaten. Eine Rückgabefrist gibt es im Modell nicht, daher bleibt eine Überfälligkeits-/Rückgabeautomatik nicht verfügbar. Beliebige Skripte und frei definierbare Aktionen sind nicht enthalten. Issue #51 bleibt offen, bis der Gesamtumfang fachlich abgeglichen ist; E-Mail/Push und Task-Erinnerungen/Eskalationen sind nicht enthalten.
- **Worker und Monitoring:** Der separate Notification-/OWKS-Worker verarbeitet Outbox-Ereignisse mit Claims, Lease/Wiederaufnahme, Retry und Dead-Letter-Historie. PR #58 ergänzt einen datensparsamen PostgreSQL-Heartbeat, Worker-Healthcheck und berechtigten Monitoring-Endpunkt für Outbox-/Dead-Letter-Zähler und verwaiste Claims; die Antwort gibt keine Payloads/Empfänger/Ereignis-IDs/Fehlertexte aus. Das ist implementierter Code in `main`, aber kein Nachweis eingerichteter externer Alarmierung oder eines überwachten Produktivbetriebs.
- **Leitstelle:** Berechtigungsgefilterte Momentaufnahme für erreichbare Objekte; operative Aktionen umfassen die serverseitige Suche und erneute Prüfung von Vertretungskandidaten beim Speichern. Die Ansicht ist kein Echtzeit- oder Alarmierungsdienst.
- **Kundenportal:** Separat verknüpfte Kundenkontakte können freigegebene Rechnungs-/Dokumentinformationen sowie Vorgänge mit Nachrichten und Anhängen nutzen. Dokumentfreigaben und Zugriffs-/Änderungsverläufe sind im Backend modelliert; kein generischer Zugriff auf interne Dokumente.
- **Mitarbeiterportal:** Eigene Schichten, Aufgaben, Benachrichtigungen, Qualifikationen, Zeitübersicht sowie Abwesenheits- und Verfügbarkeitsanträge. Nach PR #55 können eigene offene Abwesenheits-/Verfügbarkeitsanträge nachvollziehbar zurückgenommen und Qualifikationsdateien explizit für das aktive verknüpfte Mitarbeiterkonto freigegeben/widerrufen werden. Allgemeine Personal-/Vertragsdokumente bleiben ausgeschlossen; Issue #52 ist geschlossen.
- **Globale Suche:** Der registrierte Suchendpunkt berücksichtigt die jeweiligen Leserechte und Datenbereiche für Kunden, Objekte, Personal, Dokumente, Verträge, Schichten, Aufgaben, Vorfälle, Schlüssel, Inventar und OWKS-Ereignisse.
- **Inventar:** Inventargegenstände mit objekt-/personalbezogener Bereichsprüfung, Berechtigungen für Lesen/Verwalten/Bewegungen sowie Ereignishistorie für Ausgabe, Rückgabe, Übergabe, Verlust, Beschädigung, Wartung und weitere Statusänderungen. Inventarereignisse sind in PostgreSQL append-only abgesichert.
- **Private Dateiverschlüsselung:** PR #57 ergänzt für den gemeinsamen privaten Dateispeicher versioniertes AES-256-GCM, authentifizierte Metadaten und einen extern konfigurierten Schlüsselring. Produktionsstart schlägt bei fehlendem/ungültigem aktivem Schlüssel fehl; Legacy-Klartext wird in Produktion bis zu einer expliziten Migration nicht ausgeliefert. Der wiederaufnehmbare `scripts.rekey_document_storage`-Befehl unterstützt Dry-Run, Integritätsprüfung und atomare Rotation. Migration `0033_encrypted_document_storage` ändert bestehende Inhalte nicht selbst. Die Implementierung ist in `main`; Issue #56 bleibt offen für Betreiber-Schlüsselbereitstellung, explizite Bestandsmigration/Rotation und Abnahme. Es ist kein produktiver Rekey oder Deployment belegt.
- **Audit und Datenbankrollen:** Migration `0029_audit_integrity` ergänzt eine SHA-256-Hashkette, Append-only-Trigger für Audit-Einträge/Integritätsdaten und ein Prüfskript. Der Provisioner trennt Administrator-, Migrations- und Laufzeitrolle; `securityops_runtime` darf Audit-Einträge lesen/einfügen, aber nicht ändern/löschen, und erhält keinen Zugriff auf die Integritätstabelle. Datenbank-Owner/Superuser können weiterhin privilegierte Änderungen vornehmen; für externe Manipulationserkennung sind getrennt gespeicherte Prüfpunkte und unveränderliche Sicherungen nötig.

## Produktionskonfiguration und Grenzen

`docker-compose.yml` enthält PostgreSQL, Redis, ClamAV, API, Frontend, separaten Worker sowie profilgebundene Rollen-Provisionierung und Release-Migration. Das Frontend wird als statische Dateien durch Nginx ausgeliefert; API und Frontend sind am Host-Loopback gebunden. Die API erzwingt im Produktionsmodus Secure-Cookies, Redis für Rate-Limits und eine explizite Proxy-IP-Liste. TLS wird laut Deployment-Dokumentation durch einen separat zu konfigurierenden Reverse Proxy terminiert, nicht durch Compose selbst.

Backup-/Restore-Hilfen, PostgreSQL-Integrationsprüfungen und CI-Scans sind im Repository vorhanden. PR #58 hat Worker-Monitoring in `main` integriert, aber dies belegt weder externe Alarmierung noch einen produktiv überwachten Betrieb. Es gibt keinen Nachweis eines Betreiber-Rollouts, einer TLS-/DNS-/Proxy-Konfiguration in einer Zielumgebung oder einer regelmäßigen Wiederherstellung aus realen Betreiber-Sicherungen. Issue #9 bleibt deshalb offen. Die Dateiverschlüsselung und der Rekey-Befehl sind implementiert; Betreiber-Schlüsselbereitstellung, Migration vorhandener Dateien und Rotation in der Zielumgebung sowie Abnahme sind nicht nachgewiesen (Issue #56 bleibt offen). Für die konkrete Umgebung müssen unter anderem Secret-Verwaltung, Backupziel/Aufbewahrung, Restoreübungen, Monitoring/Alarmierung, Incident-Abläufe sowie Datenschutz- und Aufbewahrungsvorgaben eingerichtet und belegt werden. Eine Produktionsfreigabe wird nicht behauptet.

## GitHub-Status

Live am 09.11.2026 geprüft: PRs #54, #55, #57, #58 und #59 sind gemergt und Bestandteil von `main`. Die zuletzt relevanten integrierten Änderungen sind:

| PR | Live-Status | In `main` integrierter Umfang |
|---|---|---|
| [#40](https://github.com/Xonni-star/securityops-python/pull/40) | Gemergt | OWKS-/Vorfallintegration; Migration `0025_unique_incident_owks_event` |
| [#42](https://github.com/Xonni-star/securityops-python/pull/42) | Gemergt | Kundenportal; Migrationen `0026`–`0028` |
| [#43](https://github.com/Xonni-star/securityops-python/pull/43) | Gemergt | Mitarbeiter-Self-Service-Portal |
| [#44](https://github.com/Xonni-star/securityops-python/pull/44) | Gemergt | Operative Leitstellenfunktionen und Vertretungskandidatensuche |
| [#46](https://github.com/Xonni-star/securityops-python/pull/46) | Gemergt | Berechtigungsgefilterte globale Suche; aktueller `main`-Merge-Commit |
| [#47](https://github.com/Xonni-star/securityops-python/pull/47) | Gemergt | Audit-Integrität und getrennte Datenbankrollen; Migration `0029` |
| [#49](https://github.com/Xonni-star/securityops-python/pull/49) | Gemergt | Produktionskonfiguration und PostgreSQL-Integrationsprüfungen |
| [#50](https://github.com/Xonni-star/securityops-python/pull/50) | Gemergt, auf #47 gestapelt | Inventarverwaltung; Migration `0030`, in `main` über den Merge von #47 enthalten |
| [#54](https://github.com/Xonni-star/securityops-python/pull/54) | Gemergt | Beschränkte Automatisierungsregeln; Migration `0031_safe_automations` |
| [#55](https://github.com/Xonni-star/securityops-python/pull/55) | Gemergt | Antragsrücknahme und Freigabe von Qualifikationsdateien; Migration `0032_employee_portal` |
| [#57](https://github.com/Xonni-star/securityops-python/pull/57) | Gemergt | Verschlüsselter privater Dateispeicher und expliziter Rekey; Migration `0033_encrypted_document_storage` |
| [#59](https://github.com/Xonni-star/securityops-python/pull/59) | Gemergt | Eng begrenzte OWKS-Ereignisse als Automatisierungsauslöser; Migration `0034_owks_automation_events` |
| [#58](https://github.com/Xonni-star/securityops-python/pull/58) | Gemergt | Worker-Heartbeat und datensparsames Monitoring; Migration `0035_worker_monitoring` (Alembic-Head zum Integrationszeitpunkt) |

Die bei diesen Merge-PRs angezeigten CI-Prüfungen waren erfolgreich (Backend/PostgreSQL/Migrationen, Frontend, Container, Restore und Sicherheitsanalyse). CI-Erfolg ist kein fachlicher oder produktiver Nachweis.

### Offene Pull Requests

Bei der Live-Abfrage am 09.11.2026 um 19:40 CET waren PRs #62, #64, #65, #66, #68–#77 offen. PR #65 ist auf #64 gestapelt, PR #72 auf #65, PR #75 auf #62 und PR #77 auf #65. PR #62 steht auf `5f9c8e2`; CI-Lauf [42675534181](https://github.com/Xonni-star/securityops-python/actions/runs/42675534181) (Backend/PostgreSQL, Frontend, Docker, Restore) und Security-Lauf [42675534376](https://github.com/Xonni-star/securityops-python/actions/runs/42675534376) (SCA, Python- und JavaScript/TypeScript-CodeQL) sind vollständig erfolgreich. PR #72 steht auf `a5b1e5a`: Backend/Migration/PostgreSQL, Docker und Restore einschließlich Produktionscontainer-Prüfung waren erfolgreich; der CI-Rollup endete trotzdem mit Fehler und enthielt keinen Frontend-Job. SCA und Python-CodeQL waren erfolgreich, der Security-Rollup endete ebenfalls mit Fehler und enthielt keinen JavaScript/TypeScript-CodeQL-Job. Daher kein vollständig grüner CI-Nachweis. PR #73 steht auf `e9d9bb7`, bewahrt nach dem Diff den bisherigen Spaltenkatalog und ergänzt Schema-/Betriebsinformationen; alle gemeldeten Checks sind erfolgreich. PR #74 steht auf `224abf0`; die gemeldeten SCA-, CodeQL-, Docker-, Frontend- und Restore-Checks sind erfolgreich, jedoch fehlt ein aktueller Backend/PostgreSQL-Check. Ein manueller Lauf endete insgesamt mit Fehler und wies nur den Docker-Job als erfolgreich aus; der PostgreSQL-Testfix ist damit nicht bestätigt. PR #75 hat alle gemeldeten Checks erfolgreich. PR #76 besteht den vollständigen `workflow_dispatch`-CI-Lauf einschließlich Backend/PostgreSQL, Frontend, Docker und Restore; der PR-ausgelöste Security-Workflow bleibt unvollständig (kein Python-CodeQL-Job), daher ist PR #76 nicht vollständig grün. PR #77 steht auf `41c299b`; CI-Lauf [42675608126](https://github.com/Xonni-star/securityops-python/actions/runs/42675608126) und Security-Lauf [42675607994](https://github.com/Xonni-star/securityops-python/actions/runs/42675607994) sind vollständig erfolgreich: Backend/PostgreSQL, Frontend, Docker, Restore, SCA und beide CodeQL-Sprachen. Der vorherige Head `8e49be7` scheiterte in vier Migrationstests mit veralteter Erwartung `0037`; der neue Head bestätigt die Korrektur. PRs #64, #65, #66, #68–#71 hatten erfolgreiche Checks. Diese zeitgebundenen Ergebnisse belegen keine fachliche oder produktive Abnahme.

| PR | Status und Head zum Prüfzeitpunkt | Thema |
|---|---|---|
| [#62](https://github.com/Xonni-star/securityops-python/pull/62) | Offen · `5f9c8e2` · alle CI- und Security-Checks erfolgreich | Automate project status documentation checks |
| [#64](https://github.com/Xonni-star/securityops-python/pull/64) | Offen · `d94911c` · alle Checks erfolgreich | Add safe invoice-approval automation trigger |
| [#65](https://github.com/Xonni-star/securityops-python/pull/65) | Offen, auf #64 gestapelt · `11b503b` · alle Checks erfolgreich | Objektqualifikationen in der Dienstplanung prüfen |
| [#66](https://github.com/Xonni-star/securityops-python/pull/66) | Offen · `dc48048` · alle Checks erfolgreich | Add transactional backend workflow integration test |
| [#68](https://github.com/Xonni-star/securityops-python/pull/68) | Offen · `4aa43b3` · alle Checks erfolgreich | Dokumentiere GitHub Copilot Repository-Anweisungen |
| [#69](https://github.com/Xonni-star/securityops-python/pull/69) | Offen · `eacd9a1` · alle Checks erfolgreich | Test-only-Prüfung, dass Vorfallanhänge verschlüsselten Speicher verwenden |
| [#70](https://github.com/Xonni-star/securityops-python/pull/70) | Offen · `987b96a` · alle Checks erfolgreich | Dokumentiere Betrieb, Deployment und Wiederherstellung |
| [#71](https://github.com/Xonni-star/securityops-python/pull/71) | Offen · `6b39d7d` · alle Checks erfolgreich | Configure weekly Dependabot version updates |
| [#72](https://github.com/Xonni-star/securityops-python/pull/72) | Offen, auf #65 gestapelt · `a5b1e5a` · Backend/Migration/PostgreSQL, Docker und Restore erfolgreich; CI-Rollup fehlgeschlagen, Frontend fehlt; SCA/Python-CodeQL erfolgreich, Security-Rollup fehlgeschlagen, JS-CodeQL fehlt | Erklärbare Vorschläge für Dienstvertretungen |
| [#73](https://github.com/Xonni-star/securityops-python/pull/73) | Offen · `e9d9bb7` · alle gemeldeten Checks erfolgreich; vorheriger Spaltenkatalog bleibt erhalten und wird ergänzt | Aktualisiere Datenbankdokumentation auf Main-Schema |
| [#74](https://github.com/Xonni-star/securityops-python/pull/74) | Offen · `224abf0` · gelistete Checks erfolgreich, Backend/PostgreSQL-Check fehlt; Testfix daher nicht bestätigt | Ergänzt sicheren objektbezogenen Betriebsbericht |
| [#75](https://github.com/Xonni-star/securityops-python/pull/75) | Offen, auf #62 gestapelt · `4b0b305` · alle gemeldeten Checks erfolgreich | Add synthetic browser E2E for login and object access |
| [#76](https://github.com/Xonni-star/securityops-python/pull/76) | Offen · `7422e1f` · `workflow_dispatch`-CI vollständig erfolgreich; PR-Security-Workflow unvollständig, Python-CodeQL fehlt | MFA-Schlüssel an API-Container weitergeben |
| [#77](https://github.com/Xonni-star/securityops-python/pull/77) | Offen, auf #65 gestapelt · `41c299b` · alle Checks erfolgreich | Versionierte digitale Dienstanweisungen und Unterweisungsnachweise |

PR #76 enthält den zuvor separat gemeldeten MFA-Compose-Key-Forwarding-Commit; er ist offen und nicht Bestandteil von `main`. Für das Repository wurden bei der Live-Abfrage keine Deployments zurückgegeben.

### Issues

| Issue | Live-Status | Einordnung |
|---|---|---|
| [#7](https://github.com/Xonni-star/securityops-python/issues/7) | Offen | Rechnungswesen ist implementiert; Tarif-, Rundungs-, Steuer- und Buchhaltungsregeln benötigen fachliche Entscheidungen und Abnahme. |
| [#9](https://github.com/Xonni-star/securityops-python/issues/9) | Offen | Externe Zielumgebung, DNS/TLS/Secrets, reale Betreiber-Backups/Restore und Betreiberabnahme sind nicht nachgewiesen. Worker-Monitoring ist implementiert, aber kein Produktivbetriebsnachweis. |
| [#10](https://github.com/Xonni-star/securityops-python/issues/10) | Geschlossen am 09.11.2026 | GitHub-Kommentar bestätigt die integrierten Planungs-/Vertretungsfunktionen und Issue-Akzeptanzkriterien. Das ist keine Aussage zur gesetzlichen Ruhezeitkonformität. |
| [#45](https://github.com/Xonni-star/securityops-python/issues/45) | Geschlossen am 09.11.2026 | Audit-/Datenbankrollenanforderungen wurden mit PR #47 integriert. |
| [#48](https://github.com/Xonni-star/securityops-python/issues/48) | Geschlossen am 09.11.2026 | Inventaranforderungen wurden mit PR #50 integriert. |
| [#51](https://github.com/Xonni-star/securityops-python/issues/51) | Offen | Beschränkte Task-/OWKS-Automatisierung und `billing.invoice_approved` sind in `main`; PR #88 ergänzt `key.issued` aus bestätigten Schlüsselbewegungen. Rückgabe/Überfälligkeit, Qualifikationsablauf und weitere Trigger bleiben offen; fachlicher Gesamtumfang nicht abgenommen. |
| [#52](https://github.com/Xonni-star/securityops-python/issues/52) | Geschlossen am 09.11.2026 | Antragsrücknahme und Freigabe von Qualifikationsdateien wurden mit PR #55 integriert. Allgemeine Personal-/Vertragsdokumente bleiben ausgeschlossen. |
| [#56](https://github.com/Xonni-star/securityops-python/issues/56) | Offen · Betreiber-Nachweise fehlen | Verschlüsselter Dateispeicher und expliziter Rekey-Befehl sind mit gemergtem PR #57 in `main` vorhanden. Die Issue-Beschreibung ist hinsichtlich „nicht anwendungsseitig verschlüsselt“ und „Rekey fehlt“ teilweise überholt. Die test-only-Abdeckung für Vorfallanhänge liegt in offenem PR #69 und ist noch nicht Teil von `main`. Nicht belegt sind Betreiber-Schlüsselbereitstellung, Rekey/Migration bestehender Dateien in einer Zielumgebung und deren Abnahme; das Issue bleibt dafür offen. |
| [#63](https://github.com/Xonni-star/securityops-python/issues/63) | Geschlossen am 09.11.2026 | Der Repository-Owner meldete die Aktivierung von Dependabot alerts und automated security fixes sowie deren Verifikation über die GitHub REST API. Das in dieser Sitzung verfügbare Konto hat keine Admin-Rechte und konnte den Einstellungsstatus nicht unabhängig abrufen; es wurden keine Einstellungen geändert. |

Die Issues #2–#6 und #8 sind ebenfalls geschlossen. Geschlossene Issues und gemergte PRs werden nicht als offene Arbeit oder als außerhalb von `main` dargestellt. Offene Issues beschreiben verbleibende fachliche beziehungsweise betriebliche Arbeit, nicht zwingend fehlende Grundfunktionen.

## CI, Abnahme und produktiver Nachweis

Der Code enthält Backend- und Frontendtests sowie CI für Lint/Format, PostgreSQL-Migrationen und -Integration, Frontend-Build/-Tests, Container, Sicherheitsanalyse und einen isolierten Backup-/Restorelauf. Die letzten auf `main` gefundenen CI- und Security-Analysis-Läufe waren beim Live-Abgleich erfolgreich. Die individuellen offenen PR-Checks sind oben zeitgebunden aufgeführt. Laufstatus ist kein Nachweis fachlicher Abnahme, Betreiber-Schlüsselkonfiguration, produktiver Rekey-Ausführung oder eines Produktivbetriebs. Für das Repository wurden bei dieser Prüfung keine Deployments zurückgegeben. Diese Projektstatusdatei nennt bewusst keine aggregierten Testzahlen.

**Technische Voraussetzungen laut Projekt/CI:** Backend Python `>=3.12` (CI: 3.12); PostgreSQL 17 (CI); Frontend Node.js 22 (CI).

**Verfügbare CI-Prüfbefehle:** Backend `python -m pytest -q`, `ruff check app tests migrations scripts` und `ruff format --check app tests migrations scripts`; Frontend `npm run build` und `npm test`. Der Dokumentationsvalidator läuft im Backend-Job mit `python -m scripts.validate_project_status`.

### Branch-Schutz für `main`

Der Branch-Schutz wurde in dieser Arbeit nicht eingerichtet. Das GitHub-Konto meldete `permissions.admin=false`; die Abfrage der Branch-Protection-API lieferte HTTP 404. Damit ist der tatsächliche Regelstatus über dieses Konto nicht bestätigt. Ein Maintainer muss die Regeln in GitHub unter **Settings → Rules → Rulesets** oder **Settings → Branches** für `main` manuell einrichten und danach überprüfen:

1. Änderungen an `main` nur über Pull Requests zulassen.
2. Als erforderliche Checks alle im Pull Request erscheinenden Jobs der Workflows **CI** (Backend/Migrationen/PostgreSQL, Backup/Restore, Frontend, Container-Build) und **Security analysis** (Abhängigkeitsprüfung sowie beide CodeQL-Sprachen) auswählen.
3. Direkte Pushes und Force-Pushes auf `main` sowie das Löschen des Branches verhindern.
4. Bypass-Rechte auf ausdrücklich benannte Maintainer begrenzen; keine allgemeine Bypass-Ausnahme für Administratoren oder andere Rollen belassen.

Der Validator prüft die genannten lokalen Projektfakten und Dokumentationsangaben, aber weder GitHub-PR-/Issue-Status noch Branch-Schutz. Dafür ist eine erneute Live-Prüfung durch einen berechtigten Maintainer erforderlich.

### Lizenz

Für das Repository ist keine Lizenz ausgewählt oder hinterlegt (GitHub-Metadatum `license: null`, keine `LICENSE`-Datei). Eine Auswahl wird hier nicht vorgenommen; sie erfordert eine Entscheidung des Rechteinhabers. Die neutralen Optionen und ihre groben Auswirkungen sind in [Lizenzstatus und offene Entscheidung](LICENSING.md) zusammengefasst.

| Nachweisart | Status |
|---|---|
| Implementiert | Die oben aufgeführten Funktionen und Migrationen sind im geprüften `main`-Quellcode vorhanden. |
| CI | Die Checks der genannten Merge-PRs waren laut Live-Abfrage erfolgreich. Das gilt jeweils für die geprüften PR-Heads. |
| Fachlich abgenommen | Issue #10 wurde nach dokumentiertem Abgleich der Issue-Akzeptanzkriterien geschlossen; Issue #52 nach Merge von PR #55. Eine externe rechtliche, steuerliche oder arbeitsrechtliche Abnahme ist damit nicht belegt; Issues #7, #9, #51 und #56 bleiben offen. Issue #63 ist eine abgeschlossene Repository-Administration-Aufgabe. |
| Produktiv geprüft | Kein produktiver Rollout, Betreiber-Restore oder Rekey ist belegt; Issue #9 bleibt offen. |

## Verweise

- [Architektur](ARCHITECTURE.md) · [Datenbank/Migrationen](DATABASE.md) · [API](API.md)
- [Sicherheit](SECURITY.md) · [Deployment](DEPLOYMENT.md) · [Backup/Restore](BACKUP_RESTORE.md)
- [Audit](PROJECT_AUDIT.md) · [Sicherheitsprüfung](SECURITY_REVIEW.md) · [Roadmap](IMPLEMENTATION_ROADMAP.md) · [Lizenzstatus](LICENSING.md)
