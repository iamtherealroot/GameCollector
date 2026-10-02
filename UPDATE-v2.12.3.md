# GameCollector v2.12.3

Dauerhafter Stabilitäts- und Performance-Fix für die zentrale EAN-Identifikation.

- Medien-EANs werden klassifiziert, bevor fachfremde Provider abgefragt werden.
- Bereits durch den Medienpfad geladene Barcode-/eBay-Daten werden wiederverwendet statt erneut abgefragt.
- MusicBrainz wird bei erkanntem Film-/TV-Produkt nicht mehr zusätzlich abgefragt.
- Open Library wird nur noch für echte ISBN-10 bzw. ISBN-13 mit 978/979-Präfix abgefragt.
- Interaktive externe Requests haben kürzere Timeouts; Providerfehler bleiben ein fehlender Treffer statt den Gunicorn-Worker zu blockieren.
- Keine Erhöhung des Gunicorn-Timeouts.

Regressionen: 4010232052070 darf keinen Worker-Timeout/HTTP 500 mehr durch Open Library erzeugen; 4010232042972 darf bei erkanntem Video-Produkt nicht zusätzlich als Musik gesucht werden.
