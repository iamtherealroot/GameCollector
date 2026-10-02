# GameCollector v2.11.0

## Yu-Gi-Oh! Set-/Deck-Schnellerfassung

- Neuer Bereich „Yu-Gi-Oh! Set/Deck hinzufügen“.
- Präfixe wie `YGLD-DE` laden die zugehörigen physischen deutschen Ausgaben als Checkliste.
- „Alle auswählen“, „Nur fehlende“ und „Keine“.
- Die Auswahl wird nacheinander hinzugefügt, damit große Sets keinen einzelnen langen Webrequest erzeugen.
- Live-Fortschritt und Fehlerstatus pro Karte.
- Bereits vorhandene identische Ausgaben werden erkannt; bei bewusster Auswahl wird die Menge erhöht.
- Karten bleiben einzelne Sammlungsobjekte mit physischem Setcode, Sprache, Rarität und Marktwert.
- Exakte Setcode-Auflösung bleibt fail-safe; keine fuzzy Kartenidentität.

Hinweis: Sprachspezifische deutsche Kartenbilder sind noch nicht Bestandteil dieses Releases; falls kein sprachspezifisches Bild vorliegt, bleibt das vorhandene YGOPRODeck-Bild erhalten.
