# Bibo 5.1.2-rc.1

Prüfstand für den Ladescreen und die Film-EAN-Suche; noch kein stabiles GitHub-/APT-Release.

- Neuer vom Nutzer gelieferter Runner mit acht Laufphasen.
- Gleiche Bildgröße und Kopfposition in allen Phasen; Sprungphase bleibt erhalten.
- Gleichmäßige 0,72-Sekunden-Schleife ohne Zwischenbilder aus benachbarten Frames.
- Film-EAN-Suche probiert bereinigte Werk-Titel und kürzere Titelvarianten, wenn der Händlertitel keine Treffer liefert.
- Barcode-Produkttitel bleiben bei fehlender TMDB-Zuordnung sichtbar und lassen sich mit derselben EAN erneut suchen.
- Doppelte Suchanfragen für denselben Titel werden vermieden.
- Die ganze Bestätigungszeile „Angaben geprüft“ ist ausdrücklich mit der Checkbox verknüpft; Zeiger, Auswahl und Tastaturfokus werden hervorgehoben.
- Zentrierung, Statusmeldungen und reduzierte Bewegung bleiben erhalten.
- Eigenständige 502/503/504-Seite für Nginx Proxy Manager liegt unter packaging/proxy; deren Aktivierung erfolgt separat im Proxy.

Prüfung: Frontend-Regressionsprüfungen, Sprite-Geometrie und Release-Smoke.
Browser-Sichtprüfung des neuen Runners erfolgt in der Testumgebung.
