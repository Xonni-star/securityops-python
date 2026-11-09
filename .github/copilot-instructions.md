# Hinweise für GitHub Copilot

SecurityOps ist ein deutschsprachiger modularer Monolith für Sicherheitsdienste: FastAPI/Python, SQLAlchemy, PostgreSQL/Alembic und React/TypeScript mit Vite. Der konkrete Funktions- und Betriebsstand ist in `docs/PROJECT_STATUS.md` dokumentiert. `AGENTS.md` enthält die maßgeblichen, ausführlicheren Projekt-, Sicherheits-, Datenschutz- und Fachregeln; beachte sie, statt sie hier zu duplizieren. Prüfe bei Statusaussagen den tatsächlichen Branch und aktuelle GitHub-Daten: offene PRs sind nicht Teil von `main`.

## Aufbau und Konventionen

- Backend: `backend/app/main.py` registriert API-Router; Fachendpunkte liegen in den jeweiligen `*_api.py`-Dateien, Pydantic-Modelle/Schemas in `*_schemas.py`, SQLAlchemy-Modelle in `models.py`. Tests liegen in `backend/tests/`; Alembic-Konfiguration, Migrationen und Hilfsskripte in `backend/alembic.ini`, `backend/migrations/` und `backend/scripts/`.
- Frontend: `frontend/src/` enthält React-/TypeScript-Oberflächen nach Fachbereich sowie `api.ts`, `types.ts` und Styles. TypeScript ist strikt konfiguriert; halte Komponenten, API-Aufrufe und Typen konsistent und folge bestehenden Mustern. Verwende die npm-Skripte aus `frontend/package.json`.
- Dokumentation: `docs/` enthält Architektur, API, Datenbank, Sicherheit, Betrieb, Projektstatus und Roadmap. Aktualisiere die direkt betroffene Dokumentation und leite Aussagen zu API und Datenbank aus registrierten Routern, Modellen und Migrationen ab.
- `.github/agents/*.agent.md` enthält benutzerdefinierte Agenten im offiziellen Format für GitHub Copilot Cloud und unterstützte IDEs wie VS Code. `.github/prompts/*.prompt.md` sind manuell aufrufbare VS-Code-Prompts für den Local-Harness; Copilot Cloud und die Copilot-App führen diese Prompt-Dateien nicht aus.
- Ergänzende bereichsspezifische Hinweise liegen in `.github/instructions/`: Backend, Frontend, PostgreSQL, Alembic-Migrationen, Tests, Sicherheit, Docker, Deployment und Dokumentation. GitHub dokumentiert Pfad-Anweisungen für VS Code, Copilot Cloud und Copilot Code Review; für die Copilot-App wird keine Unterstützung behauptet.
- Spezialisierte Agenten liegen in `.github/agents/` (Backend, Frontend, Datenbank, QA, DevOps, Dokumentation, Projektprüfung und Sicherheitsprüfung). Ihr Frontmatter folgt dem offiziellen Agentenformat; die verfügbaren Tools sind je nach Änderungstätigkeit begrenzt. Copilot-App-Unterstützung ist nicht zugesichert.
- Zwölf wiederverwendbare VS-Code-Local-Prompts liegen in `.github/prompts/`. Sie sind keine Cloud-Agent-Aufträge und werden in der Copilot-App nicht als Prompt-Dateien ausgeführt. Eine Auswahl eines benannten Agenten in einem Prompt setzt voraus, dass dieser Agent im Local-Harness verfügbar ist.
- Formate und Oberflächen: [Repository- und Pfad-Anweisungen](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/add-custom-instructions/add-repository-instructions), [Unterstützung je Oberfläche](https://docs.github.com/en/copilot/reference/custom-instructions-support), [benutzerdefinierte Agenten](https://docs.github.com/en/copilot/reference/custom-agents-configuration) und [VS-Code-Prompt-Dateien](https://code.visualstudio.com/docs/agent-customization/prompt-files). Diese Quellen belegen keine Ausführung der Prompt-Dateien in Copilot Cloud oder Copilot App.
- Ändere nur den beauftragten Umfang und erhalte bestehendes Verhalten. Ergänze Tests für geänderte Funktionalität. Benutzeroberfläche, Fehlermeldungen und Dokumentation sind auf Deutsch.

## Backend, Daten und Sicherheit

- Geschäftslogik, Eingabevalidierung und Authentifizierung/Autorisierung gehören ins Backend. Jede geschützte Route muss Berechtigungen serverseitig prüfen; bei operativen Daten zusätzlich Objekt- und Personalbereich. Wende dieselben Grenzen auf Listen, Aggregate, Exporte und Dateiabrufe an. Frontend-Sichtbarkeit ist keine Zugriffskontrolle.
- Schemaänderungen erfolgen ausschließlich als Alembic-Migration und müssen mit Modellen, Schemas und API zusammenpassen. Geschäftskritische Änderungen transaktional und nachvollziehbar umsetzen; Wachbuch-, Zeit- und Abrechnungsdaten nicht still überschreiben.
- Zeitpunkte in UTC speichern; lokale Dienstzeiten mit IANA-Zeitzone und DST-Fällen behandeln. Geldbeträge als `Decimal`/`NUMERIC`; keine unbestätigten Tarif-, Steuer- oder Rundungsregeln erfinden.
- Keine Secrets, echten Personen-/Kunden-/Einsatzdaten oder produktiven Daten in Code, Git, Tests oder Logs. Upload-Prüfungen müssen serverseitig und fail-closed bleiben; ein Scan neuer Dateien belegt weder die Prüfung des Bestands noch vollständige Erkennung oder Produktionssicherheit.

## Prüfen

Die folgenden Befehle entsprechen den Projektkonfigurationen und den Schritten in `.github/workflows/ci.yml`. Backend-Befehle aus `backend/`, Frontend-Befehle aus `frontend/` ausführen:

```sh
# backend
python -m pip install -e ".[test,quality]"
ruff check app tests migrations scripts
ruff format --check app tests migrations scripts
python -m pytest -q

# frontend
npm ci
npm run build
npm test
```

`npm run build` führt TypeScript-Prüfung und Vite-Produktionsbuild aus. Die CI prüft zusätzlich Alembic/PostgreSQL 17, Redis-Integration, Container sowie isolierten Backup/Restore und Sicherheitsanalysen; dafür nötige Dienste und Schritte stehen im Workflow. Behaupte diese CI-Nachweise nicht aufgrund lokaler Teilprüfungen. Führe für Änderungen die kleinsten passenden Prüfungen aus und nenne ausgelassene Checks offen. Es gibt im Frontend-Paket kein separates Lint-Skript.

## Änderungen und Freigaben

Arbeite auf einem Feature-Branch, prüfe Zielbranch und aktuelle Änderungen vor dem PR und überschreibe oder bereinige keine fremden Änderungen. PRs sind gegen `main` zu richten und sollen Umfang sowie tatsächlich ausgeführte Prüfungen nennen. Merge oder Deployment nur auf ausdrückliche Autorisierung. Dokumentation darf weder Produktionsreife noch fachliche, steuerliche, rechtliche oder betriebliche Freigaben behaupten, sofern diese nicht konkret umgesetzt und unabhängig nachgewiesen sind. Eine grüne CI ist kein solcher Nachweis.
