# SecurityOps – Projektstatus

**Geprüft:** 09.11.2026 · **`main`:** `463ddba0fa1173d5c8a068362cd2f6af96018820` (Commit vom 09.11.2026, 12:47 Uhr +01:00) · **Alembic-Head:** `0030_inventory_management`

Diese Momentaufnahme wurde mit dem aktuellen `main`-Quellcode und der Live-Abfrage von GitHub abgeglichen. Implementierung, erfolgreiche CI, fachliche Abnahme und produktiver Betrieb sind getrennte Nachweise. Ein Merge oder grüner CI-Lauf belegt für sich weder fachliche, rechtliche oder steuerliche Abnahme noch einen produktiven Rollout.

## Tatsächlich in `main`

`backend/app/main.py` registriert neben dem Basisrouter die Fach- und Portalrouter für Personal, Mitarbeiterportal, Dienstplanung, Zeiterfassung/Zuschläge, Aufgaben, Benachrichtigungen, Schlüssel, Inventar, Dokumente/Verträge, Rechnungswesen, Identität, Vorfälle, OWKS, Leitstelle, Kundenportal und globale Suche. Für diesen Snapshot ergeben SQLAlchemy-Metadaten 84 modellierte Tabellen; das generierte OpenAPI-Schema enthält 198 API-Pfade mit 245 Operationen. In `backend/migrations/versions/` liegen 30 Migrationen von `0001_customers` bis `0030_inventory_management`; Alembic meldet genau einen Head, `0030_inventory_management`. Infrastruktur-/Alembic-Tabellen und nicht ORM-gemappte Migrationstabellen sind nicht in der SQLAlchemy-Zahl enthalten.

- **Identität und Berechtigungen:** Anmeldung, Rollen/Rechte, serverseitig widerrufbare Sitzungen, optionales TOTP-MFA, Recovery-Codes, administrative Passwortzurücksetzung und Audit-Lesezugriff. Ein nutzerinitiierter E-Mail-Passwortreset und Mailzustellung sind nicht implementiert.
- **Kunden, Objekte und Personal:** Kunden- und Objektverwaltung, objektbezogene Zugriffsgrenzen, Personalakten, Qualifikationen, Abwesenheiten und nachvollziehbare Zuweisungsverläufe. Personal-Objektzuweisungen berücksichtigen serverseitig den Objektzugriff.
- **Dienstplanung und Zeiterfassung:** Schichten, Verfügbarkeiten, Anträge und Vertretungen mit serverseitigen Konfliktprüfungen, konfigurierbarer IANA-Zeitzone/Mindestruhezeit und Datenbankabsicherung gegen Überschneidungen. Zeitnachweise, Korrekturen, Freigaben, Zuschlagszeit-Regeln und Periodensperren sind vorhanden. Diese Konfigurationen belegen keine arbeitsrechtliche Konformität; Zuschlags-Geldbeträge werden nicht berechnet.
- **OWKS, Vorfälle und Schlüssel:** Wachbuch, Kontrollgänge und Anhänge; objektgebundene Vorfälle/Beschwerden mit getrennten Rechten für sensible Inhalte; physische Schlüssel mit protokolliertem Bewegungsverlauf. Statische QR-/NFC-Kennungen belegen keine physische Anwesenheit. Neue relevante Uploads werden fail-closed mit ClamAV geprüft; vorhandene Dateien werden nicht rückwirkend geprüft.
- **Aufgaben und Worker:** Generischer Aufgaben-Kern mit In-App-Benachrichtigungen über eine transaktionale Outbox. Der separate Worker verarbeitet die Task-Ereignisse mit Claims, Lease/Wiederaufnahme, Retry und Dead-Letter-Historie und führt außerdem den OWKS-Prüfzyklus aus. Ein allgemeines, konfigurierbares Automatisierungsregelwerk ist nicht Bestandteil von `main`; PR #54 schlägt derzeit eine beschränkte Aufgabenregel-Verwaltung vor. E-Mail/Push und Task-Erinnerungen/Eskalationen sind nicht in `main` enthalten.
- **Leitstelle:** Berechtigungsgefilterte Momentaufnahme für erreichbare Objekte; operative Aktionen umfassen die serverseitige Suche und erneute Prüfung von Vertretungskandidaten beim Speichern. Die Ansicht ist kein Echtzeit- oder Alarmierungsdienst.
- **Kundenportal:** Separat verknüpfte Kundenkontakte können freigegebene Rechnungs-/Dokumentinformationen sowie Vorgänge mit Nachrichten und Anhängen nutzen. Dokumentfreigaben und Zugriffs-/Änderungsverläufe sind im Backend modelliert; kein generischer Zugriff auf interne Dokumente.
- **Mitarbeiterportal:** Eigene Schichten, Aufgaben, Benachrichtigungen, Qualifikationen, Zeitübersicht sowie Abwesenheits- und Verfügbarkeitsanträge. Eigene offene Anträge können bearbeitet werden. Rücknahme von Anträgen und ein explizites Freigabemodell für persönliche Mitarbeiterdokumente sind nicht Bestandteil von `main`; PR #55 schlägt diese Folgearbeit vor und baut auf PR #54 auf. Issue #52 bleibt offen.
- **Globale Suche:** Der registrierte Suchendpunkt berücksichtigt die jeweiligen Leserechte und Datenbereiche für Kunden, Objekte, Personal, Dokumente, Verträge, Schichten, Aufgaben, Vorfälle, Schlüssel, Inventar und OWKS-Ereignisse.
- **Inventar:** Inventargegenstände mit objekt-/personalbezogener Bereichsprüfung, Berechtigungen für Lesen/Verwalten/Bewegungen sowie Ereignishistorie für Ausgabe, Rückgabe, Übergabe, Verlust, Beschädigung, Wartung und weitere Statusänderungen. Inventarereignisse sind in PostgreSQL append-only abgesichert.
- **Audit und Datenbankrollen:** Migration `0029_audit_integrity` ergänzt eine SHA-256-Hashkette, Append-only-Trigger für Audit-Einträge/Integritätsdaten und ein Prüfskript. Der Provisioner trennt Administrator-, Migrations- und Laufzeitrolle; `securityops_runtime` darf Audit-Einträge lesen/einfügen, aber nicht ändern/löschen, und erhält keinen Zugriff auf die Integritätstabelle. Datenbank-Owner/Superuser können weiterhin privilegierte Änderungen vornehmen; für externe Manipulationserkennung sind getrennt gespeicherte Prüfpunkte und unveränderliche Sicherungen nötig.

## Produktionskonfiguration und Grenzen

`docker-compose.yml` enthält PostgreSQL, Redis, ClamAV, API, Frontend, separaten Worker sowie profilgebundene Rollen-Provisionierung und Release-Migration. Das Frontend wird als statische Dateien durch Nginx ausgeliefert; API und Frontend sind am Host-Loopback gebunden. Die API erzwingt im Produktionsmodus Secure-Cookies, Redis für Rate-Limits und eine explizite Proxy-IP-Liste. TLS wird laut Deployment-Dokumentation durch einen separat zu konfigurierenden Reverse Proxy terminiert, nicht durch Compose selbst.

Backup-/Restore-Hilfen, PostgreSQL-Integrationsprüfungen und CI-Scans sind im Repository vorhanden. Sie weisen keinen Rollout, keine TLS-/DNS-/Proxy-Konfiguration in einer Zielumgebung, keine produktive Überwachung/Alarmierung und keine regelmäßige Wiederherstellung aus einer realen Betreiber-Sicherung nach. Issue #9 bleibt deshalb offen. Der private Dateispeicher verwendet zufällige Speicher-IDs, Dateisystemrechte und autorisierte Downloads; die Datei-Nutzdaten sind dort derzeit nicht anwendungsseitig verschlüsselt, und Schlüsselrotation ist nicht vorhanden (offen in Issue #56). Für die konkrete Umgebung müssen unter anderem Secret-Verwaltung, Backupziel/Aufbewahrung, Restoreübungen, Monitoring, Incident-Abläufe sowie Datenschutz- und Aufbewahrungsvorgaben eingerichtet und belegt werden. Eine Produktionsfreigabe wird nicht behauptet.

## GitHub-Status

Live am 09.11.2026 geprüft: PR #54 und der darauf gestapelte PR #55 sind offen und nicht Bestandteil von `main`. Die zuletzt relevanten integrierten Änderungen sind:

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

Die bei diesen Merge-PRs angezeigten CI-Prüfungen waren erfolgreich (Backend/PostgreSQL/Migrationen, Frontend, Container, Restore und Sicherheitsanalyse). CI-Erfolg ist kein fachlicher oder produktiver Nachweis.

### Offene Pull Requests – Vorschläge, nicht Bestandteil von `main`

| PR | Status und Basis | Vorschlag / CI |
|---|---|---|
| [#54](https://github.com/Xonni-star/securityops-python/pull/54) | Offen, Basis `main` | Sichere Automatisierungsregeln für Aufgaben, Migration `0031`; beschränkt auf vorhandene Auslöser `task.assigned`/`task.status_changed`, validierte Aufgabenstatus-Bedingung und In-App-Benachrichtigung. Die acht angezeigten PR-CI-Checks sind erfolgreich. Ein Security-Review fand laut PR-Status keine Findings. |
| [#55](https://github.com/Xonni-star/securityops-python/pull/55) | Offen, Basis `macrave-dee-sichere-automatisierungen` (PR #54) | Mitarbeiterportal-Folgearbeit: Rücknahme eigener offener Abwesenheits-/Verfügbarkeitsanträge und ausdrückliche Freigabe von Qualifikationsdateien. Allgemeine Personal-/Vertragsdokumente und Stammdatenänderungsanträge sind laut PR-Beschreibung ausgeschlossen. Die acht angezeigten PR-CI-Checks sind erfolgreich. |

Beide PRs sind Vorschläge auf offenen Branches. Ihre Implementierung und grünen CI-Prüfungen ändern den `main`-Bestand nicht, solange kein Merge erfolgt. PR #55 ist gestapelt und setzt den in PR #54 vorgeschlagenen Branch voraus.

### Issues

| Issue | Live-Status | Einordnung |
|---|---|---|
| [#7](https://github.com/Xonni-star/securityops-python/issues/7) | Offen | Rechnungswesen ist implementiert; Tarif-, Rundungs-, Steuer- und Buchhaltungsregeln benötigen fachliche Entscheidungen und Abnahme. |
| [#9](https://github.com/Xonni-star/securityops-python/issues/9) | Offen | Betreiberabnahme, Zielumgebung und realer Datenbank-/Datei-Restore sind nicht nachgewiesen. |
| [#10](https://github.com/Xonni-star/securityops-python/issues/10) | Geschlossen am 09.11.2026 | GitHub-Kommentar bestätigt die integrierten Planungs-/Vertretungsfunktionen und Issue-Akzeptanzkriterien. Das ist keine Aussage zur gesetzlichen Ruhezeitkonformität. |
| [#45](https://github.com/Xonni-star/securityops-python/issues/45) | Geschlossen am 09.11.2026 | Audit-/Datenbankrollenanforderungen wurden mit PR #47 integriert. |
| [#48](https://github.com/Xonni-star/securityops-python/issues/48) | Geschlossen am 09.11.2026 | Inventaranforderungen wurden mit PR #50 integriert. |
| [#51](https://github.com/Xonni-star/securityops-python/issues/51) | Offen | PR #54 schlägt einen begrenzten Aufgabenregel-Umfang vor; Issue bleibt offen, bis die Implementierung integriert und der Gesamtumfang abgeglichen ist. |
| [#52](https://github.com/Xonni-star/securityops-python/issues/52) | Offen | PR #55 schlägt Antragsrücknahme und Freigabe von Qualifikationsdateien vor; die Folgearbeit ist offen und nicht Bestandteil von `main`. |
| [#56](https://github.com/Xonni-star/securityops-python/issues/56) | Offen · sehr hohe Priorität | Private Dateinutzdaten sind nicht anwendungsseitig verschlüsselt; Verschlüsselung des gemeinsamen Speichers, explizite Bestandsmigration und Schlüsselrotation sind offen. Die Umsetzung läuft separat gestapelt auf dem Mitarbeiterportal-Branch und ist nicht Bestandteil von `main` oder PR #53. |

Die Issues #2–#6 und #8 sind ebenfalls geschlossen. Geschlossene Issues und gemergte PRs werden nicht als offene Arbeit oder als außerhalb von `main` dargestellt. Offene Issues beschreiben verbleibende fachliche beziehungsweise betriebliche Arbeit, nicht zwingend fehlende Grundfunktionen.

## CI, Abnahme und produktiver Nachweis

Der Code enthält Backend- und Frontendtests sowie CI für Lint/Format, PostgreSQL-Migrationen und -Integration, Frontend-Build/-Tests, Container, Sicherheitsanalyse und einen isolierten Backup-/Restorelauf. Für die offenen Vorschläge #54 und #55 waren die jeweils angezeigten acht PR-CI-Checks erfolgreich; PR #54 hat laut Review-Status keine Findings. Dies sind Nachweise für die jeweiligen PR-Heads, nicht für `main` oder eine fachliche/produktive Abnahme. Diese Projektstatusdatei nennt bewusst keine aggregierten Testzahlen; sie wurden für diesen Snapshot nicht neu erhoben.

| Nachweisart | Status |
|---|---|
| Implementiert | Die oben aufgeführten Funktionen und Migrationen sind im geprüften `main`-Quellcode vorhanden. |
| CI | Die Checks der genannten Merge-PRs waren laut Live-Abfrage erfolgreich. Das gilt jeweils für die geprüften PR-Heads. |
| Fachlich abgenommen | Issue #10 wurde nach dokumentiertem Abgleich der Issue-Akzeptanzkriterien geschlossen. Eine externe rechtliche, steuerliche oder arbeitsrechtliche Abnahme ist damit nicht belegt; Issues #7 und #9 bleiben offen. |
| Produktiv geprüft | Kein produktiver Rollout oder Betreiber-Restore ist belegt; Issue #9 bleibt offen. |

## Verweise

- [Architektur](ARCHITECTURE.md) · [Datenbank/Migrationen](DATABASE.md) · [API](API.md)
- [Sicherheit](SECURITY.md) · [Deployment](DEPLOYMENT.md) · [Backup/Restore](BACKUP_RESTORE.md)
- [Audit](PROJECT_AUDIT.md) · [Sicherheitsprüfung](SECURITY_REVIEW.md) · [Roadmap](IMPLEMENTATION_ROADMAP.md)
