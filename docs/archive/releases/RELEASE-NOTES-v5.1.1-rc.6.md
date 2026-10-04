# Bibo 5.1.1-rc.6

Unveröffentlichter Testkandidat. Enthält alle Änderungen aus RC.1 bis RC.5.

- Fünf klar beschriftete Hauptkacheln für Startseite, Sammlung, Hinzufügen, Werte und Menü. Aktiver Bereich und Tastaturfokus werden hervorgehoben. Leser sehen nur die für sie verfügbaren Aktionen.
- Einheitliche lokale SVG-Icons statt uneinheitlicher Schriftzeichen in der Navigation. Ohne zusätzliche Bibliothek oder externe Anfragen.
- Das Menü enthält Funktionskacheln mit Icon, Titel und kurzer Erklärung. Desktop und Handy verwenden denselben Funktionskatalog. Kleine Handys zeigen eine Spalte, größere Bildschirme zwei.
- Die Funktionensuche steht auch im Desktop-Menü bereit. Mehrere passende Gruppen bleiben bei einer Suche geöffnet. Escape und Klick außerhalb schließen das Menü weiterhin.
- Im erweiterten Medienassistenten liegt zwischen Staffelauswahl und Zustand ein zusätzlicher Abstand von 1rem.

Die vom Nutzer bestätigten Easter-Egg-Animationen bleiben auf dem Stand von RC.5. Die isolierte Testumgebung benötigt weiterhin separat eingerichtete API-Zugangsdaten, einschließlich TMDB.

## Prüfung

Bestehende Prüfungen für Navigation und Berechtigungen, Dashboard, einfachen/erweiterten Medienassistenten sowie JavaScript-Prüfungen. Die Darstellung auf dem Nutzergerät wird im SSH-Testbetrieb geprüft.
