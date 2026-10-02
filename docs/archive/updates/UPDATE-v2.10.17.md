# GameCollector / Collector v2.10.17

## Yu-Gi-Oh!-Suche

- Deutsche Yu-Gi-Oh!-Treffer werden jetzt konsequent als deutsche Lokalisierung angezeigt und gespeichert.
- Bei „Alle Sprachen“ wird Deutsch bevorzugt; englische Treffer dienen nur als Fallback zur Identifikation und erzeugen keine doppelten EN/DE-Treffer mehr.
- Nach einer englischen Fallback-Identifikation lädt Collector die Karte erneut über ihre sprachunabhängige Karten-ID auf Deutsch.
- Alle vom Provider bekannten Printings/Sets einer gefundenen Karte bleiben auswählbar.
- Moderne EN-Referenzcodes werden für deutsche/französische/italienische/portugiesische/spanische physische Ausgaben lokalisiert dargestellt; der EN-Code bleibt intern als Referenz erhalten.
- Direkte DE-Setcodes wie `YGLD-DEC04` werden weiterhin über den EN-Referenzcode identifiziert, aber als eingegebene physische Ausgabe gespeichert.
- Passcode-, Namens- und Setcode-Suche verwenden dieselbe Lokalisierungslogik.

## Regressionstests

- `Schweigsamer Schwertkämpfer LV7` -> deutscher Name, deutsche Ausgabeauswahl.
- `Schweigsamer Magier LV8` -> deutscher Name.
- `Silent Magician LV8` -> weiterhin auffindbar.
- `YGLD-DEC04` -> Identifikation über `YGLD-ENC04`, Speicherung als `YGLD-DEC04`.
- `YGLD-ENC04` -> englische physische Ausgabe bleibt möglich.

Hinweis: YGOPRODeck liefert Kartenbilder nur auf Englisch. Die Bilder werden wie bisher lokal gecacht.
