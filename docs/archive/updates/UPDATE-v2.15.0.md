# GameCollector v2.15.0

Dieses Update verbessert die Film- und Seriensammlung allgemein – nicht nur für einzelne Namen wie Batman.

## Neu

- Die TMDB-Titelsuche lädt bis zu drei Ergebnisseiten (maximal 60 Treffer).
- Treffer lassen sich nach Neueste, TMDB-Relevanz oder Älteste sortieren und optional auf ein Jahr begrenzen.
- Bereits vorhandene Titel werden direkt im Suchergebnis erkannt und verlinkt.
- Film- und Serienbestände besitzen eine Suche nach Titel, Ausgabe, Medium und EAN.
- „Reihen & Fortschritt“ bietet Suche, Statusfilter, Sortierung, Fortschrittsbalken und Gesamtkennzahlen.
- Detailansichten zeigen physische Ausgaben klarer und weisen den korrekten Gesamtwert aus.
- Mehrfilm- und Staffelboxen werden wertmäßig nur einmal gezählt, auch wenn sie mehrere Teile abdecken.

## Installation

```bash
cd /opt/gamecollector/updates/v2.15.0
sudo bash install.sh
```

Das Installationsskript erstellt vor der Aktualisierung ein Programm- und Datenbankbackup, baut Web und Scheduler neu und führt anschließend den Deep-Healthcheck aus.
