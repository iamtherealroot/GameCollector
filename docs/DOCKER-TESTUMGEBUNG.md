# Isolierte Docker-Testumgebung

Vor jedem Release den neuen Code zunächst getrennt von der Produktion testen. Docker Engine und Compose v2 sind erforderlich. Der Test nutzt **ausschließlich** das Projekt `bibo-release-test`, separate Docker-Volumes und Port `127.0.0.1:18095`. Es werden keine Produktionsdaten, Produktionsordner oder Produktions-Zugangsdaten eingebunden.

Im entpackten Paket:

```bash
bash scripts/docker-test.sh check
```

Das baut die Testcontainer und startet zuerst Postgres und den einmaligen Init-Dienst. Erst nach erfolgreicher Initialisierung startet Web; nach erfolgreichem Healthcheck startet der Scheduler (nicht bei importierten Produktionsdaten). Danach laufen die Regressionstests und SQL-Backup/Wiederherstellung in einer zusätzlichen Wegwerf-Testdatenbank. Die Wiederherstellungsdatenbank wird danach entfernt; die normale Testdatenbank bleibt erhalten. Der Runner nutzt SQLite für die bestehenden Integrationstests, der Webdienst läuft mit PostgreSQL. Beide Tests sind notwendig. Web und Scheduler legen beim App-Import keine Tabellen an.

Für manuelle Tests: `bash scripts/docker-test.sh up`. Login `test-admin` ohne Passwort; der Benutzername ist vorausgefüllt, das Loginfenster bleibt. Andere Nutzer brauchen weiterhin ihr Passwort. Das gelbe TESTUMGEBUNG-Banner unterscheidet die TU von der Produktion. Testdaten und interne Datenbank-/Signaturschlüssel bleiben für weitere Durchläufe erhalten. Zum Stoppen: `bash scripts/docker-test.sh down`. Diese Aktion löscht keine Testvolumes. Kein `down -v` für die Produktionsinstallation verwenden.

Bei einem entfernten Server einen SSH-Tunnel für Port 18095 nutzen; der Port ist absichtlich nicht im LAN oder Internet erreichbar. Niemals Testzugangsdaten in GitHub veröffentlichen.

## Manuelle Freigabeprüfung

- Menü auf Desktop und iPhone, Suche, aktive Bereiche, Bildschirmbreite und Tastatur.
- Feedback als Leser, Bearbeiter und Systemadministrator; Bilder und interne Notizen.
- Globale Top 10: ohne Freigabe leer, mit Anzeigenamen sichtbar, nach Widerruf sofort entfernt.
- Neuinstallation sowie Update über `install.sh` auf einer separaten Testmaschine prüfen. Dieser Container-Test startet den Host-Installer nicht.
- Bibo-Komplettbackup einschließlich privater Bilder erstellen und auf einer getrennten Testinstallation wiederherstellen. Der automatische Test prüft SQL; die vollständige Bild-/Dateiwiederherstellung ist zusätzlich erforderlich.
- Erst danach die ausdrückliche Release-Freigabe einholen.

Diese Testumgebung ist vorbereitet, aber in der Codex-Arbeitsumgebung mangels Docker noch nicht ausgeführt.

## Mit einer Bash-Datei vom Linux-Desktop starten und öffnen

Den separaten Starter `bibo-tu.sh` und `Bibo-v5.0.4.zip` nebeneinander auf dem Desktop-Rechner ablegen. Der Starter liegt auch im Paket unter `scripts/`. Beispiel mit einem SSH-Ziel, das sudo benutzen darf:

```bash
bash bibo-tu.sh --ssh benutzer@server
```

Der Starter überträgt beide Dateien in seinen temporären Uploadordner auf dem Server, ruft die Servervorbereitung mit sudo auf und entfernt danach nur diese beiden Uploadkopien. Bei `root@server` wird kein sudo benötigt. Auf dem Server wird ausschließlich `/opt/bibo-test/Bibo-v5.0.4` vorbereitet. Vorhandene Zugangsdaten werden aus dem bisherigen versionierten Testordner übernommen. Existierende Test-Volumes bleiben erhalten; falls Zugangsdaten fehlen, wird der Vorgang abgebrochen statt ein neues Passwort für das alte Volume zu setzen.

Anschließend öffnet der Starter einen nur lokal gebundenen SSH-Tunnel, prüft `/health/deep` auf den Testmodus und öffnet den Browser. Das Terminal muss offen bleiben. Enter oder Strg+C schließt nur den eigenen SSH-Tunnel; die TU bleibt auf dem Server bestehen. SSH und sudo können ihr normales Passwort verlangen, der Bibo-Login nicht. Keine SSH-Passwörter im Skript speichern. Hostschlüssel werden normal geprüft, nicht umgangen.

Für eine bereits laufende TU:

```bash
bash bibo-tu.sh --ssh benutzer@server --open-only
```

Weitere Optionen: `--package /pfad/Bibo-v5.0.4.zip`, `--port 18096` (lokaler Ersatzport), `--no-open` (Adresse ausgeben, keinen Browser starten). `--help` zeigt den Aufruf. Für reine Vorbereitung ohne GUI direkt auf dem Server: `sudo bash bibo-tu.sh --server /pfad/Bibo-v5.0.4.zip`.

Der Starter führt weder `install.sh` für die Produktion noch automatisch eine Produktionsdatenmigration aus.

## Produktionsdaten in den Test kopieren

Im separat entpackten Testpaket, **nicht** in `/opt/gamecollector`:

```bash
bash scripts/docker-test.sh up
bash scripts/docker-test.sh migrate /opt/gamecollector --confirm-test-overwrite
```

Der Befehl liest nur die laufenden Produktionscontainer `db` und `web`. Im Test werden Web und Scheduler angehalten und SQL sowie beide Bildvolumes unter `test-runtime/import-…` privat gesichert. Produktions-SQL wird erst in einer Staging-Datenbank wiederhergestellt und geprüft, anschließend nur die Testdatenbank umgeschaltet. Die vorherige Testdatenbank bleibt zusätzlich erhalten. Bei Fehler bleibt die Test-Webapp gestoppt; die Sicherungen und Restore-Logs bleiben zur Diagnose erhalten. Bildkopien werden sicher extrahiert und zusammengeführt, nicht gelöscht. Während der Kopie keine Bilder in der Produktion ändern; SQL und Bilder sind kein gemeinsamer atomarer Snapshot.

Produktionsnutzer können sich im Test mit ihren bisherigen Passwörtern anmelden. Zusätzlich kann der Testbootstrap `test-admin` anlegen, sofern dieser Nutzer noch nicht existiert. Test-Geheimnisse bleiben getrennt; verschlüsselte Integrationseinstellungen müssen mit Test-Zugangsdaten neu eingerichtet werden. Keine automatischen Preisabfragen: Der Test-Scheduler bleibt nach dem Import auch beim nächsten `up` deaktiviert. Manuelle externe Abfragen können weiterhin stattfinden; keine Produktiv-API-Zugänge im Test eintragen.

Auf deinem Rechner den Tunnel starten:

```bash
ssh -N -L 18095:127.0.0.1:18095 root@PokeCollector
```

Dann im Browser `http://127.0.0.1:18095` öffnen. Die Sicherungen enthalten private Nutzerdaten und dürfen nicht hochgeladen werden. Dieser Import ist nur **Produktion → Test**, kein Update-/Zurückmigrationsbefehl für die Produktion.
