# Datenbank

## Verbindung und Migrationen

PostgreSQL ist für den Betrieb vorgesehen. Laufzeitverbindungen verwenden `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER` und `POSTGRES_PASSWORD`; Compose setzt dafür ausschließlich `securityops_runtime`. Alembic verwendet `securityops_migrator`, der Datenbankadministrator `POSTGRES_ADMIN_USER` und `POSTGRES_ADMIN_PASSWORD`. Die drei Rollen haben getrennte Zugangsdaten. Die API und der Benachrichtigungs-Worker erhalten keine Administrator- oder Migrationszugangsdaten. Alembic-Migrationen liegen in `backend/migrations/versions`; normales Modell-Metadaten-`create_all` ist nur in Tests zulässig.

## Derzeitige Tabellen

- `customers`: Kundennummer, Firmenname, Status, Vertragsstatus, Kontakt-E-Mail/Telefon, Rechtsform, Website, Umsatzsteuer-ID, Steuernummer, interne Notizen, Archivierungs- sowie Erstellungs-/Änderungszeitpunkt.
- `customer_addresses`: Geschäfts- und Rechnungsanschriften eines Kunden; Kunden- und Adressdatensätze werden nicht physisch gelöscht.
- `customer_contacts`: Ansprechpartner mit Kontaktdaten und Primärkennzeichnung. Ein partieller eindeutiger Index erzwingt höchstens einen primären Ansprechpartner pro Kunde.
- `customer_history`: Kundenereignisse mit Akteur, Ereignis, Zeit und geänderten Feldnamen; keine Feldwerte.
- `objects`: eindeutiger Objektcode, Kunde (FK mit RESTRICT), Status, Betriebs-/Personalangaben sowie Archivierungs- und Zeitstempel.
- `object_addresses`: optionale 1:1-Anschrift; `object_contacts`: mehrere Ansprechpartner mit partiellem eindeutigem Index für höchstens einen Primärkontakt.
- `object_history`: Akteur, Aktion, Zeit und geänderte Feldnamen; sensible Werte werden nicht in der Historie gespeichert.
- `object_assignments`: eindeutige Objekt-/Benutzerzuweisung mit Zuordnungszeit und zuordnendem Benutzer.
- `object_security_details`: getrennte Tabelle für Sicherheitsanforderungen, Zutrittsinformation und Notfallkontakt.
- `employees`: Personalnummer, optionales eindeutiges Benutzerkonto, Stammdaten, Beschäftigungsstatus, Vertragsart, Wochenstunden und Archivierungszeitpunkt.
- `employee_qualifications`: Qualifikationsmetadaten und Gültigkeits-/Ablaufdaten; Qualifikationen werden archiviert statt physisch gelöscht.
- `employee_absences`: Abwesenheitstyp, Zeitraum, Status und erstellendes Benutzerkonto; Constraints sichern erlaubte Typen, Statuswerte und Datumsbereiche.
- `employee_sensitive_details`: getrennte Anschrift, Notfallkontakt und interne Notizen mit eigener Berechtigungsgrenze.
- `employee_history`: Akteur, Ereignis, Zeit und geänderte Feldnamen ohne sensible Feldwerte.
- `employee_object_assignment_history`: unveränderliche Personalhistorie für Zuweisung und Beendigung bestehender Objektzuweisungen; verweist auf Mitarbeiterakte, Objekt und Benutzer.
- `employee_qualification_documents`: unveränderliche Qualifikationsnachweis-Versionen mit Dateiinhalt in PostgreSQL (`BYTEA`), Medien-/Dateimetadaten, SHA-256-Prüfsumme, Versionsnummer und hochladendem Benutzer.
- `schedule_settings`: einzelne Dienstplankonfiguration mit IANA-Zeitzone und konfigurierbarer Mindestruhezeit in Stunden.
- `employee_availability_windows`: wöchentlich wiederkehrende lokale Zeitfenster je Mitarbeiter und Wochentag.
- `schedule_availability_requests`: lokale Zeitwünsche und explizite Sperrzeiträume als UTC-Intervalle mit Status, Antragsteller und prüfender Person.
- `schedule_shifts`: Mitarbeiter-/Objektzuordnung, UTC-Start/-Ende, Pause, optionale benötigte Qualifikation, Status und Akteure/Zeitstempel.
- `schedule_shift_history`: append-only Ereignisse mit Akteur, Zeitpunkt und geänderten Feldnamen; Vertretungsereignisse enthalten zusätzlich ursprüngliche/neue Mitarbeiter-ID und Grund.
- `time_entries`: Mitarbeiter, Objekt, optionaler veröffentlichter Dienst, UTC-Beginn/-Ende, Status, Ersteller, Einreichung und Freigabe-/Ablehnungsentscheidung. Eine Buchung je Mitarbeiter/Dienst und höchstens eine offene Buchung je Mitarbeiter.
- `time_entry_segments`: geordnete Arbeits- und Pausenabschnitte mit UTC-Zeitpunkten; Constraints begrenzen Segmenttyp, Reihenfolge und Zeitordnung, ein partieller eindeutiger Index erlaubt höchstens ein offenes Segment je Buchung.
- `time_entry_corrections` und `time_entry_correction_segments`: begründete Korrekturanträge samt Entscheider, Status und vollständigen vorgeschlagenen Segmenten. Ursprüngliche freigegebene Segmente bleiben erhalten; genehmigte Korrekturen bilden eine getrennte, historisierte Version.
- `time_entry_history`: append-only fachliche Ereignisse mit Akteur und Details für Start, Pause, Einreichung, Freigabe, Ablehnung, Korrekturantrag und Sperre.
- `time_tracking_settings`: Bundesland für den regionalen Feiertagskalender, ohne voreingestellten Standort.
- `time_surcharge_rules`: unveränderliche Zuschlagsregeln mit Kategorie, Gültigkeitszeitraum, Zeitfenster/Wochentagen, Prozent-/Festwert, Bezugsbeschreibung, Priorität und ausdrücklich gesetztem Kombinationsmodus.
- `time_surcharge_calculations`: versionierte Zuschlagszeit-Auswertung mit Quellsegmenten, Regel-/Ergebnis-Snapshot, Bundesland und Zeitzone. Zuschlagssekunden werden als exakte Dezimaltexte geführt; es wird kein Geldbetrag gespeichert oder berechnet.
- `time_tracking_periods`: endgültig gesperrte lokale Abrechnungszeiträume mit damaliger Zeitzone, Bundesland, sperrendem Benutzer und Zeitpunkt.
- `users`: Benutzername, E-Mail, Name, Argon2id-Passworthash, Aktivstatus und Zeitstempel.
- `roles`, `permissions`, `user_roles`, `role_permissions`: rollenbasierte Rechte.
- `user_sessions`: Hash des Sitzungstokens, CSRF-Tokenhash und Ablaufzeiten.
- `audit_logs`: Akteur, Ereignis, betroffener Datensatz, optionale Metadaten und UTC-Zeit.
- `audit_log_integrity`: SHA-256-Verkettung der Audit-Einträge; eine transaktionsgebundene PostgreSQL-Sperre ordnet auch gleichzeitig eintreffende Einträge eindeutig. Die Migration verkettet vorhandene Einträge, ohne sie zu ändern oder zu löschen. Der Laufzeitbenutzer darf Audit-Einträge lesen und einfügen, aber nicht ändern, löschen, truncaten, Trigger verwalten oder die Integritätstabelle lesen/schreiben.

## Zusätzliche Tabellen im offenen PR-Stack (nicht in `main`)

- `customer_portal_links`: manuelle Verknüpfungen zwischen genau einem Login und genau einem Kundenkontakt; eindeutige Constraints je Benutzer und Kontakt sowie Aktivierungsstatus.
- `customer_portal_link_history`: append-only Ereignisse für Verknüpfung, Aktivierung, Deaktivierung und Lösung mit Akteur und Zeitpunkt; ein Datenbanktrigger verhindert UPDATE/DELETE.
- `customer_portal_document_grants` und `customer_portal_document_grant_history`: ausdrückliche Kundenfreigaben einzelner aktueller Dokumentversionen mit Kundenbezug, Freigabe-/Widerrufsakteur und -zeit; Historie ist append-only.
- `customer_portal_requests`, `customer_portal_request_messages`, `customer_portal_request_attachments` und `customer_portal_request_history`: kundenbezogene Rückfragen/Beschwerden zu eigenen Objekten, Kundennachrichten, private Datei-Metadaten und append-only Verlauf.

## Integrität und offene Erweiterungen

UUIDs, Fremdschlüssel, eindeutige Benutzer-/Kundennummern und Status-Constraints sind vorhanden. Kunden, Objekte, Mitarbeiter und Qualifikationen werden archiviert statt physisch gelöscht; FK-Constraints schützen referenzierte Datensätze. Kontakte und Adressen sind relational gebunden. Migration 0008 ergänzt Personal, Qualifikationen, Abwesenheiten, getrennte sensible Personaldaten und Historie; Migration 0009 ergänzt den Verlauf bestehender Objektzuweisungen für Personalakten, versionierte Qualifikationsdateien und separate Dokumentrechte. Migration 0010 ergänzt Kunden-Website und Vertragsstatus. Migration 0011 ergänzt Scheduling-Einstellungen, Schichten und Historie. Migration 0012 ergänzt Zeiterfassung, Arbeits-/Pausensegmente, getrennte Korrekturversionen, Historie und Berechtigungen. Ein PostgreSQL-GiST-Exclusion-Constraint auf Mitarbeiter und halboffenem `tstzrange(starts_at, ends_at, '[)')` verhindert überschneidende nicht abgesagte Schichten auch bei konkurrierenden Transaktionen; dazu aktiviert die Migration `btree_gist`. Dienstplan-, Verfügbarkeits- und Zeiterfassungsänderungen sperren zusätzlich mit PostgreSQL-Transaktions-Advisory-Locks pro Mitarbeiter. Zeiterfassung verhindert über einen partiellen eindeutigen Index mehrere offene Buchungen pro Mitarbeiter und serialisiert Arbeitszeitüberschneidungsprüfungen. Dienstzeitpunkte und einmalige Wunsch-/Sperrzeiträume werden als `TIMESTAMPTZ` und UTC-normalisiert gespeichert; wiederkehrende Verfügbarkeiten sind lokale Wochentags-/Uhrzeitwerte. Lokale Tagesfilter und Anzeige verwenden die konfigurierte Dienstplan-IANA-Zeitzone. Soll-/Ist-Abweichungen gegenüber einem Dienstplan werden sekundengenau ausgewiesen.

Migration 0013 ergänzt Bundeslandseinstellung, Zuschlagsregeln, versionierte Berechnungsnachweise und Abrechnungsperiodensperren sowie getrennte Lese-/Verwaltungs-/Sperrrechte. Berechnungs-Snapshots behalten Regelwerte und effektive Arbeitssegmente bei; spätere Regel- oder Bundeslandänderungen verändern sie nicht. Periodensperren sind append-only und endgültig.

Migration 0014 (`0013_time_tracking_surcharges` → `0014_owks_wachbuch`) ergänzt OWKS-Kontrollpunkte mit gehashten QR-/NFC-Kennungen, Routen, kurzlebige benutzergebundene Scan-Challenges, append-only Wachbuchereignisse und Statusverläufe sowie sichere Anhänge. Statische Kennungstreffer bleiben ausdrücklich unbestätigt und zählen nicht als erledigter Routenbesuch. PostgreSQL-Trigger schützen Ereignisse, Statushistorie und Anhänge vor UPDATE/DELETE; Downgrade wird abgelehnt, sobald OWKS-Tabellen Daten enthalten.

Migration 0015 (`0014_owks_wachbuch` → `0015_documents_contracts`) ergänzt Dokumente, unveränderliche Datei-Versionen, Freigaben, Lesebestätigungen, Dokumenthistorie, Verträge und Vertragschronik sowie konfigurierte Ablauf-/Kündigungs-/Verlängerungserinnerungen. Dokument-/Vertragsdaten bleiben relational geschützt; private Binärdateien liegen im persistenten, nicht öffentlich bereitgestellten Docker-Volume. Die Migration verwendet die bereits vorhandene `documents.read`-Berechtigung und fügt weitere Berechtigungen/Rollenzuordnungen konfliktfrei hinzu.

Der Downgrade von 0015 prüft vor dem Abbau alle Dokument-/Vertragstabellen auf Inhalte und lehnt den Rückbau mit einer verständlichen Fehlermeldung ab, wenn Fachdaten oder angepasste Erinnerungseinstellungen vorhanden sind. Dadurch entfernt das automatische Tabellen-Dropping keine solchen Daten. Nur unbenutzte leere Feature-Tabellen und die unveränderte Standard-Vorlaufzeit dürfen zurückgebaut werden. Binärdateien im privaten Volume werden durch die Datenbankmigration nicht gelöscht; ihre Aufbewahrung bleibt separat zu verwalten.

Migration 0016 ergänzt regelmäßige Mitarbeiterverfügbarkeiten, einmalige Dienstwunsch-/Sperrzeiträume, das Recht `scheduling.availability.request` für eigene Meldungen sowie Vorher-/Nachher-Angaben für Vertretungen in der Schichthistorie. Der Downgrade wird abgelehnt, sobald Verfügbarkeitsdaten, Anträge oder Vertretungsdetails gespeichert sind.

Migration 0029 (`0028_customer_portal_requests` → `0029_audit_integrity`) schützt `audit_logs` und `audit_log_integrity` mit PostgreSQL-Triggern vor UPDATE/DELETE. Der Audit-Akteur wird als historische UUID ohne Fremdschlüssel gespeichert, damit das spätere Entfernen eines Benutzerkontos keinen alten Audit-Eintrag verändert. Ein Hash bildet alle Audit-Felder und den vorherigen Hash ab; advisory locks serialisieren konkurrierende Inserts in derselben Transaktion. `python -m scripts.verify_audit_integrity` validiert Vollständigkeit, Verknüpfungen und Hashwerte und gibt Anzahl sowie SHA-256-Kettenende als extern speicherbaren Prüfpunkt aus. Die Kette allein schützt nicht vor Datenbank-Ownern oder Superusern: Sie können Trigger/Funktionen ändern oder Daten samt Kette neu berechnen. Dafür müssen verschlüsselte Datenbank-Backups und Prüfpunkt getrennt, zugriffsbeschränkt und möglichst unveränderlich außerhalb des Datenbankhosts aufbewahrt und regelmäßig in einer isolierten Umgebung verifiziert/restauriert werden. Der Downgrade wird abgelehnt, solange Audit-Daten vorhanden sind.

Das einmalige/idempotente `python -m scripts.provision_database_roles` wird vor Migrationen mit einem PostgreSQL-Superuser ausgeführt. Es erzeugt `securityops_migrator` und `securityops_runtime` ohne Superuser-, Rollen- oder Datenbank-Erstellungsrechte, überträgt das Eigentum bestehender Schemaobjekte an den Migrationsbenutzer und gewährt dem Laufzeitbenutzer nur benötigte Objekt- und DML-Rechte. Das Übertragen ändert keine Tabelleninhalte. Der Migrationsbenutzer ist Datenbankeigentümer und kann DDL sowie Datenänderungen ausführen; der Administrator bleibt privilegiert. Rollen-/Passwortänderungen und Backup-/Restore müssen daher getrennt kontrolliert werden.

Im offenen PR-Stack, nicht im gemergten `main`, verhindert Migration `0025_unique_incident_owks_event` doppelte Vorfallverknüpfungen zu OWKS-Ereignissen. Migration `0026_customer_portal_access` folgt darauf, ergänzt Verknüpfung und append-only Historie sowie `customer_portal.access` und `customers.portal.manage` und weist das Verwaltungsrecht der Administrator-Rolle zu. `0027_customer_document_grants` ergänzt das Aktivierungskennzeichen für Portalzugänge, Aktivierungsereignisse und explizite Dokumentfreigaben samt append-only Freigabehistorie; das Verwaltungsrecht `customer_portal.documents.manage` erhält nur die Administrator-Rolle. `0028_customer_portal_requests` ergänzt Kundenanfragen zu Kundenobjekten, append-only Nachrichten/Verlauf, private Anhang-Metadaten und das nur Administratoren zugewiesene `customer_portal.requests.manage`. Der Datenzugriff bleibt an den aktuell verknüpften Kundenkontakt gebunden.

Jede Schemaänderung benötigt eine neue Alembic-Migration. Datenlöschungen müssen mit Aufbewahrungsregeln abgestimmt werden; produktive Downgrades mit Datenverlust dürfen nicht automatisch ausgeführt werden. Eine automatische Zuschlagsabrechnung in Geld ist mangels bestätigter Lohnbasis, Festzuschlagseinheit und Rundung nicht implementiert.
