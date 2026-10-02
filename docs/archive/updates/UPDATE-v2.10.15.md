# Collector v2.10.15

## Änderungen
- Kartensuche als echtes Multi-TCG-Frontend: „Alle TCGs“ fragt Pokémon, Magic und Yu-Gi-Oh! unabhängig voneinander ab; ein Providerfehler verhindert die übrigen Treffer nicht.
- Yu-Gi-Oh!-Setcodes wie `YGLD-DEC04` werden über den dafür vorgesehenen YGOPRODeck-Setcode-Endpunkt aufgelöst; 8-stellige Passcodes und Namenssuche bleiben erhalten.
- Kartenfilter bleiben providerneutral: Sprache, Künstler/Illustrator, Set/Setcode, Kartennummer und Variante/Finish.
- Suchformular neu als responsives Raster: keine über den Container laufenden Felder; mobil einspaltige, gut bedienbare Filter.
- TCG-Aufschlüsselung auf der Startseite: Name und Kartenanzahl links, jeweiliger Gesamtwert rechtsbündig.
- Der Magic-spezifische Infokasten wurde durch einen neutralen Suchhinweis ersetzt.

## Regression
- v2.10.14 Hintergrundbewertung, PokéCollector-Preisführung für Pokémon und globale Collector-Funktionen bleiben erhalten.

## Sicherheit
`.env`, Datenbanken, Uploads und Backups sind nicht Bestandteil des Updatepakets und werden vom Installer geschützt.
