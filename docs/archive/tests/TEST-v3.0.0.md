# Testplan Bibo v3.0.0

1. Nach der Installation Version `3.0.0` und Healthcheck `200` prüfen.
2. Browser einmal vollständig neu laden (`Strg+F5`); Bibo-Logo, Favicon und
   Name müssen sichtbar sein.
3. **Bibliothek** öffnen. Spiele, Filme/Serien, Bücher, Musik, Karten, Hardware
   und Zubehör müssen gemeinsam erscheinen, sofern Einträge vorhanden sind.
4. Suche sowie Bereichs- und Statusfilter testen.
5. Je einen Eintrag pro vorhandenen Bereich über **Öffnen** aufrufen und prüfen,
   dass die bekannte Einzelbearbeitung inklusive Duplikaten erhalten ist.
6. Einen fixierten Wert kontrollieren (z. B. NES Frontloader): derselbe Wert
   muss in Bibliothek und Preiszentrum erscheinen.
7. Eine Filmreihe und Konsolenreihe öffnen; manuelle Zuordnungen und
   Besitzstatus dürfen durch die Migration nicht verändert sein.
8. App/PWA neu öffnen und neues Bibo-App-Icon kontrollieren.
9. Backup-Verzeichnis aus der Installationsausgabe notieren.

