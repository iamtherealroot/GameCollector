# Bibo 4.0.0 – Gemeinsame Bibliothek

## Eine Struktur für alle Medien

- Einheitliches Register aus Werk, Reihe, Ausgabe und Exemplar.
- Eigene Werkseite mit Ausgaben, Mengen, Werten, Zustand, Vollständigkeit und Lagerort.
- Reihenbeziehungen für Spiele, Filme, Staffeln und Bücher.
- Deutsche Verfügbarkeit wird am Werk und an der Ausgabe geführt.
- Boxsets können mehrere logische Inhalte abdecken; ihr physischer Wert wird weiterhin nur einmal gezählt.
- Getrennte Originalmodule bleiben maßgeblich und vollständig bearbeitbar.

## Enthaltene Zwischenversionen

- 3.2.0: zentrale Prüf-Inbox.
- 3.3.0: mobile Stapel- und Barcode-Erfassung.
- 3.4.0: explizite Boxset-Abdeckung.
- 3.5.0: Dashboard-Wasserzeichen und Sammlungsassistent.

## Sichere Migration

Der Start ergänzt neue Tabellen und Spalten automatisch. Der Registerabgleich liest die bestehenden Einträge, verändert oder löscht sie jedoch nicht. Das Installationsskript erstellt vor dem Austausch der Anwendung ein Backup.
