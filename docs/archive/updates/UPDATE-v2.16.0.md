# Update auf GameCollector v2.16.0

## Installation

```bash
cd /opt/gamecollector/updates/v2.16.0
chmod +x install.sh
./install.sh
```

Das Installationsskript legt vor dem Austausch automatisch ein Backup an, übernimmt Datenbank und Uploads unverändert, baut die Container neu und prüft anschließend den Healthcheck sowie die gemeldete Version.

## Neu in dieser Version

- Konsolenreihen mit vollständigem deutschen Generationenkatalog und eigener Detailansicht
- vollständige Bourne-Hauptfilmreihe und kuratierte Fußball-Manager-Reihe
- manuelles „Nicht im Besitz“ für falsch erkannte Film- und Spielreihentitel
- persönlich anordenbares Bewertungs-Dashboard
- deutlich erweiterte globale Suche

## Hinweise zu Konsolenreihen

Eine Konsolengeneration zählt genau einmal. Slim-, OLED-, Speicher- und sonstige Modellvarianten sowie mehrere physische Exemplare werden in der Detailansicht unter der Generation zusammengefasst. Der Wert addiert weiterhin alle tatsächlich vorhandenen Exemplare.

## Rückkehr zur automatischen Erkennung

Ein manuell ausgeschlossener Reihen-Titel wird nicht gelöscht. Über „Automatische Erkennung wieder verwenden“ lässt sich die Korrektur jederzeit zurücknehmen.
