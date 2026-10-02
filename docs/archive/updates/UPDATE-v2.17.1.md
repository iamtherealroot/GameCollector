# Update auf GameCollector v2.17.1

```bash
cd /
mkdir -p /opt/gamecollector/updates/v2.17.1
unzip $HOME/Downloads/GameCollector-v2.17.1-update.zip -d /opt/gamecollector/updates/v2.17.1
bash /opt/gamecollector/updates/v2.17.1/GameCollector-v2.17.1/install.sh
```

Danach müssen die Versionsprüfung `2.17.1` und der Deep-Healthcheck den HTTP-Status `200` melden.

Der Hotfix ersetzt v2.17.0 vollständig. Der bereits erzeugte fehlerhafte Vorschau-Importlauf kann ignoriert werden. Für den erneuten Test dieselbe Datei `TESTDATA-v2.17.0-import.csv` hochladen.
