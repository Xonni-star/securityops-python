# Inventarverwaltung

Die Inventarverwaltung erfasst betriebliche Betriebsmittel wie Schließ- und
Zutrittsmedien, Funkgeräte, Smartphones, Tablets, Computer, Dienstkleidung,
Sicherheitsausrüstung, Fahrzeuge und sonstige Gegenstände. Pro Eintrag werden
Inventarnummer, optionale Seriennummer, Bezeichnung, Kategorie, Zustand, Status,
Standort sowie optional Objekt und aktuell zugeordneter Mitarbeiter geführt.
Inventarnummern und nicht-leere Seriennummern sind datenbankseitig eindeutig.

## Abgrenzung zur Schlüsselverwaltung

Physische Einzelschlüssel bleiben im bestehenden Schlüsselregister (`/keys`).
Die Inventarverwaltung legt keine zweite Schlüsselakte an. Zutrittskarten,
Transponder und andere eigenständige Schließmedien können als Kategorie
„Schließ- und Zutrittsmedien“ erfasst werden. Schlüssel- und Wartungsfristen
werden nicht automatisch berechnet; es gibt keine automatische Erinnerung oder
Benachrichtigung.

## Rechte und Objektbereich

Alle Endpunkte erfordern eine Sitzung und das jeweilige Recht:

- `inventory.read`: Inventar, Suchergebnisse und Ereignishistorie lesen.
- `inventory.manage`: Inventar anlegen, Stammdaten ändern und archivieren.
- `inventory.move`: Ausgabe, Rückgabe, Übergabe, Zustandsmeldung, Wartung und
  Reparatur protokollieren.

Administrator, Geschäftsführung und operative Rollen erhalten die drei Rechte;
Objektleitungen erhalten Lese- und Vorgangsrechte. Das Backend begrenzt
Ergebnislisten, Kandidatenlisten, Einzelabrufe und Ereignishistorien auf
zugewiesene Objekte. Zentrales, keinem Objekt zugeordnetes Inventar ist nur für
Benutzer mit globalem Objektzugriff sichtbar und verwaltbar. Eine Übergabe auf
ein anderes Objekt erfordert Inventarverwaltung und die Verwaltung beider
Objektbereiche. Mitarbeiter können nur gewählt werden, wenn sie aktiv sind und
dem Zielobjekt zugewiesen sind. Nicht zugängliche Einzel-IDs werden wie nicht
vorhandene Inventare beantwortet.

## Vorgänge und Verlauf

Ausgabe und Übergabe verlangen eine bestätigte Empfangsquittierung; die
Quittierungsnotiz ist optional. Ausgabe, Rückgabe, Übergabe, Verlust,
Beschädigung, Wartungsbeginn, Reparaturabschluss und Archivierung werden in
derselben Datenbanktransaktion wie der Bestandsstatus als Ereignis gespeichert.
Eine Zeilensperre serialisiert parallele Vorgänge gegen denselben Gegenstand.
Ereignisse sind append-only und werden nicht geändert oder gelöscht. Auch
Stammdatenänderungen erzeugen ein Historienereignis und einen Audit-Eintrag.

Verlust- und Beschädigungsmeldungen sowie Wartung und Reparatur erfordern eine
Notiz. Wartung nimmt einen verfügbaren Gegenstand außer Betrieb; ein
Reparaturabschluss setzt einen Zustand und macht ihn wieder verfügbar.
Archivieren ist bei ausgegebenem oder in Wartung befindlichem Inventar nicht
zulässig. Aufbewahrung, Erinnerungszeitpunkte und automatische Benachrichtigungen
sind nicht Teil dieser Funktion.

## API

- `GET /api/v1/inventory/assets`: Suche, Filterung nach Kategorie, Zustand,
  Status, Objekt und Mitarbeiter sowie Pagination.
- `POST /api/v1/inventory/assets`: Inventargegenstand anlegen.
- `PATCH /api/v1/inventory/assets/{id}`: Stammdaten ändern.
- `POST /api/v1/inventory/assets/{id}/archive`: Gegenstand archivieren.
- `POST /api/v1/inventory/assets/{id}/events`: Ausgabe, Rückgabe, Übergabe,
  Verlust-/Beschädigungsmeldung, Wartung oder Reparatur protokollieren.
- `GET /api/v1/inventory/assets/{id}/events`: paginierte Historie einsehen.
- `GET /api/v1/inventory/objects`: im eigenen Objektbereich sichtbare Objekte.
- `GET /api/v1/inventory/employees`: derzeit zugeordnete Mitarbeiter im
  eigenen Objektbereich für Filter.
- `GET /api/v1/inventory/eligible-employees`: aktive Mitarbeiter mit passender
  Objektzuweisung für Ausgabe oder Übergabe.

Kategorie: `access_media`, `radio`, `smartphone`, `tablet`, `computer`,
`clothing`, `safety_equipment`, `vehicle`, `other`. Zustand: `new`, `good`,
`used`, `worn`, `defective`. Status: `available`, `issued`, `maintenance`,
`lost`, `damaged`, `archived`.
