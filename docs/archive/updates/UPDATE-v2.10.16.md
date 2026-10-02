# Collector v2.10.16

## Yu-Gi-Oh!-Lokalisierung und Printing-Suche

- YGOPRODeck wird für deutsche Kartennamen nativ mit `language=de` abgefragt.
- Bei „Alle Sprachen“ werden deutsche und englische Namenssuchen unabhängig ausgeführt.
- Lokalisierte physische Setcodes wie `YGLD-DEC04` werden intern nur für die Identifikation auf die YGOPRODeck-Referenz `YGLD-ENC04` abgebildet.
- Gespeichert bleibt immer der physische Setcode des Exemplars, z. B. `YGLD-DEC04`.
- Deutsche und englische Exemplare bleiben bei der Duplikaterkennung getrennt.
- Beim Hinzufügen wird der lokalisierte Kartenname aus dem YGOPRODeck-Sprachendpunkt geladen.
- YGOPRODeck/Cardmarket-Preisangaben werden als EUR-Referenz verwendet; USD-Setpreise werden nur als Fallback nach EUR umgerechnet.
- Metadaten speichern sowohl physischen Setcode als auch internen Referenzcode, damit spätere Preis-/Metadatenupdates reproduzierbar bleiben.

## Regressionstests

- `YGLD-DEC04` -> Identifikation über `YGLD-ENC04`, physischer Code bleibt `YGLD-DEC04`.
- `YGLD-ENC04` -> direkte englische Printing-Suche.
- `Silent Magician LV8` -> englische Namenssuche.
- `Schweigsamer Magier LV8` -> deutsche YGOPRODeck-Namenssuche.
