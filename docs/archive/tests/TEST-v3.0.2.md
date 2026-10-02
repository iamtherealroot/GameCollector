# Testplan Bibo v3.0.2

1. Version `3.0.2` und `/health/deep` prüfen.
2. Eine Filmreihe öffnen und bei einem ungeklärten Titel **Nie physisch in DE erschienen** wählen.
3. Prüfen, dass der Titel entsprechend markiert wird, die neue Kennzahl steigt und der Film nicht als fehlend zählt.
4. **Automatische Erkennung verwenden** wählen und prüfen, dass die manuelle Einstufung aufgehoben wird.
5. Eine TV-Sammlung öffnen und den neuen Status für eine Staffel setzen und wieder auf **Ungeklärt** stellen.
6. Prüfen, dass vorhandene Exemplare, Box-Zuordnungen, Werte und andere manuelle Status unverändert bleiben.
7. Sicherstellen, dass nirgends Aussagen zu „vergriffen“, „lieferbar“ oder „in Produktion“ erscheinen.
8. Auf der Bibo-Startseite **Games** anklicken: Es muss der vorhandene Spielebestand geöffnet werden.
9. **Katalog → Spielekatalog** öffnen: Die URL `/games` muss den Katalog und nicht die Bewertungszentrale anzeigen.
10. **Bewertungen** öffnen: Die URL `/bewertungen` muss die Bewertungszentrale anzeigen.
