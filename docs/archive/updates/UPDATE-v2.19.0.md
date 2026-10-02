# Update auf GameCollector v2.19.0

Das ZIP wie gewohnt nach `$HOME/Downloads` kopieren und als root ausführen:

```bash
cd /
mkdir -p /opt/gamecollector/updates/v2.19.0
unzip -o $HOME/Downloads/GameCollector-v2.19.0-update.zip -d /opt/gamecollector/updates/v2.19.0
bash /opt/gamecollector/updates/v2.19.0/GameCollector-v2.19.0/install.sh
```

Danach Version und Healthcheck prüfen:

```bash
cd /opt/gamecollector
docker compose exec -T web python -c 'from app.app import APP_VERSION; print(APP_VERSION)'
docker compose exec -T web python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8000/health/deep").status)'
```

Erwartet werden `2.19.0` und `200`.
