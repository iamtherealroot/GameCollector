# GameCollector v0.7.4

## Verbesserungen
- **Lokaler/deutscher Titel bleibt erhalten:** Beim Identifizieren wird der englische Provider-Titel nicht mehr automatisch übernommen.
- Im Identifizieren-Dialog gibt es pro Treffer ein editierbares Feld **„Titel in GameCollector“**.
- Der Titel wird nur geändert, wenn **„Titel ändern“** aktiviert wird. Damit können deutsche/regional gewünschte Titel unabhängig von RAWG gepflegt werden.
- Der Katalogtitel bleibt danach weiterhin normal über **Katalogeintrag bearbeiten** änderbar.
- **Serien-Abgleich verbessert:** Bereits identifizierte Spiele werden in Serien jetzt primär über `external_source + external_id` erkannt, nicht nur über den Texttitel.
- Dadurch werden deutsch benannte Spiele auch dann als **✓ Besitzt** markiert, wenn die synchronisierte Serienliste den englischen RAWG-Titel verwendet.
- Titelvergleich bleibt als Fallback bestehen, damit auch ältere/lokal angelegte Einträge weiterhin funktionieren.

## Datenbank
Keine Schemaänderung. Bestehende Sammlung, Exemplare, Preise, Bilder und PostgreSQL-Volumes bleiben unverändert.

## Installation
```bash
cd /opt/gamecollector
mkdir -p /opt/gamecollector/updates/v0.7.4
unzip -o $HOME/Downloads/GameCollector-v0.7.4-update.zip -d /opt/gamecollector/updates/v0.7.4
chmod +x /opt/gamecollector/updates/v0.7.4/install.sh
/opt/gamecollector/updates/v0.7.4/install.sh
```

Prüfen:
```bash
docker compose exec web python -c "from app.app import APP_VERSION; print(APP_VERSION)"
```
Erwartet: `0.7.4`
