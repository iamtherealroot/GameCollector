# Collector v2.10.14

## Änderungen
- TCG-übergreifende Kartenfilter: Sprache, Künstler/Illustrator, Set/Setcode, Kartennummer und Variante/Finish (soweit Providerdaten vorhanden sind).
- Filter bleiben beim Hinzufügen bzw. Zurückkehren zur Kartensuche erhalten.
- Pokémon-, Magic- und Yu-Gi-Oh!-Suche teilen dieselbe Filteroberfläche; Yu-Gi-Oh!-Setausgaben können eingegrenzt werden.
- YGOPRODeck-Anfragen vermeiden die fehlerhafte Sprachparameter-Kombination, die HTTP 400 auslösen konnte.
- Startseite zeigt je vorhandenem TCG Kartenanzahl und Gesamtwert, inklusive quantity.
- „Alle bewerten“ läuft als Hintergrundjob mit Fortschrittsseite; langsame PokéCollector/Scryfall/eBay-Aufrufe blockieren den HTTP-Request nicht mehr.
- Pokémon-Preise bleiben ausschließlich PokéCollector-gesteuert; der Hintergrundlauf synchronisiert PokéCollector einmal und bewertet Pokémon nicht zusätzlich über eBay.
- Mobile Kartenfilter kompakter dargestellt.
- Kartenscanner bleibt aus der Oberfläche entfernt.

## Sicherheit
`.env`, Datenbanken, Uploads und Backups sind nicht Bestandteil des Updatepakets und werden vom Installer geschützt.
