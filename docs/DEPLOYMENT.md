# Deployment

> **Betreiberleitfaden, keine Bereitstellungsautomatisierung:** Das Repository enthält weder
> einen TLS-Reverse-Proxy noch Secret-Manager, Backup-Scheduler, externes Monitoring,
> Alarmierung, Logrotation oder Compose-Ressourcenlimits. Die folgenden Betreiber-Schritte
> müssen für die Zielumgebung eingerichtet, sicher konfiguriert und praktisch getestet werden.
> CI-Ergebnisse sind kein Nachweis für eine produktive Umgebung.

## Laufzeitaufbau

Das Produktions-Compose-Setup baut das Frontend als statische Vite-Dateien und liefert sie über einen unprivilegierten Nginx-Prozess auf Port 8080 im Container aus. Nginx leitet `/api/` intern an FastAPI weiter; PostgreSQL und Redis liegen in einem internen Compose-Netz ohne veröffentlichte Ports. Nur Frontend und API sind am Host-Loopback gebunden. Die API erzwingt im Produktionsmodus Secure-Cookies und Redis als gemeinsamen Rate-Limit-Speicher. Ein eigener `migrate`-Dienst ist nur über das Profil `release` verfügbar und wird nicht automatisch von API-Replikaten gestartet.

Für den ersten Start oder ein Release:

```sh
docker compose up -d db redis clamav
docker compose ps clamav
docker compose --profile release run --rm provision-db
docker compose --profile release run --rm --no-deps migrate
docker compose up --build -d api notification-worker frontend
```

Der erste Befehl führt den idempotenten Rollen-Provisioner als Administrator aus; der zweite wendet Alembic als `securityops_migrator` an. API und Worker verwenden ausschließlich `securityops_runtime`. Vor dem Upgrade eines bestehenden Volumes `POSTGRES_ADMIN_USER`/`POSTGRES_ADMIN_PASSWORD` auf den bisherigen PostgreSQL-Administrator setzen, drei unterschiedliche Secrets bereitstellen und ein vollständiges Backup prüfen. Der Provisioner überträgt bestehendes Schema-/Objekteigentum an den Migrationsbenutzer, ohne Datensätze zu ändern oder zu löschen. Nicht mit Produktionsdaten experimentieren; den Upgradepfad zuerst mit einer getrennten Kopie und anschließendem Integritäts-/Restore-Test prüfen.

Der ClamAV-Dienst benötigt beim ersten Start Zeit zum Laden seiner Signaturdatenbank. Sein Compose-Healthcheck verlangt sowohl eine `PONG`-Antwort als auch eine ClamAV-`VERSION`-Antwort mit nichtleerer Signaturdatenbank-Version; mit 30 Minuten Startzeitraum wird die API erst nach erreichbarer, initialisierter Engine gestartet. Der Dienst ist nur im internen Compose-Datennetz erreichbar und veröffentlicht keinen Host-Port. Das ClamAV-Debian-Image ist auf Version und OCI-Manifest-Digest festgelegt; seine laufend aktualisierten Virendefinitionen können Erkennungsergebnisse trotz gleicher Container-Version zeitabhängig ändern. Digest-Aktualisierungen müssen geprüft und explizit übernommen werden. Details zu Grenzwerten, Fehlerverhalten und API-Ablehnungen stehen in [Upload-Prüfung](UPLOAD_SECURITY.md).

Compose setzt für die Standarddienste `restart: unless-stopped` und Healthchecks, aber keine CPU-/Speicherlimits, Compose-Logtreiber oder Logrotation. Ein fehlgeschlagener Healthcheck löst für sich allein keinen Container-Neustart aus. Host-Docker-Daemon und Betreiber müssen Ressourcenüberwachung/-grenzen sowie begrenzte, zugriffskontrollierte Logaufbewahrung konfigurieren und testen. Keine Tokens, Passwörter oder vertrauliche Anwendungsdaten in Betriebsprotokolle kopieren.

## Entwicklungs- und Produktionsgrenze

Für lokale HTTP-Entwicklung ausschließlich den Override `docker-compose.dev.yml` verwenden. Die Datei überschreibt nur die API-Umgebungswerte `APP_ENV`, `CORS_ORIGINS` und `SESSION_COOKIE_SECURE`; sie ist kein Produktions-Override. Die Compose-Konfiguration veröffentlicht Frontend (`127.0.0.1:5173`) und API (`127.0.0.1:8000`) nur am Host-Loopback. Datenbank, Redis und ClamAV haben keine veröffentlichten Host-Ports; PostgreSQL und Redis sollten nicht zusätzlich öffentlich freigegeben werden.

Das Repository stellt keinen externen Proxy oder TLS-Endpunkt bereit. Vor Produktivbetrieb müssen Betreiber mindestens DNS-Einträge und Erreichbarkeit, TLS-Zertifikatsausstellung/-erneuerung, HTTPS-Weiterleitung und Firewall-Regeln am eigenen Edge-Proxy einrichten. Die Compose-Ports sind an Loopback gebunden; ein Proxy muss daher auf demselben Host laufen oder der Betreiber muss eine bewusst konfigurierte, abgesicherte Netzverbindung einrichten. Der Proxy muss nur die benötigten öffentlichen Ports an die Frontend-Instanz weiterreichen, `/api/` unverändert weiterleiten und eingehende `X-Forwarded-*`-Header überschreiben, insbesondere den externen `X-Forwarded-Proto` auf `https` setzen. Zertifikatsdateien und private Schlüssel gehören in die getrennte Proxy-/Secret-Verwaltung, nicht in dieses Repository oder ein App-Image. Ohne den externen Proxy ist die Installation nicht öffentlich per HTTPS erreichbar.

### Vertrauenswürdige Proxy-IP

Uvicorn vertraut ausschließlich den in `FORWARDED_ALLOW_IPS` aufgelisteten Adressen; Wildcards sind verboten und werden im Produktionsmodus abgelehnt. Standard ist die feste Frontend-Container-IP `172.28.0.10`, die der API als unmittelbarer Proxy-Hop bekannt ist. `APP_NETWORK_SUBNET` und `APP_FRONTEND_IP` müssen zusammenpassen und dürfen keine bestehenden Host-/Docker-Netze überlappen. Läuft ein TLS-Proxy vor dem veröffentlichten Frontend-Port, darf nicht geraten werden, welche Quell-IP die Frontend-Instanz sieht: Diese muss in der konkreten Zielumgebung anhand der tatsächlichen Proxy-/Netzwerk-Konfiguration ermittelt und nur dann in `FORWARDED_ALLOW_IPS` ergänzt werden. Die Frontend-Container-IP muss enthalten bleiben. Keine beliebigen Client-Adressen oder `*` vertrauen. Der externe Proxy muss `X-Forwarded-For` mit der ermittelten Client-IP neu setzen. Proxy-IP-Änderungen sind nach Deployments zu prüfen; andernfalls können Client-IP-Auswertung und Rate-Limits falsch sein.

### Betreiber-Checkliste vor Freigabe

- [ ] DNS zeigt nur auf den vorgesehenen Edge-Proxy; Firewall und Weiterleitung exponieren keine PostgreSQL-, Redis-, ClamAV- oder API-Hostports.
- [ ] TLS-Zertifikat, private Schlüssel, automatische Erneuerung und HTTPS-Weiterleitung sind auf dem separat betriebenen Proxy eingerichtet und getestet. HSTS nur aktivieren, wenn die Domain dauerhaft HTTPS erzwingt.
- [ ] Tatsächlich beobachtete Proxy-IP, `FORWARDED_ALLOW_IPS`, `APP_FRONTEND_IP` und `APP_NETWORK_SUBNET` stimmen überein; manipulierte eingehende Forwarded-Header werden überschrieben.
- [ ] Produktions-Secrets sind in einem kontrollierten Secret Store hinterlegt, haben getrennte Rollen/Schlüssel und einen getesteten Wiederherstellungsweg. Beispielwerte, `.env.example`-Platzhalter und CI-Secrets werden nicht verwendet.
- [ ] Monitoring prüft von außerhalb der Container sowohl Frontend-Erreichbarkeit als auch `GET /health/ready`; Container-Healthchecks allein überwachen weder DNS/TLS/Proxy noch Alarmzustellung. Alarmempfänger, Eskalation, Rufbereitschaft und Testalarme sind eingerichtet und getestet.
- [ ] ClamAV-Verfügbarkeit/-Initialisierung, Datenbank-/Disk-Füllstand, Backup-Alter und -Fehler, Restore-Proben, API-/Worker-Fehler sowie Worker-Backlog/Dead-Letter sind in die Betreiberüberwachung einbezogen. Für Worker-Details siehe [Notification-Worker](NOTIFICATION_WORKER.md); der Monitoring-Endpunkt braucht eine autorisierte Abfrage.
- [ ] Aufbewahrungsfristen und Rotation für Host-/Container-Logs und Audit-Daten sind festgelegt und die tatsächliche Konfiguration wurde auf dem Zielhost geprüft.
- [ ] CPU-, Speicher-, Speicherplatz- und Inode-Grenzen, Kapazitätsalarme sowie Neustartverhalten sind mit der Zielgröße dimensioniert und praktisch geprüft. Die Compose-Datei konfiguriert keine Ressourcenlimits.
- [ ] Backup-Ablauf, unabhängige Ablage, Schlüsselzugriff, Restore-Probe, Update- und Wiederanlaufverfahren sind für die Zielumgebung dokumentiert und geübt.

Die Checkliste ist eine Vorgabe, kein im Repository automatisch eingerichteter Kontrollmechanismus.

## Verschlüsselung des Dokumentenspeichers

Die API verschlüsselt neue Dateien und Anhänge vor dem Schreiben mit AES-256-GCM. Das versionierte Binärformat enthält Nonce und Schlüsselversion; die Storage-ID ist an die Authentifizierung gebunden. Größen und SHA-256 bleiben auf den Klartext bezogen. Der Produktionsstart der API schlägt fehl, wenn `DOCUMENT_ENCRYPTION_ACTIVE_VERSION` nicht auf einen gültigen Schlüssel in `DOCUMENT_ENCRYPTION_KEYS` verweist. Schlüssel werden nicht in der Datenbank oder im Image abgelegt: `DOCUMENT_ENCRYPTION_KEYS` ist ein JSON-Objekt aus Versionskennung und Base64url-kodiertem 32-Byte-Schlüssel, zum Beispiel `{"v1":"<extern bereitgestellter Schlüssel>"}`. Beide Variablen müssen über die Secret-Verwaltung an jede API-Instanz und den Wartungsbefehl gelangen; Worker erhalten sie nicht.

Für einen erstmaligen Wechsel eines bestehenden Speichers oder eine Schlüsselrotation zuerst Datenbank und komplettes Dokumentenvolume sichern und einen Restore einschließlich aller benötigten alten Schlüssel prüfen. Die Alembic-Migration muss vor dem Datenlauf angewendet sein. Alte Schlüssel bleiben im Schlüsselring, bis Dateien und wiederherzustellende Sicherungen sie nicht mehr benötigen. Dann die API stoppen, Datenbank verfügbar lassen und zunächst ohne Änderungen prüfen:

```sh
docker compose --profile release run --rm provision-db
docker compose --profile release run --rm --no-deps migrate
docker compose stop api
docker compose --profile release run --rm rekey-documents --dry-run
docker compose --profile release run --rm rekey-documents
```

Vor dem Befehl für eine Rotation müssen alter und neuer Schlüssel im JSON-Schlüsselring stehen und `DOCUMENT_ENCRYPTION_ACTIVE_VERSION` auf die neue Version zeigen. Der Befehl prüft Dateiintegrität, migriert vorhandene OWKS-/Personalanhänge aus PostgreSQL und ersetzt Dateien atomar; ein erneuter Lauf setzt eine unterbrochene Ausführung fort. Bei Fehlern bleibt der betroffene Klartextinhalt erhalten, die API bleibt gestoppt und der Vorgang muss nach Behebung der Ursache wiederholt werden. Nicht migrierte Klartextdateien sind erkennbar und werden nur durch diesen expliziten Befehl verschlüsselt; sie und Klartext-BLOBs in PostgreSQL werden in Produktion bis zur Migration nicht ausgeliefert. Dateien, Datenbank und Schlüsselring müssen gemeinsam gesichert und wiederhergestellt werden. Nach erfolgreicher Prüfung API neu starten. Ein Downgrade der Alembic-Migration wird abgelehnt, sobald Dateien auf den gemeinsamen Speicher umgestellt wurden.

Die Migration muss erfolgreich abgeschlossen sein, bevor API- oder Worker-Container aktualisiert oder skaliert werden. Bei einem Rollback darf ein destruktiver Downgrade nicht ungeprüft ausgeführt werden. Nach dem Start `GET /health/ready` prüfen; in Produktion umfasst die Readiness Datenbank und Redis. API-Prozesse führen keine Migration aus. Der separate `notification-worker` verarbeitet Task-Outbox-Ereignisse und führt den OWKS-Prüfzyklus aus; sein Containerzustand ersetzt keine Überwachung von Backlog, Dead-Letter-Ereignissen oder Betriebsalarmen.

Beim Upgrade vom bisherigen root-basierten API-Image muss das private Dokumentenvolume einmalig auf den neuen Containerbenutzer übertragen werden. Zuerst ein Backup erstellen und die alte API stoppen, dann gezielt nur das Dokumentenvolume anpassen:

```sh
docker compose stop api
docker compose run --rm --no-deps --user 0 --entrypoint chown api \
  -R 10001:10001 /var/lib/securityops/documents
```

Der Befehl ändert Dateieigentümer, nicht Dokumentinhalte. Bei Neuinstallationen mit leerem Volume ist er nicht erforderlich.

Der im Frontend-Image enthaltene statische Nginx setzt Security-Header und leitet `/api/` an die API weiter; er terminiert kein TLS. Eine konkrete TLS-Proxy-Konfiguration wird bewusst nicht vorgegeben, weil Proxy-Software, Zertifikatspfade, DNS und Netzwerktopologie nicht Teil des Repositories sind. Die Anforderungen und Prüfungen stehen unter [Entwicklungs- und Produktionsgrenze](#entwicklungs--und-produktionsgrenze) und in der [Betreiber-Checkliste](#betreiber-checkliste-vor-freigabe). HSTS nur auf dem tatsächlichen HTTPS-Endpunkt aktivieren, wenn die Domain dauerhaft ausschließlich über HTTPS erreichbar ist.

## Secrets und Betrieb

- `POSTGRES_ADMIN_PASSWORD`, `POSTGRES_MIGRATION_PASSWORD`, `POSTGRES_RUNTIME_PASSWORD`, `DOCUMENT_ENCRYPTION_KEYS`, TLS-Schlüssel und Backup-Identitäten aus einem Secret-Manager bereitstellen; nicht in `.env`, Git oder Images veröffentlichen. Die Compose-Datei nimmt die Variablen aus der Compose-Umgebung entgegen und reicht ausgewählte Werte als Container-Umgebungsvariablen weiter; sie konfiguriert selbst weder Secret-Store-Integration noch Docker-Secrets. Für den Betrieb muss der Secret-Store die Werte sicher an den Compose-Aufruf übergeben. Das Administrator-Secret darf nicht an API oder Worker gelangen. Wenn TOTP-MFA genutzt wird, zusätzlich `MFA_ENCRYPTION_KEY` als Fernet-Schlüssel sicher setzen und auf allen API-Instanzen identisch halten; Schlüsselrotation vorab planen.
- `MFA_ENCRYPTION_KEY` ist zwar in `.env.example` aufgeführt, wird aber vom aktuellen `docker-compose.yml` nicht an den API-Container weitergereicht. Ein Eintrag in `.env` allein konfiguriert TOTP-MFA im Compose-Container daher nicht; vor dem Einsatz ist eine geprüfte, zielumgebungsspezifische Variablenübergabe erforderlich.
- Die Beispielkonfiguration trennt PostgreSQL-Administrator, Migrationsbenutzer und Laufzeitbenutzer. `securityops_runtime` hat keine Superuser-, Rollen-, Datenbank- oder Schema-Erstellungsrechte; der Migrationsbenutzer besitzt das Schema und kann DDL sowie Datenänderungen ausführen.
- Redis ist nur im internen Compose-Netz erreichbar und speichert flüchtige Rate-Limit-Zähler. Für externe Redis-Installationen `rediss://` und die dafür erforderlichen Zugriffsdaten sicher bereitstellen.
- Dokumente liegen im privaten Volume und niemals im statischen Webroot; neue Dateien sind zusätzlich anwendungsseitig authentifiziert verschlüsselt. Volume-Zugriff, Aufbewahrung und Backups bleiben Betreiberaufgaben.
- ClamAV läuft als interner Compose-Dienst `clamav` auf TCP 3310; dieser Port wird nicht nach außen veröffentlicht. `MALWARE_SCANNER_TIMEOUT_SECONDS` (Standard 30 Sekunden, maximal 300) und `MALWARE_SCAN_MAX_BYTES` (Standard/maximal 100 MiB) begrenzen die Backend-Prüfung; ClamAV erhält passende Stream-/Dateigrenzen. Ohne erreichbaren Scanner werden Uploads abgewiesen. Außerhalb dieses Compose-Stacks muss ein vertrauenswürdiger ClamAV-Dienst mit kompatiblen Grenzwerten konfiguriert werden.
- Der Notification-/OWKS-Worker läuft als eigener Compose-Dienst gegen PostgreSQL. `NOTIFICATION_WORKER_POLL_SECONDS` (2), `NOTIFICATION_WORKER_BATCH_SIZE` (25, höchstens 100), `NOTIFICATION_WORKER_LEASE_SECONDS` (300) und `NOTIFICATION_WORKER_MAX_ATTEMPTS` (8) steuern Polling, Batch, Lease und Retry-Obergrenze. Worker-Logs/CLI enthalten keine Payloads oder Nachrichtentexte; Metriken und externer Alarmierungsdienst sind nicht enthalten.
- Images, OS-Pakete und Abhängigkeiten regelmäßig aktualisieren; CI-Images bauen keine Images mit festgeschriebenem Digest. Für den produktiven Rollout geprüfte Images/Digests freigeben und einen Rollback-Ablauf erproben.
- Monitoring, Protokollaufbewahrung ohne Tokens/Passwörter, Alarmierung, Datenbankrechte, Datenschutz und Incident-Verfahren vor öffentlichem Betrieb festlegen.

## Start, Neustart und Update/Rollback

Ein normaler Neustart der Standarddienste erfolgt mit `docker compose up -d`; einzelne Dienste können nach Prüfung gezielt mit `docker compose restart <service>` neu gestartet werden. Compose startet `unless-stopped`-Dienste nach einem Container-/Host-Neustart erneut, sofern sie nicht zuvor gestoppt wurden. Das ersetzt keine Readiness- oder Alarmüberwachung. Nach Host-Wartung zuerst Datenbank und Redis-Verfügbarkeit, dann `GET /health/ready`, Frontend und Worker-Gesundheit prüfen. Ein geplanter Neustart ist vorab anzukündigen und anschließend in der Zielumgebung zu verifizieren.

Für Releases:

1. Change, kompatible Datenbankmigrationen und Rückweg bewerten; Wartungsfenster und Verantwortliche festlegen.
2. Vor dem Release ein vollständiges verschlüsseltes Backup von Datenbank und Dokumentenvolume erstellen und die Sicherung an das getrennte Ziel übertragen. Den Worker und andere Schreibprozesse während des gesamten Backupfensters pausieren; `backup.sh` stoppt selbst nur die API und lässt sie nach Abschluss wieder anlaufen.
3. Images aus dem geprüften Quellstand bauen und freigeben. Dieses Compose-Setup baut Backend und Frontend lokal; eine Image-Registry, Release-Promotion oder automatische Versionsfixierung ist nicht enthalten. Compose zieht für PostgreSQL und Redis getaggte Images, während ClamAV zusätzlich per Digest festgelegt ist. Vor Rollout Änderungen dieser Basis-Images explizit prüfen.
4. Rollen provisionieren und Migration separat und einmalig ausführen (siehe Laufzeitaufbau). Erst bei Erfolg API, Frontend und Worker mit dem geprüften Stand aktualisieren und Readiness, Worker und zentrale Fachabläufe kontrollieren.
5. Bei Fehlern den Dienstzugriff begrenzen, Ursache/Logs sichern und Wiederherstellung mit kompatiblem Anwendungscode sowie konsistentem Datenbank-/Dokumentenstand entscheiden. Ein Rückwechsel des App-Images macht eine bereits ausgeführte Migration nicht rückgängig. Keine Migration oder Daten mit einem ungetesteten Downgrade zurücksetzen; insbesondere verweigern einzelne Migrationen verlustbehaftete Dokument-/Vertrags-Downgrades. Ein Rollback muss mit einer isolierten Datenkopie und der konkreten Release-Version erprobt sein.

Die konkreten Image-Tags/-Digests, Freigaben, Reihenfolge im Change-Management und Rollback-Automation sind zielumgebungsspezifisch und im Repository nicht implementiert.

## Notfallwiederherstellung

Die vorhandenen `scripts/restore-test.sh`-Schritte sind absichtlich auf ein isoliertes Testprojekt, eine `_test`-Quelldatenbank und die fest benannte Testdatenbank `securityops_restore_test` begrenzt. Sie sind kein Produktions-Restore-Befehl. Für eine Notfallwiederherstellung müssen Betreiber vorab ein eigenes, zugriffsbeschränktes Verfahren für die ausgewählte PostgreSQL- und Dokumenten-Zielumgebung festlegen und in einer isolierten Zielumgebung testen:

1. Incident-Verantwortliche aktivieren, Auswirkungen und gewünschten Wiederherstellungspunkt bestimmen; betroffene Zugänge/Netze begrenzen. Ursprungsmedien und Protokolle nicht überschreiben.
2. Sauberes, isoliertes Wiederherstellungsziel mit freigegebenem App-Stand und kompatiblen Migrationen bereitstellen. Produktiv-DNS erst nach erfolgreicher Prüfung umschalten.
3. Backup aus dem getrennten, zugriffsbeschränkten Speicher abrufen. Backup-age-Identität und alle für die Dateien nötigen `DOCUMENT_ENCRYPTION_KEYS`/aktiven Versionen unabhängig beschaffen; Schlüssel und Klartext-Backups nicht im selben Ablagebereich wie die verschlüsselten Archive halten.
4. Das für das Ziel freigegebene Verfahren verwenden, um Datenbank und vollständiges Dokumentenvolume gemeinsam wiederherzustellen. Vor dem Start öffentlicher Dienste Datenbankmigration, Audit-Integrität mit getrennt verwahrtem Prüfpunkt, Anwendungszugriff auf Dateien und fachliche Smoke-Tests prüfen.
5. Wiederherstellungsergebnis, Backup-ID/-Zeit, Schlüsselversionen, Integritätsprüfpunkt, Abweichungen und Freigabe protokollieren. Erst nach Freigabe Traffic umschalten; alten Stand für Incident-Analyse gemäß Aufbewahrungsregeln erhalten.

Dieses Verfahren ist eine Leitlinie und keine fertige Produktionsautomatisierung. Wiederherstellungsziel, akzeptabler Datenverlust/-ausfall, verwendete Befehle und DNS-Umschaltung müssen festgelegt und regelmäßig geübt werden.

## Grenzen und Nachweise

CI baut die Container, prüft Rollen, Migrationen, Audit-Integrität und API-Tests auf PostgreSQL 17 und führt einen verschlüsselten Backup-/Restore-Zyklus für Datenbank und Dokumentenvolume in isolierten Testressourcen aus. Datenbank-Owner und Superuser können Trigger oder Integritätsfunktionen weiterhin ändern und die Hash-Kette neu berechnen. Ein außerhalb der Datenbank getrennt gespeicherter Prüfpunkt und getrennte, unveränderliche Sicherungen sind nötig, um solche Änderungen erkennbar zu machen. Der CI-Restore ist kein Restore einer Produktionssicherung. TLS-Zertifikate, DNS, produktive Proxy-IP, Secret-Manager, Produktionsrechte, Verfügbarkeit und Wiederherstellung im Betreiberumfeld wurden dadurch nicht eingerichtet oder nachgewiesen. Es wird keine Produktionsfreigabe behauptet.
