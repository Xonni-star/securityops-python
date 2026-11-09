# SecurityOps – Repository-Audit

Grundlage ist `main` nach dem Merge von PR #16 sowie der Feature-Branch `feature/personnel-management` mit Draft-PR #17. Die Objektverwaltung ist in `main`; Personaländerungen wurden durch CI mit PostgreSQL-Migrationen/-Tests sowie Frontend- und Docker-Builds geprüft.

## Bestand

| Bereich/Funktion | Status | Tatsächlicher Stand |
|---|---|---|
| Backend-Struktur | TEILWEISE | Ein FastAPI-Monolith mit `api.py`, `identity_api.py`, `auth.py`, zentralen SQLAlchemy-Modellen und Konfiguration. Noch keine fachlichen Modulgrenzen für Objekte, Personal, Planung, OWKS, Dokumente oder Abrechnung. |
| Frontend | TEILWEISE | React-Oberfläche mit Produktionsbuild als statische Dateien, die Nginx ausliefert; Entwicklungsserver nur im lokalen Entwicklungsworkflow. CI prüft die Produktionscontainer und Sicherheitsheader. Keine E2E-Tests. |
| PostgreSQL/ORM | TEILWEISE | SQLAlchemy-Modelle und neun Migrationen. Migrationen 0005–0007 ergänzen Objekte; 0008 Personal/Qualifikationen; 0009 Zuweisungsverlauf und versionierte Qualifikationsdateien. Lokale API-Tests laufen auf SQLite; PostgreSQL-CI muss die aktuelle Revision 0009 noch prüfen. |
| Alembic | TEILWEISE | Explizite Migrationen vorhanden. Upgrade bis 0009 und Downgrade 0009→0008 lokal offline gerendert; ein echter PostgreSQL-Lauf für die aktuellen Änderungen steht aus. |
| Anmeldung | TEILWEISE | Benutzername/Passwort, Argon2id, serverseitig widerrufbare opaque Sitzung, generische Fehlermeldung. MFA und Passwortzurücksetzung fehlen. |
| Sitzungen/CSRF | TEILWEISE | HttpOnly-Sitzungscookie, CSRF-Cookie/Header-Abgleich, SameSite=Strict, Idle-/Absolute-Timeout, Logout und Widerruf beim Passwortwechsel. Keine Sitzungsübersicht oder gezielte Einzelwiderruf-UI. |
| Rate-Limit | TEILWEISE | Produktion verwendet den gemeinsamen Redis-Speicher; die Readiness-Prüfung schlägt bei Redis-Ausfall fehl. Lokale direkte Starts ohne Redis bleiben prozesslokal. Trusted-Proxy-Adressen müssen für die konkrete Infrastruktur konfiguriert werden. |
| RBAC | TEILWEISE | Backend prüft Modulrechte sowie Objektzuweisung oder globale Objektberechtigungen. Sensitive Objekt- und Personaldaten sowie Abwesenheiten haben eigene Rechte. Kein Rolleneditor. Administratorrollenvergabe bleibt auf `users.manage_admin` beschränkt. |
| Benutzerverwaltung | TEILWEISE | Benutzer anlegen/listen/aktivieren/deaktivieren, Rollen zuweisen. Kein Rollen-/Rechteeditor, Einladungs- oder Passwortzurücksetzungsablauf. |
| Audit | TEILWEISE | Anmeldung, fehlgeschlagene Anmeldung, Passwortwechsel, Benutzer- und Kundenänderungen werden geloggt. Keine Änderungen/Löschungen über die Anwendungs-API; kein Schutz vor direkten privilegierten Datenbankänderungen, keine Vollständigkeit über noch nicht implementierte Module. |
| Kunden | TEILWEISE | Anlage, Suche, Filter/Sortierung, UUID-Detailabruf/-änderung, Geschäfts-/Rechnungsanschriften, Ansprechpartner mit Primärkontakt, Archivierung/Reaktivierung und Historie sind implementiert. Die Objektbeziehung ist vorhanden; Vertrags- und Dokumentzuordnung fehlen. Kunden werden archiviert statt physisch gelöscht. |
| Objekte | TEILWEISE / BRANCH | Backend, API, React-Oberfläche und Migrationen 0005–0007: Kunde-FK, Suche/Filter/Sortierung/Paginierung, Detailbearbeitung, Adresse, mehrere einzelne Ansprechpartner, Archivierung, Historie, Zuweisungen sowie separate Sicherheitsdaten. Zugriff wird serverseitig kontrolliert. Zuweisungen binden an aktive Konten mit Mitarbeiter-/Objektleitungsrolle, nicht an Personalakten. PostgreSQL-CI, Docker-Builds und Review dieses Branches ausstehend. |
| Personal | TEILWEISE / BRANCH | Migrationen 0008–0009, Personalakten, Qualifikationen und Ablaufübersicht, Abwesenheiten, getrennte sensible Daten, Historie, Zuweisungen über bestehende Benutzerkonten, versionierte Qualifikationsdateien, API und React-Oberfläche sind implementiert. Dateiinhalte liegen in PostgreSQL; PostgreSQL-CI und Review der aktuellen Änderungen stehen aus. |
| Dienstplanung | FEHLT | Keine Dienste, Zuweisungen, Konflikt- oder Arbeitszeitprüfung. |
| Zeiterfassung | FEHLT | Keine Zeitbuchungen, Korrekturfreigaben oder Abrechnungsschnittstelle. |
| OWKS/Kontrollen | FEHLT | Keine Wachbucheinträge, Kontrollpunkte, QR-/NFC-Validierung oder Offline-Warteschlange. |
| Dokumente/Verträge/Rechnungen | FEHLT | Kein Dateiablage-, Vertrags- oder Rechnungsmodell. |
| Dashboard | TEILWEISE | Kundenanzahl, aktive Kunden und Interessenten werden aus der Datenbank gezählt; operative Kennzahlen fehlen. |
| Docker/Deployment | TEILWEISE | Produktions-Compose liefert ein statisches Nginx-Frontend aus; Migrationen laufen als expliziter Release-Job, Redis ist gemeinsamer Rate-Limit-Speicher. Dokumentierte TLS-Proxy-Voraussetzungen, Security-Header und verschlüsselte Backup-/Restore-Verfahren. Keine produktive Betreiberumgebung eingerichtet. |
| Tests | TEILWEISE | CI prüft vollständige Alembic-Migrationen und Backend-/API-Tests auf PostgreSQL 17, Redis-Rate-Limits, Produktionscontainer, Docker-Builds und einen verschlüsselten Restore mit synthetischen Daten. Das belegt keine E2E-, Last- oder Betreiberprüfung. |

## Fehler und Risiken

### Behoben in der aktuellen Phase

- **HOCH – fehlende Objektzuweisungsprüfung:** Vorherige Prüfung ergab, dass Endpunkte mit Modulrechten fremde Objekte hätten lesen oder ändern können. PR #16 ergänzt serverseitige Zuweisungsprüfungen und Negativtests für Listen, Details, Historie und Änderungen; CI für PR #16 war erfolgreich.
- **HOCH – sensible Zutrittsdaten in normalen Objektantworten:** Sicherheits-, Zutritts- und Notfallangaben werden aus Standardlisten/-details entfernt, in eigene Tabelle migriert und über gesonderte Rechte/Endpunkte geschützt. Negativtests prüfen Trennung und Verlauf ohne Werte; PR #16 wurde mit erfolgreicher CI gemergt.
- **FEHLERHAFT – Rechteausweitung über Benutzerverwaltung:** Die Geschäftsführungsrolle hatte `users.manage`, und die Benutzeranlage nahm beliebige vorhandene Rollen an. Damit hätte sie Administratorrechte vergeben können. Die neue additive Migration trennt `users.manage_admin` ab; Create und Update kontrollieren dieses Recht serverseitig. Ein Regressionstest deckt die Ablehnung ab.
- **SICHERHEIT – unsichere implizite Cookie-Standardeinstellung:** Compose setzte `SESSION_COOKIE_SECURE` standardmäßig auf `false`. Jetzt ist der Compose-Fallback `true`; die lokale `.env.example` setzt für lokales HTTP ausdrücklich `false`.
- **SICHERHEIT – implizites Datenbankpasswort:** Anwendungskonfiguration verlangte kein explizit gesetztes Datenbankpasswort. Sie verlangt jetzt `POSTGRES_PASSWORD`; der Testaufbau setzt einen ausschließlich für Tests bestimmten Wert.

### Offen

- **Betriebsprüfung offen:** Der Produktions-Rate-Limiter nutzt gemeinsames Redis; der In-Memory-Speicher bleibt lokalen Entwicklungsstarts vorbehalten. Tatsächliche Proxy-Adressen und TLS-Topologie sind Betreiberkonfiguration.
- **Betriebsprüfung offen:** Produktionsfrontend wird statisch über Nginx ausgeliefert. TLS-Zertifikate, DNS, Reverse-Proxy-Topologie und deren vertrauenswürdige Client-IP-Weitergabe müssen Betreiber einrichten und testen.
- **Sicherheits-/Betriebsrisiko:** Der Audit-Datensatz ist nur über die App-API schreibgeschützt. Datenbankbesitzer oder Administratoren können die Tabelle ändern; Append-only-Berechtigungen/externes unveränderliches Archiv fehlen.
- **Betriebsprüfung offen:** Migrationen laufen als expliziter Release-Job vor dem API-Rollout. Ein erfolgreicher CI-Migrationslauf ersetzt keine Prüfung des eigenen Upgrade-/Rollback-Verfahrens.
- **Datenbanklücke:** Kundenstammdaten sind erweitert; die Kundennummer bleibt ein eindeutiger zufälliger UUID-basierter Identifikator statt einer fortlaufenden Nummer. Kunden- und Objekthistorien enthalten nur geänderte Feldnamen, keine Vorher-/Nachher-Werte.
- **RBAC-Lücke:** Standardrollen und Rechte werden derzeit nur durch Migration initialisiert. Rollenverwaltung in der Oberfläche/API fehlt; Administratorzuweisungen werden durch die laufende Phase separat geschützt.
- **Integrationslücke:** Lokale Tests verwenden SQLite. Gehostete CI deckt Migrationen und API-Tests gegen PostgreSQL ab; systematische Schema-Differenzprüfung und weitere Datenbanktests bleiben offen.
- **Qualitätssicherung:** GitHub Actions prüft PostgreSQL-Integration und Docker-Builds; SCA und CodeQL laufen in einer separaten Security-Workflowdatei. Produktive Betriebsprüfung bleibt ausstehend.
- Historische Auditbeobachtungen spiegeln teilweise einen früheren Repository-Stand wider. Für den aktuellen Deployment- und Backup-Stand gelten [Deployment](DEPLOYMENT.md), [Backup und Wiederherstellung](BACKUP_RESTORE.md) sowie [Security-Review](SECURITY_REVIEW.md).

## Datenbankbeobachtungen

- UUID-Primärschlüssel, Fremdschlüssel, Status-Constraints und Zeitstempel sind in Grundtabellen vorhanden.
- Benutzerrollen und Rollenberechtigungen sind Many-to-many verknüpft; Löschregeln sind überwiegend `CASCADE`. Kunden werden derzeit nicht physisch über eine API gelöscht.
- `UserSession.token_hash` ist eindeutig; absolute und gleitende Fristen sind gespeichert.
- `AuditLog.details` ist JSON; es gibt keine Datenbankregel, die Updates/Deletes für die Laufzeitrolle verhindert.
- Modell- und Migrationsdefinitionen müssen weiter gegen echte PostgreSQL-Instanzen geprüft werden.

## Architekturbeobachtungen

- Ein modularer Monolith ist für den aktuellen Umfang angemessen.
- Fachmodule sind noch nicht aus dem API-/Modellkern extrahiert; beim Wachstum sollten Domänen und Zugriffsgrenzen getrennt werden.
- Die Oberfläche ruft die API zentral über `api.ts` auf, hat aber noch kein Router-/Feature-Modul-Layout.
- Produktive Frontend-Auslieferung, Reverse Proxy, zentrale Secrets-/Rate-Limit-Verwaltung und Monitoring fehlen.

## Empfohlene Entwicklungsreihenfolge

1. Phase 1 abschließen: PostgreSQL-Integrationslauf und reproduzierbare Deployment-Prüfung ([#9](https://github.com/Xonni-star/securityops-python/issues/9)).
2. Kundenverwaltung fachlich prüfen und Vertrags-/Dokumentzuordnung planen ([#6](https://github.com/Xonni-star/securityops-python/issues/6)).
3. Personalverwaltungs-Branch gegen PostgreSQL, Docker und CI prüfen und danach Issue #5 anhand aller Akzeptanzkriterien bewerten.
4. Die neue Personalzuweisungs- und Dokumentfunktion gegen PostgreSQL prüfen und Issue #5 anhand aller Akzeptanzkriterien bewerten ([#5](https://github.com/Xonni-star/securityops-python/issues/5)).
5. Dienstplanung mit Konflikt-/Qualifikationsprüfungen ([#10](https://github.com/Xonni-star/securityops-python/issues/10)), danach Zeiterfassung/Freigaben ([#4](https://github.com/Xonni-star/securityops-python/issues/4)).
6. OWKS und manipulationsnachweisbare Kontrollereignisse ([#3](https://github.com/Xonni-star/securityops-python/issues/3)).
7. Dokumente, Verträge und Fristüberwachung ([#8](https://github.com/Xonni-star/securityops-python/issues/8)).
8. Rechnungswesen mit versionierten, nach Freigabe nicht überschreibbaren Rechnungen ([#7](https://github.com/Xonni-star/securityops-python/issues/7)).
9. Dashboard, E2E-/PostgreSQL-/Backup-Tests, Härtung und produktionsfähiges Deployment ([#9](https://github.com/Xonni-star/securityops-python/issues/9)).

## Prüfbelege

- Objektverwaltung PR #16: in `main` gemergt; die CI nach den Korrekturen war erfolgreich.
- Personalverwaltungs-Branch: 18 Backendtests, Ruff-Lint/Format und Frontend-TypeScript-/Produktionsbuild lokal bestanden; PR #17 CI bestätigt PostgreSQL-Migrationen/-Tests und Docker-Builds.
- Lokales PostgreSQL und Docker waren in der Entwicklungsumgebung nicht verfügbar; gehostete CI für den aktuellen Branch ist erfolgreich.
- Der GitHub-Actions-Lauf mit kurzlebigem PostgreSQL, Frontend-Build und Docker-Images war nach Behebung der Test-Fixture erfolgreich.
