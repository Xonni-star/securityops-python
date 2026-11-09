# Vorfall- und Beschwerdemanagement

Das Modul führt einen eigenständigen, objektbezogenen Vorgangskern für Vorfälle, Unfälle, Übergriffe, Sachbeschädigungen und Beschwerden ein. OWKS-Ereignisse bleiben unverändert und unveränderlich; ein Vorfall kann optional auf genau ein OWKS-Ereignis desselben Objekts verweisen.

## Umfang

Ein Vorgang speichert Titel und Kurzmeldung, Art, Schweregrad, Objekt, Status, Frist, verantwortliches Konto sowie Erstellungs- und Änderungszeit. Verantwortliche müssen aktiv und dem Objekt zugeordnet sein. Maßnahmen besitzen eine eigene Frist, verantwortliche Person und einen nachvollziehbaren Status. Der Status `action_required` bildet eine manuelle Eskalation ab. Überfällige offene Vorgänge können gefiltert werden. Der Abschluss verlangt einen Abschlussbericht und erledigte Maßnahmen.

Statusübergänge sind `reported → investigating → action_required → investigating` und aus jedem offenen Status nach `closed`; abgeschlossene Vorgänge sind endgültig. Änderungen, Eskalationen, Abschluss, Personen- und Dateibezüge werden mit Feld- bzw. Übergangsinformation append-only protokolliert und auditiert. Sensible Freitexte und Namen werden nicht in die allgemeine Verlaufshistorie kopiert.

## Berechtigungen

- `incidents.read` und `incidents.update` gelten nur für zugewiesene Objekte.
- `incidents.read_all` und `incidents.manage_all` erlauben den bereichsübergreifenden Zugriff ausdrücklich; Änderungen benötigen weiterhin eine Schreibberechtigung.
- `incidents.create` erlaubt Meldungen nur für erreichbare Objekte.
- `incidents.sensitive.read` schützt Vorfallhergang, Abschlussbericht, Beteiligte/Zeugen und Dateiinhalte separat.
- `incidents.sensitive.manage` erlaubt die Änderung sensibler Angaben sowie Datei-Uploads. Dafür ist zusätzlich die Vorfall-Schreibberechtigung erforderlich.

Nicht erreichbare Vorfälle werden wie nicht vorhandene Vorgänge beantwortet. Objekt- und Verantwortlichenbezüge werden serverseitig geprüft.

## Dateien und Integrationen

Anhänge sind auf PDF und PNG/JPEG bis maximal 10 MiB begrenzt. Sie verwenden die bestehende MIME-/Signaturvalidierung, den fail-closed Malware-Scan und den privaten Dokumentenspeicher; Upload und Download erfordern die jeweiligen Vorfall- und Sensitivitätsrechte. Eine Datei wird bei fehlgeschlagener Datenbanktransaktion entfernt.

OWKS wird nur referenziert, nicht dupliziert oder verändert. Vorfälle erzeugen keine automatischen Aufgaben oder Benachrichtigungen. Der separate Aufgaben-Outbox-Worker verarbeitet lediglich bereits erzeugte Ereignisse für Aufgaben-Neuzuweisung und Statuswechsel; er integriert keine Fachmodule. Fristerinnerungen, automatische Eskalationsregeln und Aufgaben-/Benachrichtigungsverknüpfungen bleiben Folgefunktionen.

Die Alembic-Migration `0022_incident_management` baut linear auf `0021_key_management` auf. Ein Downgrade wird bei Vorfällen, Maßnahmen, Verlauf, sensiblen Details, Personen-/Dateibezügen oder benutzerdefinierten Rollenberechtigungen abgelehnt.
