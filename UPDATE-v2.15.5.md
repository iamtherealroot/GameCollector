# GameCollector v2.15.5

Dieses Update vereinheitlicht „Reihen & Sammlungen“ und ergänzt digitale Spiele-Exemplare.

## Änderungen

- Kartenansicht für alle Reihen und Sammlungen
- nur noch ein zentraler Navigationspunkt unter „Sammlung“
- kompatible Weiterleitung alter `/franchises`-Links
- Spiele-Exemplare als „Physisch“ oder „Digital“ erfassen
- eigener Sammlungsfilter und Zähler für digitale Exemplare
- digitale Exemplare von physischen Preisen und Reihenfortschritten ausgeschlossen
- Formatangabe in CSV-, JSON- und Komplett-Exporten

## Installation

```bash
cd /opt/gamecollector
mkdir -p updates/v2.15.5
unzip -o $HOME/Downloads/GameCollector-v2.15.5-update.zip -d updates/v2.15.5
cd updates/v2.15.5
sudo bash install.sh
```

Der Installer erstellt vor der Aktualisierung ein Code- und Datenbank-Backup, baut Web und Scheduler neu und prüft anschließend den Healthcheck.

## Prüfung

```bash
cd /opt/gamecollector
docker compose exec -T web python -c "from app.app import APP_VERSION; print(APP_VERSION)"
```

Erwartete Ausgabe: `2.15.5`
