# Sicherheitsstatus und Betriebshinweise

## Bereits vorhanden

- Argon2id-Passwort-Hashes und generische Login-Fehler.
- Serverseitige opaque Sitzungen mit gleitender und absoluter Ablaufzeit.
- HttpOnly, SameSite=Strict Sitzungscookie; CSRF-Tokenprüfung für authentifizierte Schreibzugriffe.
- Serverseitiges TOTP-MFA mit verschlüsseltem Geheimnis, bestätigter Einrichtung, Replay-Schutz und gehashten Einmal-Wiederherstellungscodes.
- Eigene aktive Sitzungen können eingesehen und einzeln widerrufen werden; `sessions.manage` erlaubt autorisierte Übersicht und Widerruf fremder Sitzungen. Aktionen werden auditiert.
- Passwortwechsel und auditierter Admin-Reset widerrufen bestehende Sitzungen; ein Admin-Reset erzwingt die Passwortänderung beim nächsten Login und gibt keine Tokens oder Codes zurück.
- Server-RBAC, Schutz vor Zuweisung fremder Berechtigungen und Administratorrollen sowie explizite Rechte für Sitzungsverwaltung und Passwort-Reset.
- Globales Rate-Limit und strengere Anmelde-/MFA-/Passwortlimits; Produktion verwendet Redis als gemeinsamen Speicher, die API-Readiness prüft dessen Verfügbarkeit. Lokale direkte Starts ohne Redis nutzen den In-Memory-Store.
- Keine Passworthashes in API-Antworten.
- Audit-Einträge für implementierte Anmelde-, Benutzer-, Kunden- und Objektänderungen.
- PostgreSQL trennt Administrator, Migrations- und Laufzeitrolle. Die Laufzeitrolle kann `audit_logs` lesen/einfügen, aber nicht verändern oder löschen; Trigger schützen die Audit- und Integritätstabellen auch vor versehentlichen Owner-Änderungen.
- Audit-Einträge sind per SHA-256 verkettet; eine Sperre serialisiert parallele Einfügungen. Die Integritätsprüfung erkennt fehlende, abgetrennte und veränderte Einträge innerhalb der Datenbank.
- Objektzugriff serverseitig nach globalen Rechten oder Objektzuweisung; Sicherheits- und Zutrittsdaten sind getrennt und zusätzlich berechtigt.
- OWKS-Endpunkte prüfen das OWKS-Recht und zusätzlich den Objekt-Scope; Anhangabruf ist nicht öffentlich und der Upload validiert Dateiendung, MIME-Typ, Signatur und 10-MiB-Grenze.
- OWKS-Ereignisse, Statusverläufe und Anhänge sind in PostgreSQL append-only. Statusänderungen und Korrekturen werden als neue Datensätze protokolliert.
- Kontrollscans benötigen eine kurzlebige, benutzer- und objektgebundene Einmal-Challenge; PostgreSQL koordiniert den Versäumnis-Monitor zwischen Instanzen und verhindert doppelte generierte Meldungen.
- Statische QR-/NFC-Kennungstreffer werden als `presence_verified=false` protokolliert, bleiben offen und zählen nicht als erledigter Besuch. Sie belegen keine physische Anwesenheit.
- Datenbankpasswörter sind als getrennte Umgebungsvariablen erforderlich; es gibt keine impliziten Produktiv-Secrets.

## Vor jedem produktiven Betrieb

- TLS/HTTPS und Reverse Proxy mit den dokumentierten Headern, Zertifikaten und vertrauenswürdigen Proxy-IP-Adressen betreiben.
- `SESSION_COOKIE_SECURE=true` beibehalten; der Produktionsmodus lehnt deaktivierte Secure-Cookies oder einen nicht gemeinsam genutzten Rate-Limit-Speicher ab.
- `MFA_ENCRYPTION_KEY` als Fernet-Schlüssel generieren, auf allen Instanzen identisch und sicher außerhalb von Git und Image-Layern bereitstellen; Schlüsselrotation planen.
- Redis-Speicher und Proxy-IP-Vertrauen gemäß Produktionskonfiguration betreiben und überwachen.
- Secrets sicher außerhalb von Git und Image-Layern bereitstellen.
- Den Migrationsdienst einmalig je Release vor den API-Replikaten starten; API-Container migrieren nicht selbst.
- Administrator-, Migrations- und Laufzeit-Secrets getrennt aus einem Secret-Manager bereitstellen; API und Worker ausschließlich mit `securityops_runtime` betreiben. Der Migrationsbenutzer ist Datenbankeigentümer und kann Daten verändern.
- Verschlüsselte Backups und den Prüfpunkt aus `python -m scripts.verify_audit_integrity` regelmäßig in ein getrenntes, zugriffsbeschränktes und unveränderliches Ziel übertragen. Wiederherstellung und Integritätsprüfung regelmäßig in einer isolierten Testumgebung praktisch testen.
- Sicherheits- und Datenschutzprüfung, Aufbewahrungs-/Löschregeln, Monitoring und Incident-Abläufe definieren.
- OWKS-Downgrade nicht ausführen, solange Betriebsdaten vorliegen; Migration 0014 verweigert den Downgrade dann explizit. Für sichere Rollbacks müssen Datenaufbewahrung und Exportverfahren vorher festgelegt werden.
- Dokumenten-/Vertrags-Downgrade 0015 verweigert den Rückbau, sobald Fachdaten oder angepasste Erinnerungseinstellungen bestehen. Die CI prüft die Ablehnung mit einem PostgreSQL-Testdatensatz und bestätigt, dass der Datensatz erhalten bleibt.
- Statische OWKS-QR-Codes und NFC-Tags sind kopierbar. Web-NFC, Challenge und serverseitige Replay-Prüfungen beweisen keine physische Anwesenheit; dynamische kryptografische Tags oder verwaltete Standort-/Gerätenachweise sind nicht integriert.
- Keine echten Kunden-/Personal-/Einsatzdaten verwenden, solange fachliche Berechtigungen und Produktionshärtung fehlen.

## Grenzen des Audit-Schutzes

Append-only-Trigger und Hash-Verkettung sind keine vollständige Abwehr gegen privilegierte Manipulation: Datenbank-Owner und Superuser können Trigger deaktivieren, Funktionen ersetzen oder Datensätze samt Kette neu berechnen. Der Kettenprüfpunkt ist nur aussagekräftig, wenn er außerhalb der Datenbank in einem getrennten Vertrauensbereich gespeichert wird. Externe, getrennte Backups und deren regelmäßiger Restore sind weiterhin erforderlich. Die Umsetzung ist keine Produktionsabnahme.

## Offene Sicherheitsfunktionen

Ein nutzerinitiierter Passwort-Reset mit verifizierter E-Mail-Zustellung fehlt, weil kein Zustellprovider eingerichtet ist. Bis dahin steht nur der auditierte Admin-Reset mit erzwungener Passwortänderung zur Verfügung. Instanzübergreifende Rate-Limits setzen den gemeinsamen Redis-Speicher voraus. Der externe Backup-/Prüfpunkt-Betrieb muss vom Betreiber eingerichtet und überprüft werden. Die Objektberechtigungen und Datentrennung müssen weiterhin durch PostgreSQL-CI und Review bestätigt werden. Das implementierte System ist nicht sicherheitszertifiziert und noch kein vollständiges Produkt.

## Automatisierte Sicherheitsbefunde

CI auditiert die in `backend/pyproject.toml` deklarierten Python-Abhängigkeiten mit `pip-audit` und den vollständigen Frontend-Lockfile-Baum mit `npm audit`; bekannte Schwachstellen ab mittlerer Schwere blockieren den Job. CodeQL analysiert Python sowie JavaScript/TypeScript bei Pull Requests, Änderungen auf `main` und wöchentlich. Findings müssen vor Freigabe auf Betroffenheit und Ausnutzbarkeit geprüft, einem Verantwortlichen zugeordnet und als Fix oder begründete Ausnahme dokumentiert werden. Eine Ausnahme nennt mindestens Begründung, kompensierende Maßnahme, Verantwortlichen und Ablauf-/Neubewertungsdatum. Scannerbefunde dürfen nicht kommentarlos unterdrückt werden; nach Fix oder Ausnahme müssen erneute Analyse und Review erfolgen.

Der CI-Restore-Test erzeugt ausschließlich synthetische, kurzlebige Testdaten. Kein produktives Backup und kein echter Kunden-, Personal- oder Einsatzdatensatz wurde restauriert.

## Dokumenten- und Vertragsverwaltung

- Dokumentdateien liegen im Compose-Volume `document_storage` unter `/var/lib/securityops/documents`, außerhalb aller Frontend-/Static-Verzeichnisse. Im lokalen Betrieb kann `DOCUMENT_STORAGE_PATH` auf ein privates Verzeichnis gesetzt werden; Zugriffsschutz des Datenträgers und Backups liegen beim Betreiber.
- Neue Dokument-/Vertragsdateien, neue Dokumentversionen, OWKS-Anhänge und Personal-Qualifikationsdateien werden vor Datenbank-/Dateispeicherung synchron an den internen ClamAV-Dienst übergeben. Erkennung, Protokollfehler, Timeout und Nichterreichbarkeit verhindern die Freigabe; eine bereits gespeicherte Datei wird dadurch weder rückwirkend geprüft noch nachträglich als sicher bestätigt. Einzelheiten und Grenzen: [Upload-Prüfung](UPLOAD_SECURITY.md).
- Dateien erhalten eine zufällige 128-Bit-hex Storage-ID; Originalnamen werden nie als Pfad verwendet. Pfade akzeptieren ausschließlich die erwartete ID-Form und werden innerhalb des aufgelösten Root-Verzeichnisses geprüft. Dateien werden exklusiv mit Modus `0600`, Verzeichnis mit `0700` angelegt.
- Unterstützt werden PDF, PNG, JPEG, DOCX und XLSX. Endung, deklarierter MIME-Typ und serverseitige Signatur beziehungsweise OOXML-ZIP-Struktur müssen zusammenpassen. Uploadgrenze: Standard 20 MiB, konfigurierbar bis maximal 100 MiB. Bei erfolgreichem Upload werden SHA-256 und Größe gespeichert.
- Download erfolgt nur über eine authentifizierte, berechtigungs- und objektgeprüfte API-Route; Antworten sind `attachment`, `private, no-store` und `nosniff`. Upload, Download, Änderung, Archivierung, Freigabe und Lesebestätigung erzeugen Audit-Einträge. Versionen werden nicht überschrieben; Archivierung löscht nicht dauerhaft.
- Mitarbeiterdokumente benötigen HR-Sensitivberechtigung oder die eigene Personalzuordnung; Objektakten erfordern globale Objektberechtigung oder passende Objektzuweisung. Kundendatensätze benötigen Kundenrechte. Diese Prüfungen gelten auch für Download, Freigabe und Erinnerungsansichten.
- Der ClamAV-Scan ersetzt keinen vollständigen Office-Parser oder Inhaltssicherheitsdienst. Dokumentfreigabe ist ein interner Status und keine elektronische Signatur. Verschlüsselung im Ruhezustand wird nicht auf Anwendungsebene bereitgestellt.
- Erinnerungen werden aktiv durch berechtigte API/UI ausgelöst und datenbankseitig dedupliziert. Es gibt keinen Zeitplan-Worker und keine Mail-/Push-Integration. Bis ein vertrauenswürdiger Scheduler und ein Virenscanner eingerichtet, die PostgreSQL-/Docker-Integration ausgeführt und Backup/Restore praktisch getestet wurden, darf die Funktion nicht als produktionsgehärtet gelten.
