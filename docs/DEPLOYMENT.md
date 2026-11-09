# Deployment

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

Der ClamAV-Dienst benötigt beim ersten Start Zeit zum Laden seiner Signaturdatenbank. Sein Compose-Healthcheck verlangt sowohl eine `PONG`-Antwort als auch eine ClamAV-`VERSION`-Antwort mit nichtleerer Signaturdatenbank-Version; mit 30 Minuten Startzeitraum wird die API erst nach erreichbarer, initialisierter Engine gestartet. Der Dienst ist nur im internen Compose-Datennetz erreichbar und veröffentlicht keinen Host-Port. Das mehrplattformfähige ClamAV-Debian-Image ist auf Version und OCI-Manifest-Digest festgelegt; seine laufend aktualisierten Virendefinitionen können Erkennungsergebnisse trotz gleicher Container-Version zeitabhängig ändern. Digest-Aktualisierungen müssen geprüft und explizit übernommen werden. Details zu Grenzwerten, Fehlerverhalten und API-Ablehnungen stehen in [Upload-Prüfung](UPLOAD_SECURITY.md).

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

## TLS-Reverse-Proxy und vertrauenswürdige Header

TLS wird von einem separat verwalteten Reverse Proxy terminiert. Beispiel für Nginx auf demselben Host; Zertifikatspfade, Hostname und TLS-Parameter müssen an die Betriebsumgebung angepasst werden:

```nginx
server {
    listen 443 ssl;
    server_name securityops.example.invalid;

    ssl_certificate /etc/letsencrypt/live/securityops.example.invalid/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/securityops.example.invalid/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    add_header Strict-Transport-Security "max-age=31536000" always;

    location / {
        proxy_pass http://127.0.0.1:5173;
        proxy_set_header Host $host;
        # Eingehenden, nicht vertrauenswürdigen X-Forwarded-For-Wert ersetzen.
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

HSTS nur aktivieren, wenn die Domain dauerhaft ausschließlich über HTTPS erreichbar ist; `includeSubDomains` nur setzen, wenn ausnahmslos alle Subdomains HTTPS unterstützen. Der statische Nginx-Webserver setzt `nosniff`, Frame-Schutz, Referrer-Policy, eine restriktive Content-Security-Policy und eine Kamera-erlaubende Permissions-Policy. Der TLS-Proxy muss eingehende `X-Forwarded-*`-Header überschreiben, statt sie ungeprüft von Clients zu übernehmen.

Uvicorn vertraut ausschließlich den in `FORWARDED_ALLOW_IPS` aufgelisteten Adressen; Wildcards sind verboten und werden im Produktionsmodus abgelehnt. Standard ist die feste Frontend-Container-IP `172.28.0.10`, die der API als unmittelbarer Proxy-Hop bekannt ist. `APP_NETWORK_SUBNET` und `APP_FRONTEND_IP` müssen zusammenpassen und dürfen keine bestehenden Host-/Docker-Netze überlappen. Läuft ein TLS-Proxy vor dem veröffentlichten Frontend-Port, anhand der Nginx-Logs die von der Frontend-Instanz tatsächlich beobachtete Proxy-/Bridge-IP ermitteln und nur diese zusätzlich in `FORWARDED_ALLOW_IPS` aufnehmen; die Frontend-Container-IP muss enthalten bleiben. Keine beliebigen Client-Adressen oder `*` vertrauen. Der TLS-Proxy muss `X-Forwarded-For` mit der ermittelten Client-IP neu setzen, damit die Weitergabe an FastAPI eine kontrollierte Kette bildet. Die Rate-Limit-IP wird nur aus dieser vertrauenswürdigen Proxy-Kette abgeleitet.

## Secrets und Betrieb

- `POSTGRES_ADMIN_PASSWORD`, `POSTGRES_MIGRATION_PASSWORD`, `POSTGRES_RUNTIME_PASSWORD`, `DOCUMENT_ENCRYPTION_KEYS`, TLS-Schlüssel und Backup-Identitäten aus einem Secret-Manager bereitstellen; nicht in `.env`, Git oder Images veröffentlichen. Das Administrator-Secret darf nicht an API oder Worker gelangen. Wenn TOTP-MFA genutzt wird, zusätzlich `MFA_ENCRYPTION_KEY` als Fernet-Schlüssel sicher setzen und auf allen API-Instanzen identisch halten; Schlüsselrotation vorab planen.
- Die Beispielkonfiguration trennt PostgreSQL-Administrator, Migrationsbenutzer und Laufzeitbenutzer. `securityops_runtime` hat keine Superuser-, Rollen-, Datenbank- oder Schema-Erstellungsrechte; der Migrationsbenutzer besitzt das Schema und kann DDL sowie Datenänderungen ausführen.
- Redis ist nur im internen Compose-Netz erreichbar und speichert flüchtige Rate-Limit-Zähler. Für externe Redis-Installationen `rediss://` und die dafür erforderlichen Zugriffsdaten sicher bereitstellen.
- Dokumente liegen im privaten Volume und niemals im statischen Webroot; neue Dateien sind zusätzlich anwendungsseitig authentifiziert verschlüsselt. Volume-Zugriff, Aufbewahrung und Backups bleiben Betreiberaufgaben.
- ClamAV läuft als interner Compose-Dienst `clamav` auf TCP 3310; dieser Port wird nicht nach außen veröffentlicht. `MALWARE_SCANNER_TIMEOUT_SECONDS` (Standard 30 Sekunden, maximal 300) und `MALWARE_SCAN_MAX_BYTES` (Standard/maximal 100 MiB) begrenzen die Backend-Prüfung; ClamAV erhält passende Stream-/Dateigrenzen. Ohne erreichbaren Scanner werden Uploads abgewiesen. Außerhalb dieses Compose-Stacks muss ein vertrauenswürdiger ClamAV-Dienst mit kompatiblen Grenzwerten konfiguriert werden.
- Der Notification-/OWKS-Worker läuft als eigener Compose-Dienst gegen PostgreSQL. `NOTIFICATION_WORKER_POLL_SECONDS` (2), `NOTIFICATION_WORKER_BATCH_SIZE` (25, höchstens 100), `NOTIFICATION_WORKER_LEASE_SECONDS` (300) und `NOTIFICATION_WORKER_MAX_ATTEMPTS` (8) steuern Polling, Batch, Lease und Retry-Obergrenze. Worker-Logs/CLI enthalten keine Payloads oder Nachrichtentexte; Metriken und externer Alarmierungsdienst sind nicht enthalten.
- Images, OS-Pakete und Abhängigkeiten regelmäßig aktualisieren; CI-Images bauen keine Images mit festgeschriebenem Digest. Für den produktiven Rollout geprüfte Images/Digests freigeben und einen Rollback-Ablauf erproben.
- Monitoring, Protokollaufbewahrung ohne Tokens/Passwörter, Alarmierung, Datenbankrechte, Datenschutz und Incident-Verfahren vor öffentlichem Betrieb festlegen.

## Grenzen und Nachweise

CI baut die Container, prüft Rollen, Migrationen, Audit-Integrität und API-Tests auf PostgreSQL 17 und führt einen verschlüsselten Backup-/Restore-Zyklus für Datenbank und Dokumentenvolume in isolierten Testressourcen aus. Datenbank-Owner und Superuser können Trigger oder Integritätsfunktionen weiterhin ändern und die Hash-Kette neu berechnen. Ein außerhalb der Datenbank getrennt gespeicherter Prüfpunkt und getrennte, unveränderliche Sicherungen sind nötig, um solche Änderungen erkennbar zu machen. Der CI-Restore ist kein Restore einer Produktionssicherung. TLS-Zertifikate, DNS, produktive Proxy-IP, Secret-Manager, Produktionsrechte, Verfügbarkeit und Wiederherstellung im Betreiberumfeld wurden dadurch nicht eingerichtet oder nachgewiesen. Es wird keine Produktionsfreigabe behauptet.
