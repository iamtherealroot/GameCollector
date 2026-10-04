# Bibo v4.7.0 – Eigene Sammlungskategorien verwalten

## Neu

- Name, Symbol und Beschreibung eigener Dashboard-Kategorien bearbeiten. Die Kategorie-ID bleibt dabei erhalten; vorhandene Objekte bleiben zugeordnet.
- Eigene Kategorien vom Dashboard oder aus ihrer Kategorieansicht entfernen.
- Bestätigungsseite zeigt, wie viele Objekte in der Kategorie enthalten sind. Beim Löschen bleiben alle Objekte unter „Weitere Sammlungen“ erhalten.
- Mehrere Objekte in der Übersicht markieren und gemeinsam in eine andere eigene Kategorie verschieben oder die eigene Kategoriezuordnung entfernen.
- „Alle angezeigten auswählen“, „Auswahl aufheben“ und sichtbarer Auswahlzähler. Bis zu 500 Einträge je Verschiebevorgang.
- Bearbeitungsrechte, aktive Sammlung und sitzungsgebundene Formulartoken schützen die Aktionen.
- Enthält eine Verschiebeanfrage fremde, fehlende oder nicht zum Bereich passende Einträge, wird sie vollständig abgewiesen.

Preise, Fotos, Notizen und sonstige Objektmetadaten bleiben bei Kategorieänderungen erhalten. Standardbereiche wie Filme, Bücher oder Games lassen sich mit diesen Aktionen nicht löschen.

## Installation & Update

Ein Paket für Neuinstallation und Update: `Bibo-v4.7.0.zip`. Außerhalb der bestehenden Installation entpacken und `sudo bash install.sh` starten. Eine Datenbankmigration ist für diese Funktionen nicht erforderlich.

## Prüfungen

Integrationstest für Bearbeiten, Mehrfachverschieben, leere und gefüllte Kategorien, Objekterhalt, Leserechte, Bestätigung, ungültige Anfragen und Sammlungstrennung. Templates, Routen und die wichtigsten angemeldeten Seiten wurden geprüft. Preisvergleichs-Regressionstests bleiben Bestandteil der CI.
