# Bibo v4.6.6 – Stabilere Spielebewertung

- eBay-Spielepreise vergleichen ausschließlich gleiche Vollständigkeit: Loose, komplett (CIB), versiegelt oder eindeutig beschriebene Teilsets.
- Unklare Vollständigkeit, Repros, Grading, Defekte und reine Verpackungs-/Anleitungsangebote werden ausgeschlossen.
- Keine pauschale Loose-/CIB-/Sealed-Umrechnung gemischter Angebote mehr.
- Mindestens fünf vergleichbare Angebote nach Filterung; Median mit Ausreißerfilter.
- Alle Suchvarianten werden ausgewertet, Angebote anhand ihrer ID dedupliziert und Titel strenger abgeglichen.
- Änderungen ab zugleich 25 Prozent und 15 Euro werden vor Übernahme zurückgestellt. Ein weiterer Abruf frühestens nach 24 Stunden muss denselben Quellentyp und dieselbe Bewertungsbasis mit höchstens 10 Prozent Abweichung bestätigen. Offene Kandidaten verfallen nach sieben Tagen.
- Zurückgestellte Preise verändern weder den Gesamtwert noch die Preisänderungshistorie. Der bisherige Wert bleibt sichtbar, der Kandidat erscheint als Prüfhinweis im Preiscenter.
- Rückkehr zum bisherigen Preis verwirft den Kandidaten. Wiederholte Abrufe am selben Tag können keine Bestätigung erzwingen.
- Der Schutz gilt auch bei einem Wechsel zwischen eBay und Fallback-Quellen.
- Neue Datenbankspalte wird beim Start automatisch ergänzt; manuelle Schätzungen bleiben bestehen.

Installation/Update wie bisher über `bash install.sh` aus dem entpackten Verzeichnis.

## Validierung

Sieben Offline-Regressionstests mit gemischten Pokémon-Gelb-Angeboten, Quellenwechseln, Preissprüngen, Tagesbestätigung und Schutz der Historie; Python-Syntax und Shell-Syntax geprüft; ZIP-Struktur/Integrität geprüft.

Keine Live-eBay-Abfrage oder Installation auf dem Produktionsserver in dieser Umgebung. Bestehende fehlerhafte Bewertungen werden nicht pauschal gelöscht; große Korrekturen benötigen ebenfalls die spätere Bestätigung. Ein Abruf wird durch den Bestätigungsschutz nicht zusätzlich geplant: Er erfolgt durch den bestehenden Scheduler oder eine manuelle Neubewertung.
