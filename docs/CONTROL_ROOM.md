# Leitstellenübersicht

Die Leitstelle ist eine serverseitig berechnete Momentaufnahme (`GET /api/v1/control-room`). Die API setzt `control_room.read` und `objects.read` voraus. Sie gibt nur aktive, nicht archivierte Objekte aus, auf die die angemeldete Person über `objects.read_all` oder eine Objektzuweisung Zugriff hat. Ein angefragtes nicht zugängliches Objekt wird mit `404` beantwortet. Quelldaten werden zusätzlich nur ausgegeben, wenn die jeweils passende Fachberechtigung vorhanden ist; Listen sind auf 100 Einträge begrenzt, Kennzahlen zählen alle passenden Datensätze.

## Enthaltene Daten

| Bereich | Quelle und Abgrenzung |
|---|---|
| Aktive Objekte | Aktive, nicht archivierte Objekte innerhalb des Objektzugriffs. |
| Laufende Dienste / eingesetzte Mitarbeiter | Veröffentlichte Schichten, deren Startzeit erreicht und deren Endzeit noch nicht erreicht ist. Benötigt `scheduling.read`; ohne `employees.read` sind nur eigene Schichten sichtbar. |
| Kontrollgänge und Alarme | Im Zeitraum offene oder in Bearbeitung befindliche OWKS-Ereignisse vom Typ `missed`; außerdem `deviation`, `manipulation` oder `notification` nur bei Warnung/kritischer Schwere. Beschreibung und Anhänge werden nicht ausgegeben. Benötigt `owks.read`. Es werden nur vom OWKS-Monitor angelegte Versäumnisse berücksichtigt; das Dashboard erzeugt selbst keine. |
| Vorfälle | Nicht geschlossene Vorfälle samt Status, Schwere, Fälligkeit, Objekt und verantwortlicher Person. Berichtstext, sensible Details, Personenbezüge und Anhänge werden nicht ausgegeben. Benötigt eine Vorfall-Leseberechtigung. Überfälligkeit ergibt sich ausschließlich aus `due_at`. |
| Aufgaben | Offene, in Bearbeitung befindliche oder blockierte Aufgaben mit Priorität, Status, Fälligkeit und Verantwortlichkeit. Objektaufgaben bleiben auf zugängliche Objekte begrenzt; objektlose Aufgaben sind nur für die verantwortliche oder erstellende Person sichtbar. Benötigt eine Aufgaben-Leseberechtigung. „Dringend“ umfasst Priorität `urgent` oder eine überschrittene Fälligkeit. |
| Personalausfälle | Offene oder genehmigte Abwesenheiten, die sich mit dem gewählten Zeitraum überschneiden. Nur Beschäftigte mit einer Nutzerzuweisung zu einem zugänglichen Objekt. Benötigt `employees.absences.read`. |
| Qualifikationsprobleme | Nicht archivierte Qualifikationen aktiver, einem zugänglichen Objekt zugewiesener Beschäftigter mit Ablaufdatum bis zum Ende des Zeitraums; abgelaufene Nachweise bleiben enthalten. Benötigt `employees.read`. |
| Abrechnungsfreigaben | Noch nicht freigegebene Rechnungen (`draft`) ausschließlich mit einem Vertrag, der direkt einem zugänglichen Objekt zugeordnet ist. Benötigt sowohl `billing.invoices.read` als auch `billing.invoices.approve`. Rechnungen ohne objektgebundenen Vertrag werden bewusst nicht aufgeführt. |

Die Datumsauswahl wird als UTC-Kalendertag interpretiert. Sie filtert OWKS-Ereignisse und Abwesenheiten; offene Vorfälle und Aufgaben bleiben unabhängig vom Erstellungsdatum sichtbar. Laufende Schichten sind eine Momentaufnahme zum Zeitpunkt der Antwort. `generated_at` kennzeichnet diesen serverseitigen Berechnungszeitpunkt; es gibt weder WebSocket noch automatisches Polling.

## Operative Aktionen

Die Leitstelle bietet zusätzlich Aktionsbereiche für Mitarbeitersuche, Dienstplanung, Aufgaben und Vorfälle. Es werden die bestehenden Fachmodule und deren APIs eingebettet; die Leitstellenoberfläche ersetzt keine Berechtigungs- oder Objektbereichsprüfung. Die Aktionsbereiche bleiben auch verfügbar, wenn die Momentaufnahme nicht geladen werden kann. Mitarbeitersuche benötigt `employees.read`. Dienstbearbeitung und Vertretung verwenden die bestehenden `scheduling.*`-Endpunkte, Aufgabenaktionen die `tasks.*`-Rechte und Vorfalländerungen die abgestuften `incidents.*`-Rechte einschließlich separater Rechte für sensible Abschlussdaten.

`GET /api/v1/scheduling/shifts/{shift_id}/replacement-candidates` benötigt `scheduling.manage` und liefert nur andere aktive, nicht archivierte Beschäftigte, die die vorhandene Besetzungsprüfung bestehen: Objektzuweisung, Zeitraum/Beschäftigungsstatus, Abwesenheit, Verfügbarkeit, Sperrzeiten, erforderliche Qualifikation, Schichtüberschneidung und konfigurierte Ruhezeit. Ein späterer Vertretungsauftrag führt die Prüfung erneut aus und protokolliert die Vertretung wie bisher; zwischen Kandidatensuche und Zuweisung entstandene Konflikte werden dadurch abgewiesen. Die Liste ist eine Momentaufnahme, keine Reservierung.

Aufgabenabschluss verlangt weiterhin den serverseitig geprüften Erledigungsnachweis. Ein Vorfallabschluss erfordert weiterhin die Berechtigung zum Ändern sensibler Vorfalldaten, einen Abschlussbericht und abgeschlossene Maßnahmen. Fehler aus den Fach-APIs werden im Aktionsbereich angezeigt; die Leitstelle ergänzt keine eigenen Abschluss-, Eskalations- oder Benachrichtigungsregeln.

## Nicht enthaltene Kategorien

Es gibt keine belastbare Quelle für Alarmmeldungen außerhalb der OWKS-Ereignisse, fehlende Dienstbesetzungen, Qualifikationskonflikte mit konkreten Schichten, Eskalationsstufen, Kundenfreigaben, allgemeine Personalfehlzeiten ohne eingetragene Abwesenheit oder dringende Aufgaben aus nicht erfassten Systemen. Diese Kategorien werden nicht als leere Kennzahlen oder simulierte Meldungen dargestellt. Der separate Worker verarbeitet nur Aufgaben-Zuweisungs- und Statusereignisse zu In-App-Benachrichtigungen und speist die Leitstellenübersicht nicht; es gibt keine automatische Dashboard-Aktualisierung oder Alarmierung.

## Berechtigungen und Migration

Migration `0023_control_room_permission` ergänzt `control_room.read` für Administrator, Geschäftsführung, Operations und Objektleitung. Es wird keine eigene Dashboard-Tabelle angelegt. Fachrechte und Objektzuweisungen gelten weiterhin je Datenquelle.
