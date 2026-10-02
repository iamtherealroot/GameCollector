# Bibo installieren

## Voraussetzungen

- Linux mit Root-/sudo-Zugang
- Docker Engine mit Docker Compose v2
- `tar`, `flock` und `openssl`
- `unzip` zum Entpacken des Release-Pakets
- Python 3 für Updates

## Release herunterladen und starten

Lade das gemeinsame Installations-/Updatepaket aus den [GitHub-Releases](https://github.com/iamtherealroot/GameCollector/releases/latest) herunter. Entpacke es außerhalb des Zielverzeichnisses, zum Beispiel in deinem Downloadordner:

```bash
unzip Bibo-v4.7.0.zip
cd Bibo-v4.7.0
sudo bash install.sh
```

Bei einer Neuinstallation fragt der Installer Benutzername und Passwort für das erste Administratorkonto ab. Interaktiv muss das Passwort mindestens zehn Zeichen haben. Es gibt kein voreingestelltes `admin/admin`-Passwort.

Der Installer erzeugt Datenbankpasswort und Anwendungsschlüssel, erstellt eine geschützte `.env` und startet PostgreSQL, Webanwendung und Scheduler. Abschließend prüft er den Deep-Healthcheck und die installierte Version.

Standardmäßig erreichst du Bibo unter `http://SERVER-IP:8095`.

## Anderen Pfad oder Port wählen

```bash
sudo BIBO_INSTALL_DIR=/opt/bibo BIBO_APP_PORT=8095 bash install.sh
```

Bei einer vorhandenen Installation muss `BIBO_INSTALL_DIR` auf deren tatsächliches Verzeichnis zeigen. Ohne Angabe bleibt es `/opt/gamecollector`.

| Variable | Verwendung |
|---|---|
| `BIBO_INSTALL_DIR` | Zielpfad für Neuinstallation oder Update |
| `BIBO_APP_PORT` | Port bei einer Neuinstallation; Standard `8095` |
| `BIBO_TZ` | Zeitzone bei einer Neuinstallation; Standard `Europe/Berlin` |
| `BIBO_ADMIN_USERNAME` | Erstbenutzer bei einer Neuinstallation; Standard `admin` |
| `BIBO_ADMIN_PASSWORD` | Erstpasswort für eine unbeaufsichtigte Neuinstallation |

Für unbeaufsichtigte Installationen muss das Erstpasswort gesetzt sein. Zugangsdaten gehören nicht in veröffentlichte Skripte oder Repository-Dateien.

## Bestehende Installation

Sind `.env` und `docker-compose.yml` im Ziel vorhanden, erkennt derselbe Installer den Update-Modus. Ein teilweise eingerichtetes oder anderweitig belegtes Zielverzeichnis wird abgewiesen.

Das Paket wird separat entpackt und von dort ausgeführt. Ein Start direkt aus dem Zielverzeichnis ist nicht vorgesehen. Die Routine übernimmt die Dateien aus dem entpackten Paket; sie führt keinen `git pull` aus und benötigt kein `--adopt`.

Details: [Update & Wiederherstellung](UPDATES.md).

## Daten und Konfiguration

| Ort | Inhalt |
|---|---|
| `/opt/gamecollector/app` | Anwendungscode und statische Dateien |
| `/opt/gamecollector/.env` | Zugangsdaten und Konfiguration, Dateirechte `600` |
| Docker-Volume für PostgreSQL | Datenbank; tatsächlicher Name hängt vom Compose-Projekt und seiner Konfiguration ab |
| `/opt/gamecollector/uploads` und `app/static/uploads` | Uploadpfade, abhängig vom Bereich und der bestehenden Konfiguration |
| `/opt/gamecollector/backups` | Updatebackups einschließlich Programmstand und Datenbankdump |

## Reverse Proxy und HTTPS

Bibo kann hinter Nginx Proxy Manager, Caddy oder einem anderen Reverse Proxy betrieben werden. Bei durchgängigem HTTPS kann in `.env` gesetzt werden:

```dotenv
COOKIE_SECURE=1
```

Danach die Anwendung neu erstellen:

```bash
cd /opt/gamecollector
sudo docker compose up -d --force-recreate web scheduler
```

## Optionale Anbieter

Metadaten- und Preisquellen benötigen je nach Anbieter persönliche API-Zugänge. eBay wird über die Kontoeinstellungen konfiguriert, RAWG optional über `RAWG_API_KEY` in `.env`. Lokale Verwaltung und manuelle Schätzwerte bleiben ohne diese Zugänge nutzbar.
