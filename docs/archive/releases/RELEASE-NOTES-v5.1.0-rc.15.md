# Bibo 5.1.0-rc.15 – Gelenke und Rückweg des Türstehers

Unveröffentlichter Prüfentwurf; enthält alle vorherigen 5.1.0-Prüfstände.

- Arme und Beine sind in getrennte Gelenksegmente aufgeteilt. Gegenläufige Hüftbewegungen, sichtbare Kniebeugung und bewegliche Ellenbogen ergänzen Schulterbewegungen beim Laufen, Klettern und Einräumen. Bewegungsausschläge sind größer als in rc.14. Reduzierte Bewegung bleibt berücksichtigt.
- Nach der abschließenden Geste geht auch der ernste Türsteher durch die Tür. Erst nach seiner Rückkehr schließt sie. Anschließend blendet sie aus. Die Szene dauert insgesamt rund 33 Sekunden und setzt alle Klassen, Figuren und Bedienelemente zurück.
- Separaten Sockel unter dem Regal entfernt. Die temporäre Tür sitzt innerhalb des unteren Regalbereichs, ebenso der Türsteher. Laufwege werden anhand ihrer aktuellen Position berechnet. Außerhalb des Events bleibt die Tür unsichtbar.
- Persönliche Ansicht weiterhin ausschließlich unter Konto → Dashboardansicht. Bestandsdaten, Direktlinks und Größenordnung bleiben unverändert.

- Ash hat eine eigene Pokémon-inspirierte Pixel-Laufanimation mit vier wechselnden Schrittposen. Die vom Nutzer verlinkte GIF-Animation diente als Bewegungsreferenz; das externe GIF wird weder eingebettet noch als Laufzeitabhängigkeit geladen. Eigene SVG-Pixelzeichnung, Pokéballaktion bleibt erhalten.

## TU-Prüfung

Arme, Knie und Ellenbogen beim Laufen, Klettern und Einräumen ansehen. Nach der Geste beobachten, dass der Türsteher hineingeht, bevor die Tür schließt und im Regal verschwindet. Rund 33 Sekunden abwarten und danach erneut auslösen. Mobile und Desktop-Regale gegenprüfen.

Lokale Tests prüfen Szenenfolge, Rücksetzung, SVG-Struktur, Navigation und Einstellungen. Die tatsächliche Bewegungswirkung erfordert weiterhin einen TU-Sichttest; hier steht kein Browserrenderer oder Docker zur Verfügung.

Produktion und GitHub bleiben unverändert. Veröffentlichung erst nach ausdrücklicher Freigabe.
