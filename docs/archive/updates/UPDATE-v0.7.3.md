# GameCollector v0.7.3

## Neu
- Jellyfin-artige **Identifizieren**-Funktion auf Detail- und Bearbeitungsseite.
- Suche nach Titel/Plattform über RAWG sowie schlüssellose UPCitemdb-Produkttreffer.
- Trefferansicht mit Bild, Quelle, Plattform/Jahr und selektiver Feldübernahme.
- Übernahme wahlweise für Titel, Jahr, Publisher, Developer, Genre, Serie, Cover und externe ID.
- Sammlungs-/Exemplardaten (Zustand, Kaufpreis, Lagerort, Tags, Fotos, Notizen, Spielstatus, Wunschliste) werden beim Identifizieren nicht verändert.
- Interaktive **Cover suchen**-Galerie mit frei änderbarem Suchbegriff.
- Gewähltes Cover wird lokal unter `app/static/uploads/covers/` gespeichert.
- Identifizieren/Coversuche direkt aus dem Qualitätscheck erreichbar.

## Installation
Das Update verändert kein Datenbankschema und löscht keine Daten.

```bash
cd /opt/gamecollector
mkdir -p updates/v0.7.3
unzip -o ~/Downloads/GameCollector-v0.7.3-update.zip -d updates/v0.7.3
chmod +x updates/v0.7.3/install.sh
./updates/v0.7.3/install.sh
```

Prüfen:
```bash
docker compose exec web python -c "from app.app import APP_VERSION; print(APP_VERSION)"
```
Erwartet: `0.7.3`
