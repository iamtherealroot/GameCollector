# Update auf GameCollector v2.18.0

```bash
cd /
mkdir -p /opt/gamecollector/updates/v2.18.0
unzip $HOME/Downloads/GameCollector-v2.18.0-update.zip -d /opt/gamecollector/updates/v2.18.0
bash /opt/gamecollector/updates/v2.18.0/GameCollector-v2.18.0/install.sh
```

Danach müssen die Versionsprüfung `2.18.0` und der Deep-Healthcheck den HTTP-Status `200` melden.

Das Update ergänzt beim Start ausschließlich die neuen Felder für reversible Preisfixierungen. Bestehende Marktwerte, Schätzungen, Preisverläufe und Exemplare bleiben unverändert.
