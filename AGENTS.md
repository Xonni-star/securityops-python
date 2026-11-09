# Arbeitsanweisungen für KI-Agenten

## Projektziel und Umfang

SecurityOps ist eine deutschsprachige Verwaltungsplattform für einen Sicherheitsdienst. Ziel ist ein modularer Monolith mit Python/FastAPI, SQLAlchemy, PostgreSQL, Alembic sowie React/TypeScript. Der belegte `main`-Stand umfasst Identity/RBAC mit optionalem TOTP-MFA und Sitzungsverwaltung, Kunden, Objekte, Personal/Qualifikationen, Dienstplanung, Zeiterfassung einschließlich Zuschlagszeitnachweisen, OWKS, Dokumente/Verträge und Rechnungswesen. Offene Pull Requests sind kein Teil von `main` und dürfen in Statusaussagen nicht als integriert dargestellt werden.

## Verbindliche Arbeitsweise

- Benutzeroberfläche, Fehlermeldungen und Dokumentation sind auf Deutsch.
- Geschäftslogik, Eingabevalidierung und Berechtigungsprüfungen gehören ins Backend; Frontend-Prüfungen ersetzen keine serverseitigen Kontrollen.
- Datenbankänderungen erfolgen ausschließlich über Alembic-Migrationen. Modelle, Schemas, API und Migrationen müssen zusammenpassen.
- Geschäftskritische Änderungen müssen transaktional und nachvollziehbar sein. Wachbuch-, Zeit- und Abrechnungsdaten nicht stillschweigend überschreiben; Korrekturen müssen versioniert und begründet sein.
- Geldbeträge benötigen fachlich bestätigte Rechenregeln und `Decimal`/`NUMERIC`; Zeitpunkte werden UTC gespeichert. Lokale Dienstzeiten müssen eine IANA-Zeitzone und DST-Fälle berücksichtigen.
- Geheimnisse gehören in Umgebungsvariablen oder einen verwalteten Secret Store, nie in Quellcode, Git oder Container-Images.
- Keine echten Kunden-, Personal- oder Einsatzdaten in Tests, Beispielen oder Logs.
- Änderungen bleiben eng am Auftrag. Keine Fachmodule, Datenfelder oder externen Dienste ohne fachlichen Grund ergänzen.
- Tests für geändertes Verhalten ergänzen und passende Backend-Tests sowie Frontend-Build/Tests ausführen.

## Berechtigungen und Datenschutz

- Keine geschützte API ohne serverseitige Authentifizierung und Autorisierung nach außen freigeben.
- Zugriffe sind nach Rolle und bei operativen Daten zusätzlich nach Objekt-/Personalbereich zu prüfen; Daten aus fremden Scopes dürfen auch in Listen und Aggregaten nicht durchsickern.
- Sensible Objekt- und Personaldaten sowie Dateien ausschließlich über separat autorisierte Backend-Endpunkte bereitstellen.
- Audit- und Änderungshistorien nicht mit vertraulichen Feldwerten befüllen; die aktuelle Anwendungshistorie ist nicht gegen privilegierte direkte Datenbankänderungen gesichert.
- Uploads benötigen serverseitige Größen-/Typprüfung, fail-closed Malware-Scan und autorisierten Abruf. Der Scan neuer Dateien bestätigt weder den bereits gespeicherten Bestand noch eine vollständige Erkennung oder Produktionssicherheit.

## Dokumentations- und Statusregeln

- `docs/PROJECT_STATUS.md` ist die maßgebliche Momentaufnahme. Trenne dort ausdrücklich den tatsächlich gemergten `main`-Stand, offene PRs, CI-Nachweise und fachliche Abnahmen.
- PR-, Issue-, CI- und Merge-Status vor einer Aktualisierung frisch prüfen. Eine grüne CI ist kein fachlicher, rechtlicher oder produktiver Nachweis.
- Datenbank- und API-Dokumentation aus den Alembic-Migrationen, SQLAlchemy-Modellen, registrierten Routern/OpenAPI und Endpunktprüfungen ableiten; keine Tabellen, Rechte, Fehlerverhalten oder Produktionsmaßnahmen erfinden.
- Keine Produktionsreife oder Rechts-/Steuerkonformität behaupten, sofern sie nicht konkret umgesetzt und unabhängig geprüft wurde.
- Markdown-Links und Mermaid-Blöcke bei Dokumentationsänderungen lokal prüfen; keine Runtime-Abhängigkeiten allein für Dokumentationsprüfungen hinzufügen.

## Ausbau und Betrieb

Die fachliche Reihenfolge richtet sich nach echten Daten- und Berechtigungsabhängigkeiten: Kunden → Objekte → Personal/Qualifikationen → Dienstplanung → Zeiterfassung/OWKS → Dokumente/Verträge → Abrechnung. Der generische Aufgaben-Kern ist implementiert, aber nicht automatisch mit Fachmodulen verknüpft; keine Folgeintegration ohne abgestimmte Ereignis-/Transaktions- und Berechtigungsregeln ergänzen. Die im Repository offenen Abnahmen und Maßnahmen sind in [`docs/IMPLEMENTATION_ROADMAP.md`](docs/IMPLEMENTATION_ROADMAP.md) priorisiert. MFA/Sitzungsverwaltung, ClamAV-Uploadscan und Rechnungswesen sind implementiert, aber unabhängig sicherheits- bzw. fachlich zu prüfen; Uploads werden nicht rückwirkend geprüft. Nutzerinitiierter E-Mail-Passwortreset ist nicht vorhanden. Vor produktivem Betrieb sind mindestens RBAC-/Auditprüfung, TLS, Schutz der Uploads, Backup/Restore, Monitoring, Incident-Abläufe und Datenschutz-/Aufbewahrungsvorgaben zu klären und nachzuweisen.
