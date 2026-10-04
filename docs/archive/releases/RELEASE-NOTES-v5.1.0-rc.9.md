# Bibo 5.1.0-rc.9 – Medienhüllen und Direktnavigation

Unveröffentlichter Prüfentwurf, enthält alle vorherigen 5.1.0-Prüfstände.

- Die vollständige Hülle bewegt sich mit der bisherigen Herausziehbewegung nach vorne und oben. Ein fester Blickwinkel macht zusätzlich die Coverseite und Tiefe sichtbar. Formatbänder, Kunststoffkanten, Buchseiten und CD-Hüllenränder machen die Rücken realistischer. Vorhandene Cover gehören jeweils zum dargestellten Medium; ohne Cover bleibt eine neutrale Hüllenseite.
- Sieben wechselnde Rücken führen bei vorhandenen Titeln direkt zum jeweiligen Spiel- bzw. Medieneintrag. Spiele öffnen die Katalogdetailseite, andere Medien ihren konkreten Eintrag. Unbeschriftete Dekorplätze öffnen die Kategorie.
- Der achte und letzte Rücken bleibt immer unbeschriftet und öffnet die Kategorie. Das Schild unter dem Fach ist ebenfalls ein Kategorienlink. Neue Kategorie weiterhin im eigenen leeren Fach.
- Titel, Format, Cover und Link wechseln gemeinsam. Der feste Kategorienrücken ist vom Wechsel ausgeschlossen. Tastatur, Maus, Touch, Pausenschalter und reduzierte Bewegung bleiben unterstützt. Die bisherige mobile Menüverbesserung ist enthalten.
- Titel und Links stammen ausschließlich aus der aktiven Sammlung. Detailseiten behalten ihre bestehenden Zugriffsprüfungen. Keine verschachtelten Links.

- Unterschiedliche Bauformen: Kunststoff- und CD-Hüllen, dünne Vinylhüllen, Bücher mit Seitenblock und dickere Kartenalben. Game Boy, NES, SNES und Nintendo 64 werden ohne vorhandene OVP als lose Module dargestellt, mit OVP als Retrobox. DS/3DS erhalten kleinere helle Hüllen. Das ändert keine Inventardaten.

- Wärmeres Holzregal mit Maserung, stärkeren Böden und Rückwand. Handy und Tablet bis 1120 Pixel zeigen zwei Fächer pro Reihe; große Desktopansichten vier.
- Kleiner Holzknopf unter dem Regal als Easter Egg: kurz rütteln, Medien purzeln heraus, nach drei Sekunden stehen sie wieder. Keine Änderungen an Sammlungsdaten. Währenddessen pausiert der Titelwechsel; bei reduzierter Bewegung bleibt das Regal stehen.

## TU-Prüfung

FIFA 98 oder einen anderen Titel anklicken und das Ziel prüfen. Filme, Bücher und eigene Kategorien gegenprüfen. Danach letzten unbeschrifteten Rücken und Schild unten anklicken: beide müssen zur Kategorie führen. Mindestens zwölf Sekunden warten und nach dem Titelwechsel erneut klicken. Bei Maus-/Tastaturbedienung pausiert der Wechsel. Die gesamte Hülle einschließlich Coverseite muss bei der bestehenden Bewegung herauskommen.

Lokale Backend-/JavaScript-Prüfungen vor Auslieferung. Tatsächliche Darstellung und Animation auf Desktop, iPhone und iPad bitte in der TU prüfen; lokal stehen weder Browserrenderer noch Docker zur Verfügung. Serverchecks: im Verzeichnis `/opt/bibo-test/Bibo-v5.1.0-rc.9` mit `bash scripts/docker-test.sh check`.

Produktion und GitHub bleiben unverändert. Veröffentlichung erst nach ausdrücklicher Freigabe.
