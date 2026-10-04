# Bibo 5.1.1-rc.3

Unveröffentlichter Testkandidat, einschließlich aller Änderungen aus RC.1 und RC.2.

## Korrekturen am Easter Egg

- Neue Spriteposen benutzen isolierte Silhouettenmasken statt verschachtelter SVG-Ausschnitte. Globale CSS-Regeln können dadurch weder die Ausschnittgröße ändern noch den ganzen Spritebogen sichtbar machen.
- Nachbarfiguren und fremde Körperteile wurden aus den Masken ausgeschlossen. Unbrauchbare oder zusammenhängende Posen werden durch saubere Posen derselben eingesendeten Figur ersetzt. Einzelne Figuren verwenden dadurch weniger unterschiedliche Laufbilder.
- Die gespeicherte Vogelvorlage bleibt auch innerhalb der Helferfigur verborgen. Nur die fliegende Kopie erscheint während der Aktion.
- Der Vogelstart ist auf die Hand ausgerichtet; Flugziel, Rückkehr und Szenenabbau bleiben erhalten.
- Sechs unterschiedliche Helferthemen, vier Leitern, Sicherheitsgruppe und Wächterin bleiben erhalten.

## Prüfung

- Alle 210 neuen Figurenposen statisch mit librsvg gerendert und nach Korrekturen visuell kontrolliert.
- Maskenprüfung schützt vor unmaskierten Bildern, übergroßen Ausschnitten, doppelten Clip-IDs, verschachtelten SVG-Viewports und sichtbarer Vogelvorlage.
- Interaktionstests für Auswahl, Leitern, Vogelflugziel, Rückkehr, vollständigen Szenenabbau und reduzierte Bewegung bestanden. Dashboard- und Bedienungsregressionen bestanden.
- Die komplette Animation mit Browser-CSS, Firefox/iPhone und Docker/PostgreSQL muss weiterhin in der SSH-Testumgebung geprüft werden. Die statische Renderprüfung ersetzt diesen Test nicht.

Originale Bildquellen wurden unverändert übernommen. Nicht auf GitHub veröffentlicht.
