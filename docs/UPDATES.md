# Bibo aktualisieren und wiederherstellen

## Standardupdate

Lade das neue Release-Paket herunter und entpacke es außerhalb der laufenden Installation:

```bash
unzip Bibo-v4.6.6.zip
cd Bibo-v4.6.6
sudo bash install.sh
```

Der Installer erkennt `/opt/gamecollector/.env` und `docker-compose.yml` und führt das Update durch. Für einen anderen bestehenden Zielpfad:

```bash
sudo BIBO_INSTALL_DIR=/opt/bibo bash install.sh
```

## Ablauf

1. Installationssperre setzen und Voraussetzungen prüfen.
2. Programmstand als `code.tar.gz` und `.env` als `env.backup` sichern.
3. PostgreSQL-Dump als `database.sql` erstellen.
4. Release-Dateien übernehmen; bestehende Konfiguration und Uploads erhalten.
5. Python-Syntax und Compose-Konfiguration prüfen, Web und Scheduler neu bauen.
6. Deep-Healthcheck und installierte Version prüfen.

Das Backup liegt unter `backups/update-vVERSION-ZEITSTEMPEL/`. Bei einem vom Fehlerhandler erfassten Updatefehler versucht die Routine, Programmstand und Konfiguration zurückzusetzen und die Dienste neu zu starten. Eine automatische Rücksicherung des Datenbankdumps erfolgt dabei nicht.

Der Installer aktualisiert aus dem entpackten Paket. Er führt kein `git pull` aus.

## Sicherungen aufbewahren

Kopiere wichtige Sicherungen zusätzlich auf einen anderen Datenträger. Das lokale Updatebackup ersetzt keine externe Sicherung. `docker compose down -v` löscht die Compose-Volumes und darf für ein normales Update nicht verwendet werden.

## Datenbank manuell wiederherstellen

Wähle einen zum Programmstand passenden Dump. Eine Rücksicherung ersetzt Datenbankinhalte; sichere den aktuellen Stand vorher separat.

Zuerst Schreibzugriffe stoppen:

```bash
cd /opt/gamecollector
sudo docker compose stop web scheduler
```

Den ausgewählten Dump zurückspielen (`UPDATE-ORDNER` durch den tatsächlichen Backupordner ersetzen):

```bash
sudo docker compose exec -T db sh -lc \
  'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < /opt/gamecollector/backups/UPDATE-ORDNER/database.sql
```

Die Dumps werden ohne `--clean` erzeugt. Eine vollständige Wiederherstellung benötigt daher eine leere Zieldatenbank mit denselben Zugangsdaten; der obige Import ist kein automatisches Zusammenführen mit einem bestehenden Bestand. Programmstand, Datenbank und Konfiguration müssen zusammenpassen.

Anschließend Dienste starten und Bereitschaft prüfen:

```bash
sudo docker compose up -d --build
curl -fsS http://127.0.0.1:8095/health/deep
```
