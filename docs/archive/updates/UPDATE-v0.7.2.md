# GameCollector v0.7.2

## Neu
- Gesamtwertentwicklung der kompletten gemeinsamen Sammlung als Liniengraph
- Zeiträume 30 / 90 / 365 Tage / Alles
- Tiefst-, Höchstwert, absolute und prozentuale Veränderung
- tägliche automatische Neubewertung um 03:00 Uhr (Europe/Berlin) über separaten Scheduler-Container
- jeder automatische Lauf schreibt einen Gesamtwert-Snapshot
- manueller „Sammlung neu bewerten“-Lauf schreibt ebenfalls einen Snapshot
- historischer Gesamtgraph startet mit v0.7.2; alte Gesamtwerte werden bewusst nicht rückwirkend erfunden
- Release-Workflow verwendet künftig `/opt/gamecollector/updates/vX.Y.Z/`

## Installation
Siehe die mitgelieferten Installationsbefehle. Das bestehende PostgreSQL-Volume bleibt erhalten. Niemals `docker compose down -v` verwenden.
