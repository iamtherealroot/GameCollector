# Update auf GameCollector v2.17.0

## Installation aus dem Downloads-Ordner

```bash
cd /
mkdir -p /opt/gamecollector/updates/v2.17.0
unzip $HOME/Downloads/GameCollector-v2.17.0-update.zip -d /opt/gamecollector/updates/v2.17.0
bash /opt/gamecollector/updates/v2.17.0/GameCollector-v2.17.0/install.sh
```

Das Paket kann direkt über v2.16.2 installiert werden. Datenbank und Uploads bleiben erhalten; vor dem Update wird automatisch ein Backup angelegt.

## Neu

- echter CSV-Vorschaulauf ohne sofortige Datenänderung
- Konfliktentscheidung pro Zeile
- Unterstützung einzelner physischer und digitaler Exemplare
- Importprotokoll und sicheres Rückgängigmachen
- verlustfreies Zusammenführen erkannter Katalogdubletten

Die konkrete Abnahme befindet sich in `TEST-v2.17.0.md`. Eine vorbereitete Datei liegt als `TESTDATA-v2.17.0-import.csv` bei.
