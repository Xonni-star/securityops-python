# Globale Suche

Die globale Suche ist ein migrationsfreier MVP unter `GET /api/v1/search`. Sie durchsucht ausschließlich Kunden und Objekte. Ein Treffer enthält nur ID, Typ, Titel und Referenz; Kontaktdaten, Anschriften, Notizen, Beschreibungen, Sicherheitsdaten und Dateiinhalte werden weder als Suchfelder verwendet noch ausgegeben.

## Berechtigungen und Scope

- Kunden werden nur mit `customers.read` und ohne archivierte Datensätze durchsucht.
- Objekte werden nur mit `objects.read` und ohne archivierte Datensätze durchsucht. `objects.read_all` erlaubt die globale Suche; sonst muss eine aktive Objektzuweisung zum angemeldeten Benutzer bestehen.
- Ein Typfilter (`type=customer` oder `type=object`) schränkt die Suche ein. Nicht erlaubte Typen liefern keine Treffer. Fehlt für beide Typen das Leserecht, antwortet der Endpunkt mit `403`.
- Beim Öffnen eines Treffers lädt das jeweilige Fachmodul die Detailansicht erneut über seinen geschützten Endpunkt. Die Suchantwort ist keine Berechtigung für Detaildaten.

## Anfrage und Sortierung

`q` ist erforderlich und wird nach dem Entfernen äußerer Leerzeichen auf 2 bis 100 Zeichen begrenzt. `limit` ist 1 bis 50 (Standard 20), `offset` 0 bis 5000 (Standard 0). Die Antwort enthält `items`, `total`, `limit` und `offset`.

Exakte Titel-/Referenztreffer stehen vor Präfix- und Teiltreffern; danach wird stabil nach Titel, Typ, Referenz und ID sortiert. `%`, `_` und `\\` in der Eingabe werden als Suchzeichen und nicht als SQL-Wildcards behandelt. Die Oberfläche wartet 250 ms nach der letzten Eingabe und lädt Treffer seitenweise.

## Bewusste Grenzen

Mitarbeiter, Dokumente, Verträge, Schichten, Aufgaben, Vorfälle/Beschwerden, Schlüssel/Inventar, Rechnungen und Wachbucheinträge erscheinen nicht in dieser Suche. Bei ihnen können selbst Titel personenbezogene, finanzielle, operative oder vertrauliche Informationen enthalten; die jeweilige Scope-Prüfung reicht für eine zusätzliche, minimierte globale Antwort nicht aus. Weitere Suchquellen benötigen eine eigene Prüfung von Leserecht, Kunden-/Objektbereich und sicherem Ergebnisfeld. Es gibt keinen Suchindex, keine externe Suche und keine Datenbankmigration.
