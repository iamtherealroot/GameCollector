# Bibo 6.0.0-rc.2 – Sammlung und Wertentwicklung

Alle Funktionen der ersten 6.0-Testversion sind enthalten. Stabil bleibt 5.1.5.

- **Cover, Liste und Reihe:** Drei sichtbare Ansichtsschalter in der Sammlung, je Nutzer und Sammlung gespeichert. Die Reihenansicht gruppiert die vorhandenen Einträge, ohne Exemplare doppelt zu zählen. Karten unterschiedlicher TCGs bleiben getrennt. Einzelne Reihen führen zur vorhandenen Fortschritts- und Fehlteileübersicht.
- **Reihen vervollständigen:** Präsenter Zugang direkt in der Sammlung sowie bei Filmen, TV und Büchern. Spiele, Filme, TV, Bücher und Konsolen übernehmen den passenden Bereich. Ungeklärte Reihen bleiben über „Alle Reihen & Fortschritt“ erreichbar.
- **Gesamtwert:** Größere Anzeige auf der Startseite. Klein darunter die Tagesveränderung mit Betrag und Prozent: Grün bei Anstieg, Rot bei Rückgang, neutral bei unverändertem Wert. Bei fehlendem oder veraltetem Vergleichsstand wird keine Tagesänderung behauptet. Bei einem Nullwert als Basis entfällt die Prozentangabe.
- **Kleiner Verlaufsgraph:** Wählbare und gespeicherte Zeiträume 24 Stunden, 7 Tage, 1 Monat (30 Tage), 1 Jahr (365 Tage) und Gesamt. Vorhandene, sammlungsbezogene Wertstände bilden die Grundlage. Die Startseite speichert neue Beobachtungen bei Änderungen oder nach einer Stunde. Zwischen Beobachtungen wird der letzte gespeicherte Wert gehalten; fehlende Historie wird gekennzeichnet. Der Verlauf enthält auch Käufe, Verkäufe und Preiskorrekturen.
- **Einzelkartenpreise:** eBay-Treffer benötigen eine konkrete Ausgabe/Kartennummer und den passenden Namen. Setnamen allein oder Verpackungs-EANs reichen nicht. Decks, Booster, Pakete, Playsets, bewertete Karten und unpassende Ausgaben werden ausgeschlossen. Sprache, Variante und bekannte Seltenheits-/Zustandsangaben werden berücksichtigt. Mindestens zwei unterschiedliche passende Angebote sind nötig.
- **Bestehende falsche Kartenwerte:** Alte eBay-Automatikwerte ohne Ausgabenprüfung werden mit ihren bisherigen Angaben gesondert in den Metadaten aufbewahrt und aus aktuellen Automatikwerten entfernt. Manuelle Schätzungen und Fixpreise bleiben erhalten. Die alten ungesicherten eBay-Aktivitäten werden nicht mehr als Gewinner/Verlierer gewertet. Eine erneute Bewertung verwendet die neue Prüfung, auch bei geplanten Läufen. Historische Gesamtwertpunkte bleiben erhalten; die aktuelle Korrektur kann daher im Graph als Rückgang erscheinen.

## Enthaltene Grundlagen aus rc.1

Gespeicherte Filter, direkt ausgewählte Exemplare für gemeinsame Änderungen, Datenqualität mit konkreten Einträgen, einheitliche Detailaktionen und nächster Scan nach erfolgreichem Speichern.

## Prüfstand

Automatisierte Tests prüfen Kartenidentität und Angebotsfilter, Rückstellung alter Werte, manuelle Preise, Tagesvergleich, fehlende und alte Historie, Sammlungsgrenzen, gespeicherte Ansichten und Reihenverknüpfungen. Die bestehenden Regressionstests werden weiter ausgeführt. Die neue Darstellung muss auf Desktop und iPhone noch visuell abgenommen werden. Diese Testversion wurde nicht auf dem Produktionsserver installiert.

Die vollständige globale Katalogüberarbeitung der Spiel- und Buchreihen ist ein separater offener Arbeitsblock. Die neue Reihenansicht verwendet die vorhandenen Zuordnungen.

## Testumgebung

Paket auf dem Docker-Testserver entpacken und im Paketordner ausführen:

```bash
bash scripts/docker-test.sh check
```

Der enthaltene `scripts/bibo-tu.sh` kann das Paket alternativ per SSH vom Desktop an den Testserver übertragen und einen Tunnel öffnen. Nicht ungeprüft über die Produktion installieren.
