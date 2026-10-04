# Bibo 5.1.0-rc.12 – Ansichtswahl, Größenordnung und Helfer

Unveröffentlichter Prüfentwurf; enthält alle vorherigen 5.1.0-Prüfstände.

- Direkt auf dem Dashboard zwischen den ursprünglichen Kacheln, dem Holzregal und Schwarzglas wechseln. Auswahl ist pro Nutzer gespeichert, unabhängig von der aktiven Sammlung und anderen Nutzern. Ohne gespeicherte Auswahl ist Schwarzglas voreingestellt; bestehende gespeicherte Ansichten bleiben erhalten. Auch Nutzer mit Leserechten dürfen ihre Ansicht ändern. Speicheraktion prüft einen benutzer- und sitzungsgebundenen Token.
- Ursprüngliche Kacheln aus rc.6 mit Coverwechsel, Beständen, Werten, Kategorien und Anlegefach wiederhergestellt. Leere Weitere Sammlungen bleiben ausgeblendet. Regal-Script und Easter Egg laufen ausschließlich in der Regalansicht.
- Sichtbare Medien sind von links nach rechts nach ihrer dargestellten Höhe sortiert. Auch beim automatischen Wechsel werden Titel, Höhe, Cover und Ziel gemeinsam neu geordnet. Der letzte Kategorienrücken bleibt frei. Größen sind stilisierte Darstellungen, keine ausgemessenen Produktmaße.
- Helfer mit eigenen Kostümen: Mario und Luigi mit Kappen und Handschuhen; Hitman mit Glatze, dunklem Anzug und roter Krawatte; Walter White mit gelbem Schutzanzug und Brille; Conan mit Brille und roter Fliege; Ash mit Trainerkappe und Pokéball; Kool Savas als stilisierte Rapperfigur mit Kappe, Mikrofon und KS-Shirt. Eigene Kategorien bekommen Abenteurer oder Zauberer. Es sind stilisierte SVG-Figuren, keine fotorealistischen Porträts.
- Pro Fach erscheint genau ein Helfer. Bei erneutem Rütteln wird bei mehreren verfügbaren Figuren ein anderer gewählt. Ash wirft einen Pokéball, Hitman blickt abwechselnd nach links und rechts, Kool Savas nickt in Bühnenpose. Medien kommen zeitlich versetzt zurück. Diese Animationen müssen in der TU visuell bewertet werden.
- Schwarzglas nutzt dunkle Flächen, Lichtreflexe und metallische Befestigungspunkte. Der versteckte Knopf unten rechts sieht genauso aus wie die drei rein dekorativen Punkte.
- Getragene Hüllen/Bücher sind größer, mit Formattext und sichtbarem Rücken. Nach dem Rütteln erscheinen die Helfer und räumen Medien zeitlich versetzt wieder ein. Gesamtablauf rund zehn Sekunden. Die übrige Seite bleibt nutzbar; Regal-Links und Titelwechsel sind bis zur Wiederherstellung pausiert. Reduzierte Bewegung bleibt berücksichtigt.

## TU-Prüfung

Ansicht wechseln, neu anmelden und eigene gespeicherte Auswahl prüfen; zweiten Nutzer gegenprüfen. Kachelbestände und Kategorie-Anlegen testen. Regal nach Größen prüfen, zwölf Sekunden Titelwechsel abwarten und erneut prüfen. Rütteln auslösen, Helfer und gestaffeltes Einräumen ansehen, anschließend Medienlinks testen. Desktop und mobiles Zweierregal ansehen, sobald möglich.

Lokale Backend-/JavaScript-Tests vor Auslieferung. Darstellung und Animation brauchen weiterhin einen Sichttest in der TU; lokal stehen weder Browserrenderer noch Docker zur Verfügung.

Produktion und GitHub bleiben unverändert. Veröffentlichung erst nach ausdrücklicher Freigabe.
