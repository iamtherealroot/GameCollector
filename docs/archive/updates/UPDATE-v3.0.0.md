# Bibo v3.0.0

GameCollector wird sichtbar zu **Bibo**. Interne Installationspfade und bestehende
Datenbanktabellen bleiben absichtlich kompatibel.

## Neu

- neues Bibo-Logo, App-Icon, Favicons und PWA-Name
- gemeinsame **Bibliothek** für Spiele, Filme, TV-Serien, Bücher, Musik,
  Sammelkarten, Hardware und Zubehör
- neue, medienunabhängige Struktur aus **Werk → Ausgabe/Modell → Exemplar**
- gemeinsame Suche und Filter nach Bereich und Besitzstatus
- einheitliche Wertanzeige mit bestehender Priorität
  `fixierter Wert → automatischer Wert → eigene Schätzung`
- bestehende Einzelbearbeitung, Serienlogik, Bilder und Preisfixierungen bleiben
  über direkte Links erreichbar

## Sichere Migration

Die neuen Bibo-Tabellen sind ein reversibles Register über den vorhandenen
Daten. Bestehende IDs werden weder geändert noch gelöscht. Fehlende Quellen
werden im Register nur als inaktiv markiert. `/opt/gamecollector`, Docker-Namen,
`.env`, Uploads und Datenbank bleiben unverändert.

## Installation

```bash
cd /
mkdir -p /opt/gamecollector/updates/v3.0.0
unzip $HOME/Downloads/Bibo-v3.0.0-update.zip \
  -d /opt/gamecollector/updates/v3.0.0
cd /opt/gamecollector/updates/v3.0.0/Bibo-v3.0.0
chmod +x install.sh
./install.sh
```

