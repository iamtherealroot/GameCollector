# Bibo 5.1.0-rc.7 – interaktives Sammlungsregal

Unveröffentlichter Prüfentwurf, enthält alle vorherigen 5.1.0-Prüfstände einschließlich Preis-, Speicher-, Cover- und Update-Backupfixes aus rc.6.

- Dashboard-Kategorien erscheinen als farbige Buchrücken, DVD-/Blu-ray-Hüllen, Boxsets und Alben in einem warmen Regal. Echte vorhandene Katalogbilder erscheinen als kleine Coverstreifen; Dekohüllen sind keine erfundenen Sammlungsobjekte.
- Jede Kategorie bleibt ein normaler Link. Beschriftung, Bestandszahlen und Wert sind sichtbar, auch ohne darüberzufahren. Eigene Kategorien erscheinen mit ihrem Namen und Symbol im Regal.
- Ein freies Fach führt für Bearbeiter zum bestehenden Formular „Kategorie anlegen“ und fokussiert den Namen. Für Leser bleibt das Regal navigierbar; der Anlegebereich wird ausgeblendet und ist serverseitig gesperrt.
- Beim Darüberfahren gleitet eine unbeschriftete Hülle leicht nach oben und vorne, wie beim Herausnehmen aus dem Regal. Tastaturfokus bekommt ebenfalls Hervorhebung. Touch-Navigation benötigt kein Hover; bei reduzierter Bewegung sind die Bewegungen deaktiviert.
- Dashboard-Tutorial erklärt jetzt die Regalnavigation. Bestehende Tutorial-Schalter bleiben erhalten.
- Layout passt seine Spaltenzahl an die Bildschirmbreite an. Regaldarstellung ist CSS/HTML, ohne zusätzliche Bildpakete oder Netzabhängigkeit.

Vollständige lokale Backend-, Navigation-, Kategorien-, Rechte-, Template- und JavaScript-Vertragstests bestanden. Die tatsächliche Darstellung auf Desktop/iPhone und die Animation bitte in der TU prüfen; hier ist kein Browserrenderer oder Docker verfügbar.

## TU-Prüfung

1. Kategorien per Maus und Tastatur öffnen, Bestands-/Wertschilder prüfen.
2. Maus über ein Fach bewegen und die leicht herauskommende Hülle prüfen.
3. Neues Fach anlegen, eigene Kategorie öffnen; Leserzugang gegenprüfen.
4. Die Stabilitätschecks aus RELEASE-NOTES-v5.1.0-rc.6.md durchführen. Der Serverpfad lautet hier `/opt/bibo-test/Bibo-v5.1.0-rc.7`; darin `bash scripts/docker-test.sh check` ausführen, um TU-Regressions- und SQL-Restoretests zu starten.

Produktion und GitHub bleiben unverändert. Veröffentlichung erst nach expliziter Freigabe für den finalen 5.1.0-Stand.
