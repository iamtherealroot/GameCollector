# Update auf Bibo v3.0.9

Das Update legt automatisch eine Sammlung „Gemeinsam“ für den vorhandenen Bestand an. Bestehende Benutzer erhalten entsprechend ihrer bisherigen Rolle Zugriff. Anschließend können Systemadministratoren unter **Kontomenü → Nutzerverwaltung → Datenbanksteuerung** weitere Sammlungen anlegen und Rechte vergeben.

## Installation

```bash
mkdir -p /opt/gamecollector/updates
cd /opt/gamecollector/updates
unzip -o /pfad/zu/Bibo-v3.0.9-update.zip
cd Bibo-v3.0.9
sudo bash install.sh
```

Die Installation erstellt wie bisher vor der Aktualisierung ein Backup und führt die additive Schemaerweiterung beim Start aus.

## Rechte

- **Lesen:** Bestand, Suche und Auswertungen ansehen; keine Änderungen.
- **Bearbeiten:** Bestand, Metadaten, Reihen und Bewertungen pflegen.
- **Verwalten:** zusätzlich Zugriffe und Einstellungen der Sammlung verwalten.
- **Systemadministrator:** Benutzer und Sammlungen anlegen und alle Sammlungen verwalten.
