# GameCollector v2.14.6

PokéCollector-Wertsynchronisierung korrigiert.

- Der von PokéCollector gelieferte Portfolio-Gesamtwert ist für Pokémon die alleinige Gesamtsumme.
- Collector-Startseite, Sammelkartenansicht, Hauptdashboard und Gesamtwert-Snapshots verwenden dieselbe zentrale Berechnung.
- Einzelkartenwerte bleiben für Detailansichten und Sortierungen erhalten, werden jedoch nicht zusätzlich zur Portfoliosumme addiert.
- Magic: The Gathering und Yu-Gi-Oh! werden weiterhin getrennt bewertet und zur gesamten Sammelkartensumme addiert.
- Ältere Datensätze mit der Quelle „PokéCollector“ werden zuverlässig als Pokémon erkannt.
- Datenbank, `.env`, Uploads und Docker-Volumes bleiben unverändert erhalten.
