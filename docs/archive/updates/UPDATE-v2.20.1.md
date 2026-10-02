# Update auf GameCollector v2.20.1

v2.20.1 korrigiert die Überlagerung zwischen der Offline-Statusleiste und den Desktop-Navigationsmenüs. Alle Funktionen aus v2.20.0 bleiben enthalten.

```bash
cd /
mkdir -p /opt/gamecollector/updates/v2.20.1
unzip -o $HOME/Downloads/GameCollector-v2.20.1-update.zip -d /opt/gamecollector/updates/v2.20.1
bash /opt/gamecollector/updates/v2.20.1/GameCollector-v2.20.1/install.sh
```

Danach Version und Healthcheck prüfen. Erwartet werden `2.20.1` und `200`.
