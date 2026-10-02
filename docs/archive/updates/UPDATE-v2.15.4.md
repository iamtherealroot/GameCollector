# GameCollector v2.15.4

Dieses Korrekturupdate behebt falsche Filmreihen-Zusammenführungen und die unbekannte Gesamtzahl in der Reihenübersicht.

## Behoben

- TMDBs unscharfe Collection-Suche gilt nicht länger automatisch als Beweis für eine gemeinsame Filmfamilie.
- Eine gefundene Collection wird nur zusammengeführt, wenn der bereinigte, lokalisierte Reihenname exakt übereinstimmt.
- „Der Pate“ zeigt ausschließlich die drei kanonischen Teile der TMDB-Collection 230; „Freitag der 13.“ und „Der Kindergarten Daddy“ bleiben eigene Reihen.
- Die Filmreihenübersicht lädt die bekannte Zahl eindeutiger TMDB-Filmteile. Dadurch wird beispielsweise `1 / 3` statt `1 / ?` angezeigt.
- Dubletten desselben Films verändern die Zahl vorhandener Teile nicht. Mehrfilm-Boxen und manuelle Abdeckungen können weiterhin mehrere unterschiedliche Teile als vorhanden markieren.
- Die feste Batman-Hauptfilmfamilie aus v2.15.3 bleibt vollständig erhalten.

Persönliche Exemplardaten, Werte, Status und Box-Zuordnungen werden nicht gelöscht oder überschrieben.

## Installation

```bash
cd /opt/gamecollector
mkdir -p updates/v2.15.4
unzip -o $HOME/Downloads/GameCollector-v2.15.4-update.zip -d updates/v2.15.4
cd updates/v2.15.4
sudo bash install.sh
```
