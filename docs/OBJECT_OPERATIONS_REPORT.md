# Objektbetriebsbericht

Der Objektbetriebsbericht ist eine aggregierte Ergänzung der Leitstelle. Er liest vorhandene Dienstplan-, Vorfall-, OWKS- und Aufgabendaten direkt; es gibt weder gespeicherte Berichtsdaten noch eine Migration. API und CSV sind auf aktive Objekte beschränkt, die der angemeldeten Person zugewiesen sind, sofern `objects.read_all` keine globale Objektsicht erlaubt. Ergebnisse werden stabil nach Objektnummer paginiert (50 Einträge in der UI, maximal 100 pro Anfrage); der CSV-Export enthält nur die aktuelle Seite.

## Kennzahlendefinitionen

- **Veröffentlichte, zugewiesene Schichten:** Anzahl veröffentlichter Planungsdatensätze, deren Dienstzeit den gewählten Zeitraum berührt. Schichten haben im Modell eine verpflichtende Mitarbeiterzuweisung; Entwürfe sind ausgeschlossen. Dies zählt geplante Dienste, nicht Anwesenheit.
- **Erstellte Vorfälle:** Anzahl gespeicherter Vorfälle nach `created_at` im UTC-Zeitraum. Es werden keine Titel, Berichte, Schweregrade, betroffenen Personen oder sonstigen Vorfallnarrative ausgegeben. Ein separates Ereignisdatum ist im aktuellen Vorfallmodell nicht vorhanden.
- **Kontrollereignisse / versäumte Kontrollen:** Anzahl gespeicherter OWKS-Ereignisse der Typen `control` bzw. `missed` nach `occurred_at` im UTC-Zeitraum. Das ist keine Quote erfolgreicher Kontrollgänge; erwartete Routenpunkte oder Sollkontrollen sind damit nicht vollständig belegbar.
- **Aufgabenstatus:** Aufgaben nach `created_at` im Zeitraum, gruppiert nach ihrem aktuellen Status beim Abruf. Die Kennzahl ist kein historischer Status-Snapshot.

Der Zeitraum ist einschließlich der angegebenen Start- und Endtage (höchstens 367 Kalendertage); Zeitstempel werden als UTC-Intervall `[Starttag 00:00, Tag nach dem Enddatum 00:00)` ausgewertet. Für Schichten wird geprüft, ob das Dienstintervall diesen Zeitraum überschneidet.

Eine **Besetzungsquote** wird nicht berechnet: Es gibt keine fachlich bestätigte, zeitlich auswertbare Sollbesetzung je Objekt. Eine **Ausfallquote** wird ebenfalls ausgelassen: Abwesenheitsdaten sind nicht hinreichend eindeutig bestimmten Diensten zugeordnet; eine Quote aus Abwesenheiten und Schichten wäre erfunden. Eine fachliche Definition ist vor Erweiterung abzustimmen. Der Bericht erstellt keine Noten, Rankings oder Aussagen über Qualitätskonformität.
