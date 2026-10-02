# Bibo v3.1.0 installieren

Die Version ist kumulativ. Eine vorhandene Bibo-Installation kann direkt von 3.0.10 oder einer späteren Zwischenversion aktualisiert werden.

```bash
cd $HOME/Downloads
unzip -o Bibo-v3.1.0-update.zip
cd Bibo-v3.1.0
sudo bash install.sh
```

Das Installationsskript erstellt vor der Aktualisierung ein Datenbank- und Upload-Backup, migriert das Schema und prüft anschließend Version und Gesundheitsstatus.
