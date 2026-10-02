# Collector v2.10.13

## Schwerpunkt: Magic-Printings und schnellere Sammlungspflege

- Magic-Suche auf konkrete Drucke/Artworks erweitert.
- Deutsche Standardländer werden auf ihre Oracle-Identität aufgelöst: Ebene, Insel, Sumpf, Gebirge und Wald.
- Künstler kann direkt im Suchtext (z. B. `Ebene Rob Alexander`) oder als eigener Filter angegeben werden.
- Magic-Treffer zeigen Set, Setcode, Sammlernummer, Künstler und Erscheinungsjahr.
- Unterschiedliche Scryfall-Printing-IDs bleiben getrennte Sammlungsobjekte; echte identische Duplikate erhöhen weiterhin die Menge.
- Suchparameter bleiben beim Rücksprung aus einer Karte erhalten.
- Globale Collector-Suche ergänzt um Sortierung und TCG-Filter; Mengen >1 werden sichtbar.
- Qualitätscheck umfasst nun auch Filme, Serien, Bücher, Musik und Sammelkarten (Cover, Provider, Wert sowie Karten-Set/-Nummer/TCG).
- Der Kartenscanner ist aus der Oberfläche entfernt; der alte Scanner-Aufruf leitet zur Kartensuche um.
- Bestehende v2.10.12-Funktionen (Pokémon-Preise via PokéCollector, globale Suche, automatische Karten-Mengenführung) bleiben erhalten.

## Installation

Das Paket wie gewohnt nach `/opt/gamecollector/updates/v2.10.13` entpacken und dort `bash install.sh` ausführen. Der Installer sichert den aktuellen Stand, übernimmt das lokale Paket, baut die Container neu und prüft anschließend den Healthcheck.
