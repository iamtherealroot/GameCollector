# Collector v2.14.4

Filmreihen-Reparaturrelease.

- Film und Filmreihe sind strikt getrennte Identitäten.
- TMDB `belongs_to_collection` / Collection-ID ist die kanonische Filmreihen-ID.
- Alle Filmreihen können über „Alle Filmreihen aktualisieren“ neu abgeglichen werden.
- Jede Filmreihe besitzt wieder „Sammlung aktualisieren“.
- Legacy-Einträge mit `collection_name` werden gegen TMDB-Collections abgeglichen.
- Einzelne Filme bleiben einzelne Werke (z. B. Ted und Ted 2), werden aber derselben Reihe zugeordnet.
- Explizite Mehrfilm-Boxen wie „Trilogie 1-3“ können mehrere TMDB-Werke abdecken, ohne den physischen Bestand zu duplizieren.
- Keine persönlichen Bestandsdaten werden überschrieben oder gelöscht.
