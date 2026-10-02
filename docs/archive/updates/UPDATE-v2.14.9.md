# GameCollector v2.14.9

Letzte Korrektur der PokéCollector-Preissynchronisierung.

- GameCollector liest nach Möglichkeit die benutzerspezifische primäre Preisart aus PokéCollector.
- Der Dashboard-Endpunkt wird ausdrücklich mit diesem `price_field` aufgerufen.
- Für die aktuelle PokéCollector-Oberfläche wird `avg7` verwendet; der offizielle Dashboardwert beträgt damit `202,91 EUR` statt des parameterlosen `trend`-Werts von `217,32 EUR`.
- Einzelkarten und Gesamtwert verwenden dieselbe Preisart.
- Datenbank, `.env`, Uploads und Docker-Volumes bleiben erhalten.
