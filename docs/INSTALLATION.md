# Installation und Migration

## Neue Installation

Benötigt werden Git, Docker Engine, Docker Compose v2 und `openssl`.

```bash
sudo git clone https://github.com/iamtherealroot/GameCollector.git /opt/gamecollector
sudo bash /opt/gamecollector/install.sh
```

Der Installer erstellt `/opt/gamecollector/.env` mit zufälligen Datenbank- und
Anwendungsschlüsseln, startet PostgreSQL und wartet auf den tiefen Healthcheck.
Die vorläufige Erstkennung lautet `admin` / `admin`. Nach dem ersten Login
erzwingt GameCollector ein neues Passwort und sperrt bis dahin alle anderen
Bereiche.

Standardmäßig heißt der erste Benutzer `admin`. Für eine eigene Kennung bei
einer frischen Datenbank:

```bash
sudo env ADMIN_USERNAME=meinadmin ADMIN_PASSWORD='Sicheres-Passwort-2026' \
  bash /opt/gamecollector/install.sh
```

Das Passwort muss mindestens acht Zeichen lang sein und darf in dieser
Bootstrap-Variable keine Leerzeichen enthalten. Bestehende Benutzer werden bei
einer Installation oder einem Update niemals überschrieben.

Wichtige Verzeichnisse:

| Pfad | Inhalt | Von Git verändert? |
|---|---|---:|
| `/opt/gamecollector/app` | Anwendungscode | Ja |
| `/opt/gamecollector/.env` | Geheimnisse und Konfiguration | Nein |
| `/opt/gamecollector/uploads` | lokale Cover und Uploads | Nein |
| Docker-Volume `gamecollector_postgres_data` | PostgreSQL-Datenbank | Nein |
| `/opt/gamecollector/backups` | Updatebackups | Nein |

## Bestehende Installation übernehmen

Die Übernahme ist ausdrücklich für eine vorhandene Installation unter
`/opt/gamecollector` vorgesehen. Das Skript erkennt das tatsächlich vom
laufenden Datenbankcontainer verwendete Docker-Volume und trägt dessen Namen
in `.env` ein.

```bash
git clone https://github.com/iamtherealroot/GameCollector.git /tmp/gamecollector-public
cd /tmp/gamecollector-public
sudo bash install.sh --adopt
```

Vor dem Überschreiben der Programmdateien werden Code, `.env` und Datenbank
unter `/opt/gamecollector/backups/adoption-*` gesichert. Uploads und das
PostgreSQL-Volume bleiben an ihrem Ort. Die Übernahme bricht ab, wenn keine
gültige bestehende Docker-Compose-Installation erkannt wird.

## Reverse Proxy und HTTPS

Hinter Nginx Proxy Manager, Caddy oder einem anderen HTTPS-Reverse-Proxy:

```dotenv
COOKIE_SECURE=1
```

Danach anwenden:

```bash
cd /opt/gamecollector
sudo docker compose up -d --force-recreate web scheduler
```

## Provider

- eBay Browse API: Zugangsdaten im Nutzermanagement eintragen.
- RAWG: optional `RAWG_API_KEY` in `.env` setzen.
- Ohne optionale Schlüssel bleiben lokale Verwaltung und manuelle Werte nutzbar.
