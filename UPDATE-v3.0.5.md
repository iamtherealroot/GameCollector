# Update auf Bibo v3.0.5

1. ZIP nach `/opt/gamecollector/updates/` kopieren und entpacken.
2. In das entpackte Verzeichnis wechseln.
3. Update starten:

   ```bash
   sudo bash install.sh
   ```

Der Installer sichert Programm und Datenbank, aktualisiert Web und Scheduler und prüft anschließend Healthcheck und Versionsnummer. Bei einem Fehler wird der vorherige Programmstand automatisch wiederhergestellt.

Benutzerdaten, Uploads, `.env`, Backups und bestehende Datenbankinhalte bleiben erhalten.
