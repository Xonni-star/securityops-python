# Backup und Wiederherstellung

## Verschlüsseltes Backup

Die Compose-Datenbank ist PostgreSQL 17. `scripts/backup.sh` stoppt die API während der Sicherung, damit Datenbank und Dokumentenvolume konsistent aufgenommen werden, und startet sie anschließend wieder, falls sie zuvor lief. PostgreSQL-Custom-Dump und TAR-Archiv der privaten Dokumentenablage werden jeweils direkt durch `age` gestreamt; unverschlüsselte Archive werden nicht auf dem Host zwischengespeichert. Währenddessen ist die Oberfläche nicht nutzbar. Andere Datenbank-Schreibprozesse und Releases müssen ebenfalls pausiert sein. Benötigt werden Docker Compose, `age` und ein nur für Backups vorgesehener öffentlicher Empfänger:

```sh
umask 077
mkdir -p "$HOME/.config/securityops"
age-keygen -o "$HOME/.config/securityops/backup-identity"
age-keygen -y "$HOME/.config/securityops/backup-identity"
export BACKUP_AGE_RECIPIENT='age1...' # Ausgabe des vorherigen Befehls
bash scripts/backup.sh "/sicherer-zielpfad/securityops-$(date +%F)"
```

Das neue Backup-Verzeichnis enthält `database.dump.age` und `documents.tar.age`. Die private Identität getrennt, zugriffsbeschränkt und wiederherstellbar aufbewahren. Backup-Dateien enthalten vertrauliche Kunden-, Personal- und Betriebsdaten: nach erfolgreichem Backup das Verzeichnis auf ein getrenntes, zugriffsbeschränktes Ziel übertragen und Aufbewahrung sowie Löschung festlegen. Das Skript überschreibt kein bestehendes Zielverzeichnis. Ein verschlüsseltes lokales Backup allein ist keine ausreichende Auslagerung.

Für Audit-Schutz den Sicherungsprozess regelmäßig und unabhängig vom Datenbankhost ausführen. Nach einem erfolgreichen Backup die Integrität mit dem Migrations-/Prüfbenutzer prüfen:

```sh
docker compose --profile release run --rm migrate python -m scripts.verify_audit_integrity
```

Anzahl und ausgegebenen SHA-256-Kettenendwert zusammen mit Sicherungszeit und Backup-Identität in einem getrennten, zugriffsbeschränkten und unveränderlichen System protokollieren. Backup-Dateien und Prüfprotokoll dürfen nicht ausschließlich auf demselben Datenbankhost liegen. Aufbewahrung, Zugriff, Verschlüsselung, unabhängige Überwachung und Alarmierung sind vom Betreiber festzulegen. Ein Hash-Kettenwert in derselben Datenbank reicht nicht als unabhängiger Manipulationsnachweis.

## Wiederherstellungstest

Restore ausschließlich in einem eigens dafür bereitgestellten, isolierten Compose-Testprojekt mit separaten PostgreSQL- und Dokumentenvolumes ausführen. Niemals das Produktions-Compose-Projekt oder die Produktionsdatenbank als Ziel verwenden. Vorher `COMPOSE_PROJECT_NAME=securityops-restore-test` und `POSTGRES_DB=securityops_backup_test` setzen. Das Restore-Skript verweigert Projekt-Namen ohne `restore-test` und Datenbanknamen ohne `_test`-Endung. Das Skript erstellt ausschließlich die feste Testdatenbank `securityops_restore_test` und stellt Dokumente in ein separates `restore_test_documents`-Volume wieder her; es überschreibt und löscht keine vorhandenen Inhalte. Eine bereits vorhandene Testdatenbank führt zum Abbruch.

```sh
export COMPOSE_PROJECT_NAME=securityops-restore-test
export POSTGRES_DB=securityops_backup_test
export BACKUP_AGE_IDENTITY_FILE="$HOME/.config/securityops/backup-identity"
export RESTORE_TEST_ACK=I_AM_USING_AN_ISOLATED_TEST_DATABASE
bash scripts/restore-test.sh "/sicherer-zielpfad/securityops-YYYY-MM-DD"
```

Das Skript entschlüsselt direkt in `pg_restore` beziehungsweise in den isolierten Dokumenten-Container, prüft Migrationsstand und Berechtigungsdaten und lässt Testdatenbank sowie Testvolume zur Prüfung bestehen. Nach dem Restore `python -m scripts.verify_audit_integrity` mit einem auf die Testdatenbank gerichteten Prüfzugang ausführen und den Kettenendwert mit dem unabhängig gespeicherten Prüfpunkt vergleichen. Anschließend Datenbankzugriff, benötigte fachliche Beziehungen, Dateien und Anwendungssmoke-Tests prüfen, den Lauf protokollieren und die Testumgebung gemäß ihrem isolierten Verfahren entfernen. Wegen der enthaltenen Daten darf sie nicht öffentlich erreichbar sein.

## Automatisierter Nachweis und Grenzen

Die GitHub-CI erzeugt einen ephemeren age-Schlüssel, migriert eine neue PostgreSQL-17-Datenbank mit getrennten Rollen, prüft Bestandsdatenmigration und Laufzeitrechte für Audit-Einträge und startet die Produktionscontainer mit synthetischem Admin. Sie erstellt ein verschlüsseltes Datenbank- und Dokumentenbackup, restauriert beide Teile in eine getrennte Testdatenbank und ein getrenntes Testvolume und verifiziert Migration, Berechtigungsdaten sowie eine synthetische Dokumentdatei. Das ist ein reproduzierbarer Restore-Test mit synthetischen CI-Daten; es ist kein Backup oder Restore einer produktiven Installation. Vor dem Produktivbetrieb muss der Betreiber denselben Ablauf regelmäßig mit echten, verschlüsselten Sicherungen in einer getrennten Testumgebung ausführen und dokumentieren.
