# Bibo 5.1.0-rc.8 – gefülltes Medienregal

Unveröffentlichter Prüfentwurf; enthält alle vorherigen 5.1.0-Prüfstände und Stabilitätsfixes.

- Acht schmale Rücken pro Fach statt einer großen Kategorienhülle. Zufällig ausgewählte echte Titel stammen ausschließlich aus der aktiven Sammlung. Freie Rücken sind unbeschriftete Dekoration; Bestandszahlen bleiben unverändert.
- Kategorienamen stehen nur unter dem Fach. „Weitere Sammlungen“ verschwindet bei leerem Bestand. Das freie Fach zum Anlegen einer Kategorie bleibt erhalten.
- Filme und Serien: blaue, kürzere Blu-ray-Hüllen; schwarze, höhere DVDs; schwarze UHD-Hüllen und größere VHS-Hüllen.
- Games: rote Switch-Hüllen, grüne Xbox-360-Hüllen; Xbox 360 und PS2 gleich hoch, PS1 kleiner als PS3, PS3 kleiner als PS2/Xbox 360. PS4/PS5 erhalten blaue Hüllen. Andere Plattformen nutzen eine neutrale Gaming-Hülle. Die Darstellung stilisiert typische Formate; Sonderverpackungen können abweichen.
- Bücher mit verschiedenen Rückenfarben und Höhen; Musik mit CD-, Vinyl- und Kassettenformaten; Karten als Alben. Eigene Kategorien verwenden Archivhüllen.
- Eine einzelne Hülle wird nach vorne und leicht oben gezogen. Räumliche Seiten- und Oberflächen ersetzen die bisherige seitliche Kippbewegung. Einzelne Rücken reagieren auf Mausposition; Tastaturfokus zieht einen mittleren Rücken vor. Touch öffnet die Kategorie direkt. Reduzierte Bewegung wird berücksichtigt.

- Rückentitel wechseln alle zwölf Sekunden automatisch, mit Pausenschalter. Während Maus-/Tastaturbedienung, bei verborgenem Tab und bei reduzierter Bewegung pausiert der Wechsel. Bis zu 48 zufällig ausgewählte vorhandene Titel pro Kategorie stehen zur Verfügung.
- Mobile und Tablet: kompakter Header, keine seitlich auslaufende obere Navigation. Das Menü unten öffnet eine Übersicht mit Kacheln untereinander und Funktionssuche; die Schnellnavigation bleibt sichtbar. Alte CSS-Regeln werden gezielt überschrieben.

## In der TU prüfen

Regal mit mehreren DVD-/Blu-ray- und Plattformformaten ansehen, einzelne Rücken überfahren, Tastatur und schmale Bildschirmbreiten prüfen. Titel und Bestandszahlen mit der aktiven Sammlung vergleichen. Eine leere und eine gefüllte eigene Sammlung gegenprüfen.

Lokale Backend- und JavaScript-Prüfungen werden vor Auslieferung ausgeführt. Die tatsächliche Animation und Docker-Prüfung sind hier mangels Browserrenderer und Docker nicht ausführbar. Im Serververzeichnis `/opt/bibo-test/Bibo-v5.1.0-rc.8` die TU mit `bash scripts/docker-test.sh check` prüfen.

Produktion und GitHub bleiben unverändert. Veröffentlichung erst nach ausdrücklicher Freigabe.
