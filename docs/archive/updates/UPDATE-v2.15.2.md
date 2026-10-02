# GameCollector v2.15.2

Dieses Update stellt DVDs, Blu-rays und Serienausgaben auf echte Einzel-Exemplare um – entsprechend der Verwaltung mehrerer Spielekopien.

## Neu

- Jede physische Film-/Serienausgabe erhält einen eigenen Datensatz und eine eigene Exemplar-ID.
- EAN, Medium, Edition, Zustand, Vollständigkeit, Kaufpreis, Kaufdatum, Lagerort, Marktwert, Schätzung und Notizen sind pro Exemplar getrennt bearbeitbar.
- In Filmreihen und TV-Staffeln ist jedes vorhandene Exemplar direkt anklickbar.
- Auf der Detailseite werden alle physischen Exemplare desselben Werks übersichtlich verlinkt.
- Über „Weiteres Exemplar anlegen“ kann eine bestehende Ausgabe kopiert und anschließend individuell angepasst werden.
- Bereits vorhandene Titel können über die TMDB-Suche erneut als weiteres Exemplar angelegt werden.

## Automatische Migration

Bestehende Film- und Serieneinträge mit einer Menge größer 1 werden beim ersten Start automatisch aufgeteilt. Alle Ausgangsdaten werden auf die neuen Exemplare übernommen. Die Gesamtanzahl und der berechnete Sammlungswert ändern sich dadurch nicht.

Die Migration löscht keine Filme, Serien, Boxsets oder persönliche Felder. Das Installationsskript erstellt zusätzlich vorab ein vollständiges Programm- und Datenbankbackup.

## Installation

```bash
cd /opt/gamecollector/updates/v2.15.2
sudo bash install.sh
```
