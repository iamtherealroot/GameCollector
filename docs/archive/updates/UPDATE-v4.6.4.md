# Bibo v4.6.4

Dieses Wartungsrelease trennt die Spielreihen vollständig nach aktiver Sammlung.

## Korrekturen

- Neue und leere Sammlungen übernehmen keine Spielreihen der ersten Sammlung mehr als `0/x`.
- Spielreihen werden aus den tatsächlich vorhandenen physischen Spielen der aktiven Sammlung aufgebaut.
- Sobald eine Reihe begonnen wurde, zeigt Bibo weiterhin den vollständigen bekannten Reihenkatalog und den korrekten Fortschritt an.
- Reihen-Erkennung und Reihen-Synchronisierung arbeiten ausschließlich für die aktive Sammlung.
- Globale Katalogdaten und Bestände anderer Sammlungen werden nicht verändert.

## Eigene Dashboard-Kategorien

- Die neue Kachel „Sammlungskategorie hinzufügen“ öffnet direkt das Anlegeformular auf der Startseite.
- Name, Symbol und Beschreibung können frei gewählt werden, beispielsweise Figuren, Brettspiele oder Modelle.
- Jede Kategorie erhält eine eigene Kachel mit Coverbildern, Objektzahl und Gesamtwert.
- Über die Kachel können neue Objekte unmittelbar dieser Kategorie zugeordnet werden.
- Bereits vorhandene eigene Objekte lassen sich beim Bearbeiten einer Kategorie zuweisen.
- Die Kategorien erscheinen auch einzeln im Bewertungsdashboard und gehören ausschließlich zur aktiven Sammlung.

## Installation

```bash
cd $HOME/Downloads
unzip -o Bibo-v4.6.4-update.zip
cd Bibo-v4.6.4
sudo bash install.sh
```
