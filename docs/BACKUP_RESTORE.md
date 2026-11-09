# Backup und Wiederherstellung

> **Leitfaden:** Das Repository enthält ein manuell gestartetes Backup-Skript und einen
> ausschließlich isolierten Restore-Test, aber keinen Zeitplaner, keine externe Ablage und
> keine Produktiv-Restore-Automatisierung. Aufbewahrung, Schlüsseltrennung, Alarmierung und
> regelmäßige Restore-Proben müssen Betreiber in der Zielumgebung umsetzen und nachweisen.

## Verschlüsseltes Backup

Die Compose-Datenbank ist PostgreSQL 17. `scripts/backup.sh` stoppt die API während der Sicherung, damit Datenbank und Dokumentenvolume konsistent aufgenommen werden, und startet sie anschließend wieder, falls sie zuvor lief. PostgreSQL-Custom-Dump und TAR-Archiv der privaten Dokumentenablage werden jeweils direkt durch `age` gestreamt; unverschlüsselte Archive werden nicht auf dem Host zwischengespeichert. Währenddessen ist die Oberfläche nicht nutzbar. Andere Datenbank-Schreibprozesse und Releases müssen ebenfalls pausiert sein. Benötigt werden Docker Compose, `age` und ein nur für Backups vorgesehener öffentlicher Empfänger:

```sh
umask 077
mkdir -p "$HOME/.config/securityops"
age-keygen --output "$HOME/.config/securityops/backup-identity"
chmod 600 "$HOME/.config/securityops/backup-identity"
age-keygen -y "$HOME/.config/securityops/backup-identity"
export BACKUP_AGE_RECIPIENT='age1...' # Ausgabe des vorherigen Befehls
bash scripts/backup.sh "/sicherer-zielpfad/securityops-$(date +%F)"
```

Das neue Backup-Verzeichnis enthält `database.dump.age` und `documents.tar.age`. Das Skript prüft nur, dass beide verschlüsselten Dateien nicht leer sind; es entschlüsselt sie nicht zur Integritätsprüfung und bestätigt keinen Restore. Es stoppt und startet die API, aber nicht `notification-worker` oder andere externe Schreibprozesse. Vor dem Backup müssen Betreiber daher alle weiteren Datenbankschreiber pausieren und nachher wieder starten. Beispiel für den vorhandenen Worker-Dienst:

```sh
docker compose stop notification-worker
bash scripts/backup.sh "/sicherer-zielpfad/securityops-$(date +%F)"
docker compose start notification-worker
```

Wird das Skript abgebrochen, muss geprüft werden, ob die API wieder läuft; den zuvor gestoppten Worker ebenfalls gezielt wieder starten. Das Skript versucht, die API bei normalem Beenden oder Fehlern wieder zu starten, doch Host-/Docker-Ausfälle können diese Bereinigung verhindern.

Die private age-Identität und `DOCUMENT_ENCRYPTION_KEYS` getrennt, zugriffsbeschränkt und unabhängig wiederherstellbar aufbewahren; zum Entschlüsseln der Anwendungsdateien wird der passende Dokumentenschlüsselring zusätzlich zur age-Identität benötigt. Alte Dokumentenschlüssel erst entfernen, wenn sie in keiner aufbewahrten Sicherung mehr benötigt werden. Backup-Dateien enthalten vertrauliche Kunden-, Personal- und Betriebsdaten: nach erfolgreichem Backup das Verzeichnis auf ein getrenntes, zugriffsbeschränktes Ziel übertragen und Aufbewahrung sowie Löschung festlegen. Verschlüsselte Archive und private Entschlüsselungsidentitäten gehören nicht in dieselbe Ablage oder Zugriffsdomain. Das Skript überschreibt kein bestehendes Zielverzeichnis. Ein verschlüsseltes lokales Backup allein ist keine ausreichende Auslagerung.

### Betreiberaufgaben für Sicherungsbetrieb

Der Zeitplan muss in der Zielumgebung eingerichtet und überwacht werden; es gibt keinen enthaltenen Backup-Scheduler. Betreiber müssen RPO/RTO, Häufigkeit, Aufbewahrungsdauer, geschützte Übertragung, Zugriffstrennung, Löschung sowie Alarmierung bei fehlendem/fehlgeschlagenem Lauf festlegen. Protokollieren, welche Sicherung vollständig an den getrennten Speicher übertragen wurde, ohne Schlüssel oder vertrauliche Inhalte mitzuloggen. Regelmäßig freien Speicherplatz und Lesbarkeit des Sicherungsziels prüfen. Für Produktionsbetrieb kontrolliert sicherstellen, dass Backup-Prozess/API/Worker und weitere DB-Schreiber konsistent pausiert sind. Der Beispielaufruf ist manuell; er erzeugt oder überträgt keinen Backup-Plan.

Die Audit-Integritätsprüfung muss im Restore-Test auf der wiederhergestellten Testdatenbank laufen, nicht lediglich auf der aktiven Quelldatenbank. `restore-test.sh` führt nach Wiederherstellung bereits `python -m scripts.verify_audit_integrity` über den Migrationsdienst auf der Testdatenbank aus. Der unabhängige Prüfpunkt (Anzahl und SHA-256-Kettenendwert) muss außerhalb der Datenbank und getrennt vom Backup gespeichert und beim Test verglichen werden. Diese Vergleichs-/Ablageautomatik stellt das Skript nicht bereit.

Ein Hash-Kettenwert in derselben Datenbank reicht nicht als unabhängiger Manipulationsnachweis. Ein einfacher Backup-Erfolg oder Dateigrößenvergleich ist kein Ersatz für Entschlüsselungs-, PostgreSQL-, Datei- und Anwendungsprüfungen in einer isolierten Wiederherstellung.

## Wiederherstellungstest

Restore ausschließlich in einem eigens dafür bereitgestellten, isolierten Compose-Testprojekt mit separaten PostgreSQL- und Dokumentenvolumes ausführen. Niemals das Produktions-Compose-Projekt oder die Produktionsdatenbank als Ziel verwenden. Für jeden Lauf einen neuen `COMPOSE_PROJECT_NAME` wählen, der `restore-test` enthält, und `POSTGRES_DB=securityops_backup_test` setzen. Das Restore-Skript verweigert Projekt-Namen ohne `restore-test` und Datenbanknamen ohne `_test`-Endung. Das Skript erstellt ausschließlich die feste Testdatenbank `securityops_restore_test` und stellt Dokumente in ein separates `restore_test_documents`-Volume wieder her; es überschreibt und löscht keine vorhandenen Inhalte. Eine bereits vorhandene Testdatenbank führt zum Abbruch. Für einen Anwendungsabruf im Test zusätzlich den passenden `DOCUMENT_ENCRYPTION_KEYS`-Schlüsselring und `DOCUMENT_ENCRYPTION_ACTIVE_VERSION` sicher an den Testprozess übergeben; sie werden nicht im age-Backup enthalten.

Für den isolierten Test eigene, nicht-produktive Datenbank-Secrets setzen und die Datenbank im eigenen Compose-Projekt starten, bevor das Skript ausgeführt wird:

```sh
export COMPOSE_PROJECT_NAME=securityops-restore-test
export POSTGRES_DB=securityops_backup_test
export BACKUP_AGE_IDENTITY_FILE="$HOME/.config/securityops/backup-identity"
export RESTORE_TEST_ACK=I_AM_USING_AN_ISOLATED_TEST_DATABASE
docker compose up -d db
bash scripts/restore-test.sh "/sicherer-zielpfad/securityops-YYYY-MM-DD"
```

Das Skript entschlüsselt direkt in `pg_restore` beziehungsweise in den isolierten Dokumenten-Container, wendet Rollen-/Migrationseinrichtung auf die Testdatenbank an, prüft Audit-Integrität, Migrationsstand und Berechtigungsdaten und lässt Testdatenbank sowie Testvolume zur Prüfung bestehen. Danach müssen Betreiber den Kettenendwert mit dem unabhängig gespeicherten Prüfpunkt vergleichen sowie Datenbankzugriff, benötigte fachliche Beziehungen, Dateien und Anwendungssmoke-Tests prüfen, den Lauf protokollieren und die Testumgebung gemäß ihrem isolierten Verfahren entfernen. Für entschlüsselte Dateien ist zusätzlich der passende Anwendungsschlüsselring nötig. Wegen der enthaltenen Daten darf die Testumgebung nicht öffentlich erreichbar sein. Das Skript löscht Testdatenbank und Volume nicht automatisch.

## Automatisierter Nachweis und Grenzen

Der GitHub-CI-Workflow erzeugt einen ephemeren age-Schlüssel, migriert eine neue PostgreSQL-17-Datenbank mit getrennten Rollen und startet die Compose-Produktionsdienste mit synthetischen Daten. Er erstellt ein verschlüsseltes Datenbank- und Dokumentenbackup, restauriert beide Teile in eine getrennte Testdatenbank und ein getrenntes Testvolume und verifiziert Migration, Berechtigungsdaten sowie eine synthetische Dokumentdatei. Das ist ein Restore-Test mit synthetischen CI-Daten; CI restauriert keine produktive Sicherung, prüft keine Produktionsschlüssel und belegt weder Produktivbetrieb noch externe Ablage, Schlüsselwiederherstellung, Alarmierung oder RPO/RTO. Vor dem Produktivbetrieb muss der Betreiber den Ablauf regelmäßig mit echten, verschlüsselten Sicherungen in einer getrennten Zielumgebung ausführen, Prüfpunktvergleich und Anwendungstests ergänzen und dokumentieren.

Für den Betrieb muss der Betreiber eine angemessene Restore-Häufigkeit festlegen (mindestens nach Änderungen an Datenbankschema, Backup-Verfahren oder Verschlüsselungsschlüsseln) und eine aktuelle Sicherung in isolierter Umgebung proben. Den Lauf mit Zeitpunkt, getesteter Sicherung, Integritätsprüfpunkt, Schlüsselversionen, Ergebnis und Abweichungen in einem vom Backup getrennten Betriebsprotokoll festhalten. CI-Läufe ersetzen diese Betreiberprüfung nicht.
