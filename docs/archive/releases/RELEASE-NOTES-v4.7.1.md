# Bibo v4.7.1 – Symbolauswahl und flexibler Installer

Beim Anlegen und Bearbeiten eigener Sammlungskategorien stehen 20 Standardicons in einem Dropdown bereit. Über „Eigenes Emoji“ lässt sich ein eigenes Symbol eingeben. Vorhandene eigene Symbole bleiben beim Bearbeiten erhalten.

Die Löschbestätigung zeigt eine sauber ausgerichtete Checkbox, den Kategorienamen und den Hinweis, dass enthaltene Objekte erhalten bleiben. Auf kleinen Bildschirmen stehen die Schaltflächen untereinander.

Das Startskript `scripts/bibo-update-latest.sh` sucht lokale Pakete im Downloads-Ordner und das aktuelle stabile GitHub-Release. Die höchste Versionsnummer gewinnt; bei gleicher Version wird das lokale Paket bevorzugt. Lokale Pakete lassen sich auch ohne GitHub-Verbindung installieren. Vorhandene neuere Versionen werden nicht heruntergestuft.

Ein abweichender Downloadordner lässt sich über `BIBO_DOWNLOAD_DIR` angeben. Mit `BIBO_CHECK_ONLY=1` wird das Paket geprüft, ohne den Installer zu starten. GitHub-Pakete werden mit SHA256 geprüft; lokale Pakete verwenden eine vorhandene passende Prüfsummendatei. ZIP-Integrität und Anwendungsversion werden in beiden Fällen geprüft.

## Prüfungen

Kategorien-Integrationstests einschließlich Standard- und eigener Symbole, Formulartoken, Rechte, Sammlungstrennung und Objekterhalt; 108 Templates und 210 Routen; Startskript mit lokalem Paket, GitHub-Paket, Offlinebetrieb, vorhandener Version, Prüfsummen und falscher Paketversion geprüft. Eine visuelle Browserprüfung und Installation auf dem Produktionsserver wurden hier nicht durchgeführt.

## Installation und Update

`Bibo-v4.7.1.zip` außerhalb der bestehenden Installation entpacken und `sudo bash install.sh` starten. Das Paket enthält den vollständigen Quellcode. Die Änderungen benötigen keine Datenbankmigration.
