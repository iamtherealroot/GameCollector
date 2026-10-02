# GameCollector v2.12.2

## Dauerhafter Fix: zentrale EAN/UPC/GTIN/ISBN-Erkennung

- Die globale Dashboard-Suche erkennt numerische Produktcodes jetzt vor der lokalen Volltextsuche.
- EAN-8, UPC-A, EAN-13, GTIN-14 und ISBN-10 werden an den bestehenden zentralen `/identify/<code>`-Workflow übergeben.
- Damit greifen dieselben Provider- und Medienpfade für Games, Film/TV, Bücher, Musik sowie Hardware/Zubehör.
- Ein unbekannter Barcode endet nicht mehr fälschlich nur mit „In deiner Sammlung wurde nichts Passendes gefunden“.
- Normale Textsuchen bleiben unverändert.
- Die Lösung ist zentral im Dashboard-Routing umgesetzt, damit neue Sammlungsbereiche nicht erneut einen eigenen Barcode-Sonderfall benötigen.
