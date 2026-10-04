# Bibo 5.1.1-rc.1

Unveröffentlichter Testkandidat auf Basis von 5.1.0. Noch kein stabiles Release.

## Einfachere Bedienung

- Kompaktes Dashboard mit Sammlung, zentraler Suche und Scanner; zusätzliche Werkzeuge sind aufklappbar.
- Suche in der Reihenfolge: EAN oder Titel eingeben, Medienart auswählen, Treffer auswählen oder neu anlegen. Externe Katalogsuche wird ausdrücklich gestartet.
- Vereinfachte manuelle Medienerfassung mit Titel als einzigem Pflichtfeld und optionalen Details; erweiterter Assistent bleibt verfügbar.
- Nach dem Speichern direkt zum Eintrag und von dort zum nächsten Eintrag. Filter, Kategorie und Scrollposition bleiben beim Navigieren erhalten.
- Gelöschte Einträge lassen sich innerhalb von zehn Minuten wiederherstellen, einschließlich Preisverlauf und vorhandener Medienzuordnungen. Nutzerrechte gelten auch für die Wiederherstellung.

## Schnellere Sammlungen

- Dashboard-Zusammenfassung wird pro Sammlung zwischengespeichert und nach Änderungen erneuert.
- Die interne Bibliothek wird beim Lesen nur nach tatsächlichen Datenänderungen synchronisiert.
- Gebündelte Datenbankabfragen, zusätzliche Indizes, 40 Einträge pro Seite und verzögertes Laden der Cover reduzieren Arbeit und übertragene HTML-Daten.
- Easter-Egg-Figuren werden erst beim Auslösen geladen.

Lokaler synthetischer SQLite-Vergleich mit 300 Spielen und 200 Filmen, Median aus drei warmen Serveraufrufen:

| Seite | 5.1.0 | 5.1.1-rc.1 |
| --- | ---: | ---: |
| Dashboard | 165,71 ms | 9,56 ms |
| Bibliothek | 933,95 ms | 31,74 ms |
| Spielesammlung | 71,71 ms | 31,83 ms |
| Filme | 14,13 ms | 9,57 ms |

Diese Messungen enthalten keine Netzwerkübertragung oder Browserdarstellung. Reale Zeiten hängen von Datenbestand und Server ab. Die erste Bibliothekssynchronisierung nach Änderungen kann weiterhin aufwendiger sein.

## Regal und Easter Egg

- Nur Figuren aus den eingesendeten Spritebögen. Die ursprünglich gezeichneten Figuren wurden entfernt.
- Höchstens eine Helferfigur je Thema Sport, Piraten, Detektive und Rapper pro Szene. Bei mehr Fächern bleiben einzelne Fächer ohne Helfer.
- Tür, Leitern, vollständiger Ablauf, vier Sicherheitsarbeiter und Wächterin bleiben erhalten.
- Tür bleibt vor dem Ereignis unsichtbar; keine textliche Erzählung während der Animation.
- Mehr Platz für perspektivische Hüllenenden und Abstand zur mobilen Navigation.

## Prüfung

- Vollständige lokale Python-Regressionen bestanden; nach der abschließenden Wiederherstellungsänderung die gezielten Erfassungs- und Bedienungstests erneut bestanden.
- Alle JavaScript-Interaktionstests bestanden, einschließlich verzögertem Laden, Themenauswahl, vollständigem Szenenabbau und reduzierter Bewegung.
- Öffentlichkeitsprüfung und Prüfung auf fehlerhafte Diff-Leerzeichen bestanden.
- Ausstehend: echte iPhone-Sichtprüfung, Browserprüfung der mobilen Überlagerungen, Docker/PostgreSQL-Prüfung und reale externe Anbieterabfragen. Der lokale Browserstart war wegen fehlender Browserdateien nicht möglich.

Dieser Kandidat wurde nicht auf GitHub veröffentlicht.
