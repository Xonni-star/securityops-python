# OWKS- und Vorfallintegration

Ein berechtigter Nutzer kann ein zugängliches OWKS-Ereignis aus der Ereignisansicht als Vorfall oder Beschwerde erfassen. Jedes OWKS-Ereignis kann höchstens einem Vorfall zugeordnet sein; eine eindeutige Datenbank-Constraint verhindert auch doppelte parallele Erfassungen. Der Vorgang speichert Titel, Typ, Schwere, eigenen Bericht, eine dem Objekt zugeordnete verantwortliche Person und optional eine Fälligkeit. Die bestehende Vorfall-API prüft `incidents.create`, Objekt-Schreibzugriff, die Objektzugehörigkeit des OWKS-Ereignisses und die Verfügbarkeit der verantwortlichen Person serverseitig.

Gespeichert wird nur die OWKS-Ereignisreferenz. Die Oberfläche zeigt bei bereits verknüpften Ereignissen nur diesen Status und keine Vorfalldetails. Das Originalereignis, seine Beschreibung und Anlagen werden nicht kopiert oder verändert; der Vorfall enthält keine privaten Vorfalldetails oder Anhänge aus dieser Integration. OWKS-Kontrollscans bleiben ausdrücklich ohne bestätigte physische Anwesenheit (`presence_verified=false`), solange keine geeignete kryptografische Tag-Infrastruktur besteht.

Dieser Schritt verknüpft keine Aufgaben, Benachrichtigungen oder Eskalationsregeln. Automatische Empfänger, Fristerinnerungen und weitere Ketten bleiben offen und werden nicht impliziert.
