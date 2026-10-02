# GameCollector v2.14.8

PokéCollector-Portfolio und Einzelpreise werden aus derselben offiziellen Preisbasis synchronisiert.

- Der Gesamtwert kommt direkt aus `GET /api/dashboard/` (`total_value`).
- GameCollector übernimmt automatisch PokéCollectors aktuell ausgewähltes `price_field`, beispielsweise `trend` oder `avg7`.
- Holo und Reverse Holo folgen der PokéCollector-Fallbacklogik: ausgewählter Holo-Wert, ausgewählter Normalwert, Cardmarket-Durchschnitt.
- Falls der Dashboard-Endpunkt vorübergehend nicht erreichbar ist, bleibt der bisherige sichere Fallback aktiv.
- Datenbank, `.env`, Uploads und Docker-Volumes bleiben erhalten.
