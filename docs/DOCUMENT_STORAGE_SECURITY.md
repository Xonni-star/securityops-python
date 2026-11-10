# Dokumentenspeicherung und Schlüsselverwaltung

Diese Dokumentation beschreibt die Implementierung der verschlüsselten Dokumentenspeicherung und Schlüsselverwaltung gemäß den Anforderungen aus Issue #56.

## Überblick

Die Sicherheitsimplementierung schützt private Dokumentdateien durch authentifizierte Verschlüsselung ruhender Dateien. Alle Dateien im gemeinsamen Storage-Layer werden automatisch verschlüsselt, einschließlich:
- Dokumente und Verträge
- OWKS-Anhänge
- Personal-Qualifikationsdateien
- Vorfall-/Portal-Anhänge
- Andere Dateien im gemeinsamen Storage-Layer

## Verschlüsselungsmechanismus

### Algorithmus
- AES-256-GCM (Galois/Counter Mode) für symmetrische Verschlüsselung
- Authentifizierung durch HMAC-Sicherheit
- 12-byte Nonce für jeden Verschlüsselungsprozess

### Schlüsselstruktur
- Schlüssel werden aus externer Konfiguration/Secret-Verwaltung bezogen
- Versionierte Schlüssel (Key Versioning)
- Fail-closed-Modus bei fehlenden/ungültigen Schlüsseln

## Schlüsselbereitstellung

### Konfiguration
Schlüssel werden in der `.env`-Datei konfiguriert:

```env
# Dokumentenschlüssel (mehrere Versionen möglich)
DOCUMENT_ENCRYPTION_KEYS={"v1": "base64-encoded-key-here", "v2": "base64-encoded-key-here"}
DOCUMENT_ENCRYPTION_ACTIVE_VERSION="v1"
```

### Schlüsselgenerierung
Schlüssel müssen 32 Byte lange Base64-basierende Schlüssel sein:

```bash
# Generiere einen neuen 32-Byte-Schlüssel
openssl rand -base64 32

# Oder mit Python
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Sicherheitsrichtlinien
- Schlüssel dürfen nicht im Repository oder Datenbanktext gespeichert werden
- Jede Schlüsselversion sollte aus einer sicheren Secret-Verwaltung bezogen werden
- Schlüssel sollten regelmäßig rotiert werden

## Schlüsselrotation

### Prozess
1. Neue Schlüsselversion in Konfiguration einfügen
2. Aktive Schlüsselversion auf neue Version ändern
3. Bestehende Dateien mit `scripts.rekey_document_storage` migrieren
4. Alte Schlüsselversionen entfernen (nach Migration)

### Migrationsskript
```bash
# Dry-Run zur Prüfung
python -m scripts.rekey_document_storage --dry-run

# Migration durchführen
python -m scripts.rekey_document_storage

# Migration mit spezifischer Schlüsselversion
python -m scripts.rekey_document_storage --key-version v2
```

### Sicherheitsmaßnahmen
- Migration ist atomar und fehler-resistant
- Integritätsprüfung aller verschlüsselten Dateien während der Migration
- Wiederherstellung bei Fehlern ist möglich
- Keine Datenlöschung oder Unlesbarkeit während der Migration

## Backup und Wiederherstellung

### Backup-Strategie
1. Datenbank-Backups inklusive Metadata
2. Dateisystem-Backups des Dokumentenspeichers
3. Schlüsselbackups in sicherer Secret-Verwaltung

### Wiederherstellungsprozess
1. Datenbank-Wiederherstellung
2. Dateisystem-Wiederherstellung
3. Schlüsselwiederherstellung aus Secret-Verwaltung
4. Validierung der Verschlüsselungskonfiguration

## Sicherheitsvorfälle

### Fehlende Schlüssel
- Im Produktionsmodus schlägt der Start bei fehlendem/ungültigem Schlüssel fehl
- Legacy-Klartext wird in Produktion nicht ausgeliefert
- Fehlermeldung: "Ein gültiger DOCUMENT_ENCRYPTION_ACTIVE_VERSION-Schlüssel ist erforderlich."

### Manipulierte Dateien
- Manipulierte Ciphertexts werden fail-closed abgewiesen
- Keine Klartext-Fallbacks für Produktionskonfiguration
- Fehlermeldung: "Die Authentifizierung des verschlüsselten Dokuments ist fehlgeschlagen."

## Tests

Alle Speicherlese-/Schreibpfade sind mit Tests abgedeckt:
- Verschlüsselung und Decryption
- Manipulation/Tagfehler
- Fehlende/falsche Schlüssel
- Upgrade/Rotation
- File-Permission-Verhalten

### Testausführung
```bash
cd backend
pytest tests/test_document_storage.py -v
```

## Produktionskonfiguration

### Sicherheitseinstellungen
- Im Produktionsmodus muss `DOCUMENT_ENCRYPTION_ACTIVE_VERSION` gültig sein
- Secure-Cookies werden erzwungen
- Redis wird für Rate-Limits verwendet
- Keine stille Klartext-Fallbacks

### Empfohlene Praktiken
1. Verwende separate Schlüssel für verschiedene Umgebungen
2. Implementiere regelmäßige Schlüsselrotation
3. Sichere Backup-Strategien für Schlüssel
4. Überwachung der Verschlüsselungskonfiguration
5. Teste Migrationen in einer Testumgebung vor der Produktion

## Fehlerbehandlung

### Häufige Fehler
- `DOCUMENT_ENCRYPTION_ACTIVE_VERSION` fehlt oder ist ungültig
- Schlüssel nicht in `DOCUMENT_ENCRYPTION_KEYS` konfiguriert
- Manipulierte Dateien oder Ciphertexts
- Fehlende Berechtigungen für Dateisystemoperationen

### Diagnose
- Prüfe Konfigurationsdateien
- Validiere Schlüsselstruktur
- Überprüfe Dateisystemberechtigungen
- Prüfe Protokolle für detaillierte Fehlermeldungen

## Compliance

### Datenschutz
- Alle Dateien werden serverseitig verschlüsselt
- Keine sensiblen Daten im Klartext gespeichert
- Authentifizierung aller Dateioperationen
- Audittrail für alle Dateioperationen

### Technische Sicherheit
- Verschlüsselung mit modernen Standards (AES-256-GCM)
- Authentifizierung aller Datenübertragungen
- Fail-closed-Design bei Sicherheitsfehlern
- Wiederherstellbarkeit bei Fehlern