# Update auf GameCollector v2.20.0

v2.20.0 enthält sämtliche Funktionen aus v2.19.0, korrigiert dessen fehlerhafte Installationsprüfung und ergänzt nachträglich verwaltbare Konsolenmodellbilder. Die Installation ist direkt über v2.18.0 möglich.

```bash
cd /
mkdir -p /opt/gamecollector/updates/v2.20.0
unzip -o $HOME/Downloads/GameCollector-v2.20.0-update.zip -d /opt/gamecollector/updates/v2.20.0
bash /opt/gamecollector/updates/v2.20.0/GameCollector-v2.20.0/install.sh
```

Danach prüfen:

```bash
cd /opt/gamecollector
docker compose exec -T web python -c 'from app.app import APP_VERSION; print(APP_VERSION)'
docker compose exec -T web python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8000/health/deep").status)'
```

Erwartet werden `2.20.0` und `200`.
