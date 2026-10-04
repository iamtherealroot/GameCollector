# Bibo 5.1.1-rc.5

Unveröffentlichter Testkandidat. Enthält alle Änderungen aus RC.1 bis RC.4.

- Der eingesendete Runner und der Ladehinweis erscheinen mittig im sichtbaren Bildschirm: bei Seitenwechseln, der Katalogsuche und der Suche nach Zusatzinfos. Kleine Bildschirme und reduzierte Animationen werden berücksichtigt.
- Nach EAN/Titel und Medienauswahl startet die passende externe Katalogsuche automatisch. Lokale Treffer erscheinen zuerst; das Laden der Seite wartet nicht auf Anbieter. Der zusätzliche Klick aus RC.4 entfällt. Die bisherigen Anbieter und der Film/Serien-EAN-Resolver bleiben erhalten. Suchformulare in nachgeladenen Treffern verwenden ihre ursprüngliche Suchroute.
- MCU-Filme lassen sich nach Kinostart oder Handlungschronologie sortieren. Die Auswahl wird für die Sitzung gespeichert. Weitere Universen und angekündigte Titel werden in der Timeline separat angezeigt. Die Hauptfilmhandlungen bestimmen die Zuordnung; Rückblicke und Abspannszenen können abweichen. Quellen und Stand stehen in der Ansicht sowie in `app/mcu_order.py`.
- Die Easter-Egg-Tür erscheint und öffnet sich erst nach dem letzten fallenden Medium. Aufbau und Helferstart sind entsprechend verschoben.
- Jeder fliegende Vogel erhält eigene Masken-IDs. Maskendefinitionen liegen außerhalb der animierten Posegruppen. Der SVG-Bereich begrenzt die Darstellung zusätzlich, damit kein vollständiger Spritebogen außerhalb der Figur sichtbar wird.

## Prüfung

Automatisierte Tests prüfen beide MCU-Reihenfolgen, gespeicherte Auswahl, unveränderte Exemplarzahlen, automatische Kataloganfragen und Fehlerfeedback, Weiterleitung der gemeldeten EAN an den bestehenden Resolver, Fragment-Suchformulare, Türzeitpunkt, Leiterverkehr, eindeutige Vogelmasken und alle 216 zugeschnittenen Spriteframes. Anbieter sind in diesen Tests simuliert. Eine echte Anbieteranfrage mit der gemeldeten EAN und die Firefox-Darstellung auf dem Nutzerrechner müssen im Testbetrieb geprüft werden.

Das Testpaket wird nicht auf GitHub veröffentlicht und verwendet den bestehenden isolierten SSH-Testablauf.
