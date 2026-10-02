# GameCollector v0.7.1

Kleines Wartungsupdate für die automatische Preisbewertung.

## Änderungen

- Neue neutrale Diagnose `no_automatic_price_source`, wenn weder PrixRetro noch VGPreise die Plattform unterstützt.
- Moderne Plattformen werden dadurch nicht mehr irreführend als Fehler/„unsupported platform“ dargestellt.
- Dashboard zeigt **Keine automatische Preisquelle** statt **Plattform nicht unterstützt**.
- Sammlungsfilter wurde entsprechend umbenannt.
- Alte Einträge mit `unsupported_platform` bleiben kompatibel und werden weiterhin im selben Filter erfasst.
- Einzel- und Sammel-Neubewertung behandeln fehlende Plattformquellen korrekt.
- Manuelle Schätzwerte und bestehende Preisverläufe bleiben unverändert.

## Installation

```bash
cd /opt/gamecollector
unzip -o ~/Downloads/GameCollector-v0.7.1-update.zip
docker compose up -d --build web
```

Prüfen:

```bash
docker compose exec web python -c "from app.app import APP_VERSION; print(APP_VERSION)"
```

Erwartet: `0.7.1`

> Wichtig: `docker compose down -v` nicht verwenden.
