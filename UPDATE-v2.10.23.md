# GameCollector v2.10.23

- Fix: Yu-Gi-Oh!-Setcode-Treffer, die YGOPRODeck nicht in `card_sets` führt, lassen sich nun auch zur Sammlung hinzufügen.
- Der Add-Handler verwendet denselben exakten Printing-Resolver wie die Suche.
- Sicherheitsprüfung: Ein aufgelöstes Printing wird nur akzeptiert, wenn seine YGOPRODeck-Karten-ID exakt der ausgewählten Karte entspricht und der Referenz-Setcode exakt übereinstimmt.
- Der physische/lokalisierte Setcode (z. B. `YGLD-DEG01`) bleibt die Sammlungsidentität; der englische Referenzcode dient nur zur Provider-Auflösung.
- Die bestehende Release-Bereinigung nach erfolgreichem Healthcheck bleibt erhalten.
