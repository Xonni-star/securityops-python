# SecurityOps – Sicherheitsprüfung

Diese Prüfung fasst die bisherigen Reviews für `main` nach PR #16 und den aktuellen Feature-Branch `feature/personnel-management` zusammen. Sie ist kein Penetrationstest und keine Produktionsfreigabe. Es wurden keine echten Betriebsdaten verwendet.

## Zusammenfassung

| Kennung | Schweregrad | Status | Befund |
|---|---|---|---|
| SEC-01 | Mittel | Offen | Login-Rate-Limit liegt pro Prozess im Arbeitsspeicher; Neustarts und mehrere Instanzen schwächen die Begrenzung. |
| SEC-02 | Mittel | Offen | Compose startet Vite im Entwicklungsmodus; produktiver Webserver, TLS-Reverse-Proxy und Security-Header sind nicht Bestandteil des Deployments. |
| SEC-03 | Mittel | Teilweise behoben (Issue #45) | Getrennte Datenbankrollen, Append-only-Trigger und eine SHA-256-Kette schützen vor Änderungen durch die Laufzeitrolle und machen Änderungen innerhalb der Datenbank prüfbar. Datenbank-Owner/Superuser können Schutzmechanismen umgehen; getrennte externe Sicherungen und Prüfpunktaufbewahrung bleiben Betreiberaufgaben. |
| SEC-04 | Mittel | Offen | Anmeldung ohne MFA und Passwortzurücksetzungsprozess; keine aktive Sitzungsübersicht oder gezielte Einzelwiderruf-UI. |
| SEC-05 | Niedrig | Offen | Es gibt noch keine automatisierte Abhängigkeits- oder statische Sicherheitsanalyse in CI; als nächste Härtungsmaßnahme in [#9](https://github.com/Xonni-star/securityops-python/issues/9) nachzuverfolgen. |
| SEC-06 | Niedrig | Offen | API setzt keine expliziten allgemeinen Browser-Sicherheitsheader; dies muss derzeit ein vorgeschalteter Webserver übernehmen. |
| SEC-07 | Mittel | In `main` behoben | Die Anwendung verlangt `POSTGRES_PASSWORD`; Tests setzen ausschließlich einen Testwert. |
| SEC-08 | Hoch | In `main` behoben | Administratorrollenvergabe/-änderung ist serverseitig zusätzlich an `users.manage_admin` gebunden und durch Regressionstest abgedeckt. |
| SEC-09 | Hoch | In `main` behoben, PR #16 CI erfolgreich | Objektendpunkte erzwangen zuvor keine Zuweisung und erlaubten mit Modulrechten Zugriff auf fremde Objekte. Lesen, Ändern, Archivieren, Kontakte, Historie, Zuweisungen und sensible Details prüfen jetzt den Objekt-Scope serverseitig. |
| SEC-10 | Hoch | In `main` behoben, PR #16 CI erfolgreich | Allgemeine Objektantworten enthielten zuvor Sicherheits-/Zutrittsdaten. Diese Angaben liegen nun getrennt und benötigen eigene Les-/Schreibberechtigungen; Negativtests prüfen Antworttrennung und Scope. |
| SEC-11 | Mittel | Im Personal-Feature-Branch umgesetzt, CI erfolgreich | Sensible Personalangaben und Abwesenheiten sind aus allgemeinen Personalantworten getrennt und durch eigene Rechte geschützt. Lokale Negativtests sowie PostgreSQL-Migrationen und -Tests in PR #17 CI bestätigen die Änderungen; weiterer Review bleibt offen. |
| SEC-12 | Mittel | Im Personal-Feature-Branch umgesetzt; neue Änderungen benötigen erneute CI | Qualifikationsdateien haben separate Lese-/Schreibrechte, Größen-/Format-/Signaturprüfung und unveränderliche Versionen. Inhalte liegen als `BYTEA` in PostgreSQL; Anwendungsebene-Verschlüsselung und unabhängige private Objektspeicherung fehlen, daher müssen Datenbank- und Backupzugriffe entsprechend geschützt werden. |

## Geprüfte Schutzmaßnahmen

- Passwortspeicherung mit Argon2id; Login-Fehler sind für unbekannte und falsche Konten gleich.
- Sitzungen verwenden zufällige opaque Tokens; gespeichert werden Token-Hashes. Sitzungen haben Idle- und absolute Laufzeit, Logout und Passwortwechsel widerrufen Sitzungen.
- Authentifizierte schreibende Requests prüfen CSRF-Cookie, Request-Header und gespeicherten Hash.
- Cookies sind HttpOnly (Sitzung), SameSite=Strict und Secure per Konfiguration; Compose fällt auf Secure=true zurück. Lokale HTTP-Entwicklung setzt es in `.env.example` ausdrücklich auf false.
- RBAC wird serverseitig an Kunden-, Benutzer-, Rollen-, Audit- und Dashboardrouten geprüft.
- Objektzugriff wird zusätzlich zum Modulrecht global oder anhand einer Benutzerzuweisung autorisiert. Sensible Sicherheits- und Zutrittsdaten haben separate API-Routen und Berechtigungen.
- Zuweisungsendpunkte akzeptieren ausschließlich aktive Mitarbeiter- oder Objektleitungskonten; die Zuordnung selbst wird mit eindeutiger Datenbankbedingung geschützt.
- Objektänderungen werden transaktional mit Verlauf/Audit gespeichert. Historieneinträge listen geänderte Felder, nicht deren sensible Werte.
- Personalanschrift, Notfallkontakt und interne Notizen werden in einer eigenen Tabelle geführt; Personalhistorie und Audit protokollieren nur Feldnamen. Abwesenheiten haben ebenfalls eigene Lese-/Schreibrechte.
- Qualifikationsdateien werden nur über geschützte Dokument-Endpunkte bereitgestellt. Uploads sind auf PDF/PNG/JPEG und 10 MiB begrenzt; Dateiendung, Content-Type und Signatur werden geprüft. Die Dateiversionen sind unveränderlich und SHA-256-gekennzeichnet.
- Anwendungsebene-Verschlüsselung für Qualifikationsdateien ist derzeit bewusst nicht ergänzt: Im Repository gibt es weder einen verwalteten Schlüssel-/KMS-Bezug noch einen Ablauf für Schlüsselrotation und Wiederherstellung verschlüsselter Backups. Eine lokale Schlüsseldatei oder ein Umgebungsgeheimnis ohne Rotation und Restore-Verfahren würde nur eine unvollständige Schutzmaßnahme schaffen. Vor produktiver Ablage ist ein überprüfbares Schlüsselmanagement samt Rotation, Backup und Wiederherstellung festzulegen; bis dahin sind Datenbank-, Volume- und Backupverschlüsselung sowie streng beschränkter Administrationszugriff Voraussetzung.
- Qualifikationsmetadaten und Abwesenheiten sind über Fremdschlüssel mit `RESTRICT` an Personalakten gebunden; Archivierung erhält verbundene Datensätze, statt sie zu löschen.
- ORM-Abfragen verwenden gebundene Parameter; React escaped Textausgaben standardmäßig. Personal- und OWKS-Dateien werden ausschließlich über geschützte Backend-Endpunkte verarbeitet; externe private Dateiablage und Anwendungsebene-Verschlüsselung fehlen.
- CORS stammt aus einer expliziten Origin-Konfiguration und erlaubt keine beliebigen Origins.
- Compose verlangt ein gesetztes Datenbankpasswort; Anwendungskonfiguration enthält keinen Produktions-Standardwert.

## Offene Maßnahmen

1. Gemeinsamen Rate-Limit-Speicher (z. B. Redis) und vertrauenswürdige Proxy-IP-Konfiguration einführen; Login- und weitere sensible Endpunkte prüfen.
2. Produktionsfrontend als statische Assets ausliefern und TLS, HSTS, CSP sowie weitere passende Header am vertrauenswürdigen Reverse Proxy konfigurieren. Den Devserver nicht öffentlich bereitstellen.
3. Laufzeit-, Migrations- und Backup-Datenbankrollen nach minimalen Rechten trennen. Audit-Protokoll extern oder append-only sichern; direkte privilegierte Datenbankänderungen bleiben sonst außerhalb des App-Schutzes.
4. MFA, sicheren Passwort-Reset und Sitzungsanzeige/-widerruf mit Abuse- und Berechtigungstests umsetzen.
5. CI um verwaltete SCA-/SAST-Prüfungen ergänzen und deren Pflege/Alarmierungsweg festlegen.
6. Security-Header, TLS, Datenschutz-/Aufbewahrung und Incident-Abläufe für die konkrete Serverumgebung festlegen und prüfen.
7. Mitarbeiter-Objektzuweisungen nutzen die vorhandene Objektzuweisungstabelle; Zuweisung und Ende werden in der Personalhistorie erfasst, Archivierung und Beendigung des Arbeitsverhältnisses beenden aktive Zuweisungen. Die aktuellen Änderungen benötigen einen erneuten PostgreSQL-CI-Lauf und Review.

## Grenzen und Prüfbelege

- Die oben genannten Belege beziehen sich auf die jeweiligen früheren PR-Stände, nicht auf den aktuellen OWKS-Head. Für aktuelle Ergebnisse und OWKS-spezifische offene Punkte siehe die Prüfung unten.
- Frühere PostgreSQL-Migrationen/-Tests und Docker-Builds des Personal-Branches waren in CI erfolgreich, jedoch für einen älteren Commit. Ein externer Penetrationstest liegt nicht vor. Die CI für PR #16 war nach den Objektkorrekturen ebenfalls erfolgreich.
- Die Prüfung bewertet keinen konkreten Server, Reverse Proxy, Firewall, Secret Store, Backup-Speicher oder administrativen Datenbankzugang.
- Die Anwendung ist derzeit ein Entwicklungsstand. Vor öffentlichem oder produktivem Betrieb sind die offenen Punkte sowie Datenschutz-, Arbeitszeit- und Abrechnungsanforderungen fachlich und sicherheitstechnisch zu prüfen.

## OWKS-Prüfung für PR #23

Der Review hat die OWKS-Endpunkte, Objektzuweisung, Anhänge, Offline-Idempotenz, append-only Status-/Ereignisdaten, PostgreSQL-Monitor und Migration 0014 betrachtet. Diese Prüfung ist codebasiert und kein Penetrationstest.

| Kennung | Schweregrad | Status | Befund |
|---|---|---|---|
| OWKS-01 | Mittel | Abgemildert; kryptografischer Präsenznachweis offen | Statische QR-/NFC-Kennungen lassen sich kopieren. Treffer werden deshalb als `presence_verified=false` und mit offenem Status protokolliert und zählen nicht als erledigter Besuch. Server-Challenge und Replay-Prüfung beweisen weiterhin keine physische Anwesenheit; dynamische kryptografische Tags oder verifizierte Geräte-/Standortbeweise sind nicht integriert. |
| OWKS-02 | Mittel | Im aktuellen Branch abgesichert; PostgreSQL-CI erfolgreich | Migration 0014 verweigert Downgrade, sobald OWKS-Tabellen Daten enthalten. Der PostgreSQL-spezifische Regressionstest bestätigte im CI-Lauf 42520765482, dass der Downgrade fehlschlägt und der Kontrollpunkt erhalten bleibt. |

Der lokale PostgreSQL-Dienst und Docker sind in der aktuellen Entwicklungsumgebung nicht verfügbar; SQLite überspringt fünf PostgreSQL-spezifische Tests. Im GitHub-Actions-Lauf 42520765482 (Commit `01d7c17a21aa5c6353156d15428184527336c2eb`) wurden Migrationen live auf PostgreSQL 17 angewendet und alle 41 Backendtests bestanden. Frontend-Typprüfung und Produktionsbuild, 17 Vitest-Tests sowie beide Docker-Image-Builds waren ebenfalls erfolgreich. Der frühere Backend-Joblauf endete einmal mit einem Deadlock in einem bestehenden parallelen Dienstplan-Test; der fehlgeschlagene Job wurde erneut ausgeführt und bestand. Ein erfolgreicher CI-Lauf ist kein Penetrationstest und keine Produktionsfreigabe.
