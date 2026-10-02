# Update auf Bibo v3.0.4

1. ZIP nach `/opt/gamecollector/updates/` kopieren und entpacken.
2. In das entpackte Verzeichnis wechseln.
3. Update starten:

   ```bash
   sudo bash install.sh
   ```

Der Installer erstellt vor der Aktualisierung ein Code- und Datenbank-Backup, baut Web und Scheduler neu und prüft anschließend den Healthcheck sowie die gemeldete Version. Bei einem Fehler wird der vorherige Programmstand automatisch wiederhergestellt.

Benutzerdaten, Uploads, `.env`, Backups und bestehende Datenbankinhalte bleiben erhalten.
