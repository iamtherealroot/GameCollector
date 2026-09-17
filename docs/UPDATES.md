# Updates und Wiederherstellung

## Standardupdate

```bash
sudo bash /opt/gamecollector/install.sh
```

Der Ablauf ist absichtlich streng:

1. Installationssperre setzen und Voraussetzungen prüfen.
2. Lokale Änderungen an versionierten Dateien ausschließen.
3. Code, `.env` und PostgreSQL sichern.
4. `git fetch` und ausschließlich Fast-Forward-Merge von `origin/main`.
5. Images neu bauen und Dienste starten.
6. Tiefen Healthcheck ausführen.
7. Bei einem Fehler auf den vorigen Commit zurückgehen und Dienste neu starten.

Niemals `docker compose down -v` verwenden: `-v` würde das Datenbank-Volume
löschen.

## Bestimmten Branch verwenden

```bash
sudo GAMECOLLECTOR_BRANCH=main bash /opt/gamecollector/install.sh
```

## Backup manuell wiederherstellen

Zuerst Dienste anhalten, ohne Volumes zu löschen:

```bash
cd /opt/gamecollector
sudo docker compose stop web scheduler
```

Datenbankdump zurückspielen:

```bash
cat /opt/gamecollector/backups/UPDATE-ORDNER/database.sql | \
  sudo docker compose exec -T db sh -lc \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

Danach Dienste neu bauen und Healthcheck prüfen:

```bash
sudo docker compose up -d --build
curl -fsS http://127.0.0.1:8095/health/deep
```
