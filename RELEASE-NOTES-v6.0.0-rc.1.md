# Bibo 6.0.0-rc.1 – Einfach sammeln

Erster Prüfkandidat für Bibo 6.0. Die stabile Version bleibt 5.1.5.

- Sammlung: Listen- und Coveransicht, Titel- und Wertsortierung sowie zuletzt hinzugefügte Einträge.
- Ansicht, Bereich, Besitzstatus und Qualitätsfilter lassen sich je Nutzer und Sammlung speichern. Die Suche bleibt vorübergehend. Leser dürfen eigene Ansichtseinstellungen speichern.
- Mehrfachbearbeitung direkt aus der Sammlung: einzelne Exemplare oder die aktuelle Seite auswählen, Auswahl auf der Bearbeitungsseite prüfen und gemeinsam ändern.
- Mehrfachbearbeitung berücksichtigt ausschließlich ausgewählte Einträge innerhalb des gewählten Bereichs und Suchfilters. Fremde Sammlungen und Leserechte bleiben geschützt.
- Datenqualität: fehlende Cover, fehlender Zustand, fehlender Lagerort und mögliche doppelte Exemplare derselben Ausgabe als konkrete, filterbare Einträge. Wunschlisten und digitale Exemplare benötigen keinen physischen Zustand oder Lagerort. Keine automatische Zusammenführung.
- Gemeinsame Detailseite mit Besitzstatus, Wert, Zustand, Vollständigkeit und Lagerort. „Exemplar bearbeiten“ öffnet die gewählte Kopie, auch wenn ein Spiel mehrfach vorhanden ist. Vorlagen für weitere Spiele- und Medienexemplare sind direkt erreichbar.
- Gemeinsamer Einstieg unter /add und /find mit klaren Schritten, EAN-/Titelsuche und manueller Erfassung. Die bestehenden geprüften Anbieter- und Vorlagenwege bleiben eingebunden.
- Medienassistent und Spieleformular können nach erfolgreichem Speichern direkt zum nächsten Scan wechseln.
- Doppelt angezeigte Film-/Serientreffer in der EAN-Erkennung entfernt.

## Prüfung

Automatisierte Tests mit separaten SQLite-Datenbanken: Ansichten über erneute Anmeldung hinweg, getrennte Einstellungen pro Konto, Qualitätsfilter, exaktes Spieleexemplar, Vorauswahl und gefilterte Mehrfachänderungen, keine Änderungen an fremden Einträgen, Leserechte und Speichern vor dem nächsten Scan. Bestehende Erfassungs-, Vorlagen-, Dubletten-, Bestands- und Zugriffsprüfungen werden weiter ausgeführt.

Die visuelle Prüfung der neuen Ansichten auf Desktop und iPhone ist noch offen. Die automatische Browserinstallation war in der Entwicklungsumgebung nicht verfügbar. Kein Nachweis eines vollständigen Docker-Laufs für diesen Prüfkandidaten.

## Weitere Arbeit für 6.0

- Darstellung und Erfassung aller Medienarten in der Testumgebung praktisch abnehmen.
- Bereichsübergreifende Formulare weiter vereinheitlichen; Spezialangaben müssen erhalten bleiben.
- Globale Spiel-/Buchreihenprüfung separat entwickeln und am Katalog prüfen. Dieser Prüfkandidat führt keine automatische Reihenänderung aus.
- Kategorieänderungen zwischen unterschiedlichen Medienarten sind nicht Teil der gemeinsamen Bearbeitung. Bestehende Spezialfunktionen für eigene Kategorien bleiben erhalten.

## Testen

ZIP auf dem Rechner mit Docker entpacken und im Paketordner ausführen:

```bash
bash scripts/docker-test.sh check
```

Alternativ den vorhandenen TU-Starter für den Debian-Server verwenden. Diese Testversion nicht ungeprüft über die Produktion installieren.
