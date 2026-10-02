# GameCollector v0.7.6 FINAL

## Schwerpunkt
Data Quality & Fast Entry – schnelleres Befüllen, konservative Dublettenerkennung und robustere Metadatenpflege.

## Änderungen

- EAN/UPC-Dublettenschutz beim Scanner, manuellen Bearbeiten und Import.
- Mehrere physische Exemplare derselben Ausgabe bleiben ausdrücklich erlaubt.
- Dublettenerkennung priorisiert EAN/UPC; geteilte RAWG-IDs sind nur noch ein Hinweis, kein automatischer Merge-Grund.
- „Kein Duplikat“ kann Fehlalarme im Qualitätscheck dauerhaft ausblenden.
- Identifizieren 2.0: lokaler/deutscher Titel bleibt standardmäßig erhalten; Übernahme einzelner Metadatenfelder möglich.
- RAWG-Sammeldatensätze dürfen mehreren getrennten Katalogspielen zugeordnet werden (z. B. Pokémon Diamant/Perl).
- Plattformanzeige in der Identifizieren-Suche wurde korrigiert; „Plattform passt“ basiert auf den tatsächlich von RAWG gelieferten Plattformen.
- Interaktive Coversuche und lokale Speicherung ausgewählter Cover.
- Region, Sprache und Edition sind getrennte Katalogfelder.
- EAN/UPC-Status auf der Detailseite und zentraler Datenqualitätscheck.
- Schnellbearbeitung für häufige Exemplarwerte.
- Verbesserter Scanner-Workflow für bereits bekannte Barcodes und weitere Exemplare.
- Datenbank-Statusseite mit Abdeckung wichtiger Metadaten.
- Geldfelder akzeptieren deutsche und internationale Schreibweisen, z. B. `100,00`, `100.00`, `1.000,00` und `1,000.00`.
- Eigener Schätzwert hat Vorrang vor dem automatischen Marktwert; der automatische Wert bleibt als Referenz sichtbar.
- Sammlungswert, Exporte, Sortierung und Wertentwicklung nutzen denselben Vorrang des manuellen Schätzwerts.
- Beim Speichern eines Sammlungswerts wird ein neuer Gesamtwert-Snapshot angelegt.
- Pokémon-Hauptreihe wird unabhängig von RAWG-Sammeldatensätzen als einzelne Spiele geführt und nach Generation I–IX gruppiert.
- Pokémon Diamant und Pokémon Perl, X und Y usw. können unabhängig voneinander als „Besitzt“ markiert werden.
- New Pokémon Snap befindet sich in der Unterreihe „Pokémon Snap“ und nicht in der Hauptreihe.
- Unicode-/Umlaut-Normalisierung für Serien- und Titelabgleiche verbessert.

## Datenbank

Bestehende PostgreSQL-Daten und das Docker-Volume bleiben erhalten. Beim Start ergänzt GameCollector fehlende Schemafelder in-place. Es wird kein Volume gelöscht.

## Installation

Das Update-Paket nach `$HOME/Downloads/` kopieren und unter `/opt/gamecollector/updates/v0.7.6/` entpacken. Anschließend `install.sh` ausführen.
