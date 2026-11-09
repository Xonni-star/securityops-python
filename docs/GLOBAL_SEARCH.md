# Globale Suche

Die globale Suche ist migrationsfrei unter `GET /api/v1/search` verfügbar. Sie durchsucht Kunden, Objekte, Personalnummern, Dokumente, Verträge, Dienste, Aufgaben, Vorfälle/Beschwerden, Schlüsselnummern, Inventarnummern/-bezeichnungen und Wachbuchkategorien. Ein Treffer enthält ausschließlich ID, Typ, Titel und Referenz. Berichte, Aufgabenbeschreibungen, interne Notizen, Mitarbeiternamen und sonstige Personaldetails, Dateinamen/-inhalte, Schlüsselbeschreibungen, Inventar-Seriennummern/-standorte und Wachbuch-Freitext werden weder durchsucht noch ausgegeben.

## Berechtigungen und Scope

- Kunden werden nur mit `customers.read` durchsucht.
- Objekte erfordern `objects.read`; `objects.read_all` erlaubt alle nicht archivierten Objekte, andernfalls gelten die persönlichen Objektzuweisungen. Kunden und Objekte mit archiviertem Kundenbezug werden ausgeschlossen.
- Mitarbeiter erfordern `employees.read`; gesucht wird ausschließlich die Personalnummer und als Titel wird ein konstanter Text ausgegeben. Namen und weitere Personalfelder sind ausgeschlossen. Der bestehende Personal-Lesepfad verwendet dieses Modulrecht, aber keinen Objekt-/Kundenscope; die globale Suche übernimmt dieselbe serverseitige Grenze und leitet keine Reichweite aus UI-Filtern ab.
- Dokumente (`documents.read`) und Verträge (`contracts.read`) verwenden die vorhandenen Scope-Helper des Dokumenten-/Vertragsmoduls, einschließlich Mitarbeiter-, Kunden- und Objektbereich. Archivierte Akten sowie Einträge mit archiviertem Kunden, Objekt oder Mitarbeiter werden ausgeschlossen.
- Dienste erfordern `scheduling.read` und verwenden `visible_shift_query`: ohne `employees.read` nur eigene Dienste, ohne `objects.read_all` nur zugewiesene Objekte. Abgesagte Dienste und archivierte Mitarbeiter, Objekte oder Kunden werden ausgeschlossen. Gesucht werden Objektname/-code; Titel und Referenz enthalten nur einen konstanten Typtext bzw. Dienstbeginn.
- Aufgaben erfordern `tasks.read_own`, `tasks.read_all` oder `tasks.manage_all` und verwenden `task_visibility`. Abgebrochene Aufgaben sowie Zuordnungen zu archivierten Kunden/Objekten werden ausgeschlossen. Nur der Titel ist Suchfeld.
- Vorfälle erfordern `incidents.read` oder ein globales Vorfallleserecht; `_incident_query` beschränkt lokale Rechte auf zugewiesene Objekte. Archivierte Objekte und Kunden werden ausgeschlossen. Nur der Vorfalltitel und die feste Vorfallsart werden ausgegeben; Bericht und sensible Details bleiben außen vor.
- Schlüssel erfordern `keys.read`; wie im bestehenden Schlüsselbestand gilt `objects.read_all`/`objects.manage_all` oder persönliche Objektzuweisung. Archivierte Schlüssel, Objekte und Kunden werden ausgeschlossen. Gesucht wird die Schlüsselnummer, niemals die Beschreibung.
- Inventar erfordert `inventory.read` und übernimmt die Bereichsgrenze des Inventarlisten-Endpunkts: `objects.read_all`/`objects.manage_all` oder persönliche Objektzuweisung. Archivierte Inventargegenstände, Objekte und Kunden werden ausgeschlossen. Gesucht werden nur Inventarnummer und Bezeichnung; Seriennummer, Standort und Mitarbeiterzuordnung werden nicht durchsucht oder ausgegeben. Zentrales Inventar ohne Objektzuordnung ist nur bei globalem Objektzugriff sichtbar.
- Wachbuchereignisse erfordern `owks.read`; außerhalb von `objects.read_all` begrenzt die persönliche Objektzuweisung den Zugriff. Ereignisse an archivierten Objekten/Kunden werden ausgeschlossen. Suchbar sind ausschließlich feste Ereigniskategorien, nicht Titel oder Freitext. Beim Öffnen lädt das Wachbuch das Ereignis über einen zusätzlich geschützten Detailendpunkt und prüft dort den Objektzugriff erneut.
- `type` schränkt auf einen einzelnen Suchtyp ein. Typen ohne Leserecht liefern keine Treffer. Ohne Suchberechtigung auf mindestens eine Quelle antwortet der Endpunkt mit `403`.
- Treffer öffnen das jeweils zuständige Fachmodul. Kunden, Objekte, Personal, Aufgaben, Vorfälle, Dokumente, Verträge und Wachbuchereignisse laden Details über die geschützten Fachpfade erneut; Dienste, Schlüssel und Inventargegenstände navigieren in den passenden Fachbereich und heben den Treffer hervor bzw. filtern über dessen Referenz. Eine Suchantwort selbst erteilt keine Berechtigung für Detaildaten.

## Anfrage und Sortierung

`q` ist erforderlich und wird nach dem Entfernen äußerer Leerzeichen auf 2 bis 100 Zeichen begrenzt. `limit` ist 1 bis 50 (Standard 20), `offset` 0 bis 5000 (Standard 0). Die Antwort enthält `items`, `total`, `limit` und `offset`.

Exakte Kunden-/Objekttitel und -referenzen stehen vor Präfix- und Teiltreffern; danach wird stabil nach Titel, Typ, Referenz und ID sortiert. `%`, `_` und `\\` in der Eingabe werden als Suchzeichen und nicht als SQL-Wildcards behandelt. Die Oberfläche wartet 250 ms nach der letzten Eingabe, bietet nur Suchtypen mit passendem Leserecht und lädt Treffer seitenweise.

## Bewusste Grenzen

Rechnungen bleiben ausgeschlossen: der aktuelle Rechnungslisten-Endpunkt erzwingt keinen Kunden-/Objektbereich und ein optionaler Filter ist keine Zugriffskontrolle. Die Personalquelle hat entsprechend dem bestehenden Personalmodul nur das Modulrecht `employees.read`, keine Objekt-/Kundengrenze. Die Suche ist eine einfache SQL-Abfrage ohne neuen Suchindex oder externen Dienst; sie verwendet bestehende Suchfelder und kann bei großen Datenmengen weniger schnell sein als eine dedizierte Volltextsuche. Es gibt keine Datenbankmigration.
