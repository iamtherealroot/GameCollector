# GameCollector v2.14.7

PokéCollector-Preissynchronisierung exakt angeglichen.

- Pokémon-Karten verwenden denselben Cardmarket-7-Tage-Durchschnitt (`price_avg7`) wie die PokéCollector-Oberfläche.
- Spezielle Holo-/Illustration-Rare-Karten verwenden bei fehlendem separaten Holo-Durchschnitt den kanonischen 7-Tage-Wert der Karte.
- Abweichende TCGPlayer-Holo-Marktwerte werden nicht mehr vor dem PokéCollector-Primärpreis verwendet.
- Liefert `/api/collection/` keinen Portfolio-Gesamtwert, berechnet GameCollector ihn nach einem fehlerfreien Sync aus `price_avg7 × Menge`.
- Einzelkarten, Pokémon-Kachel, Sammelkartenansicht, Dashboard und Gesamtwert verwenden danach dieselbe Preisbasis.
- Datenbank, `.env`, Uploads und Docker-Volumes bleiben erhalten.
