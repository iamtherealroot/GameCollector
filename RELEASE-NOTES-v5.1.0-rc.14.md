# Bibo 5.1.0-rc.14 – ruhigere Helferbewegungen

Unveröffentlichter Prüfentwurf; enthält alle vorherigen 5.1.0-Prüfstände.

- Türwächter mit zusammengezogenen Augenbrauen und ernstem Mund statt Lächeln.
- Tür ist außerhalb der Szene unsichtbar. Beim Auslösen blendet sie ein, öffnet sich zur Ankunft, schließt nach der Rückkehr und blendet am Ende wieder aus. Ihre Position bleibt für die Berechnung der Wege verfügbar; unsichtbare Dekoration ist nicht interaktiv.
- Wege mit sanfterem Anlaufen und Abbremsen. Laufen und Klettern sind eigene Abschnitte mit kurzen Übergängen an Leiterfuß und Regalfach. Kein abruptes Kippen der gesamten Figur. Hin- und Rückweg enden an exakt denselben Positionen wie die Arbeitsphase.
- Gegenläufige Beinbewegungen und ruhigere, abwechselnde Armbewegungen. Getragene Medien erscheinen erst beim Einräumen und verschwinden für den Rückweg. Leicht unterschiedliche Schrittphasen vermindern die Synchronität der Helfer. Die Szene bleibt rund 30 Sekunden lang.
- Persönliche Ansicht weiterhin unter Konto → Dashboardansicht; Größenordnung, Direktlinks, reduzierte Bewegung und Türwächterreaktionen bleiben erhalten.

## TU-Prüfung

Regal vor der Szene ohne sichtbare Tür prüfen. Rütteln auslösen: Einblenden, Öffnen, Laufen, Klettern, Einräumen, Rückweg und Schließen ansehen. Ernstes Gesicht und vollständiges Verschwinden der Tür am Ende prüfen. Desktop und mobiles Zweierregal gegenprüfen, sobald möglich.

Lokale Backend-/JavaScript-Prüfungen vor Auslieferung. Ob die Bewegungen überzeugend wirken, muss in der TU visuell geprüft werden; lokal stehen weder Browserrenderer noch Docker zur Verfügung.

Produktion und GitHub bleiben unverändert. Veröffentlichung erst nach ausdrücklicher Freigabe.
