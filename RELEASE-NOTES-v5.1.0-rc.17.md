# Bibo 5.1.0-rc.17 – Sprite-Ausschnitte, Schuss und eindeutige Helfer

Unveröffentlichter Prüfentwurf für die isolierte TU. Enthält alle bisherigen Prüfstände.

- Die festen Rasterausschnitte aus rc.16 waren ungenau. Jede Sportlerpose verwendet jetzt eine eigene, anhand der zusammenhängenden Figur bestimmte Vektorkontur. Benachbarte Figuren werden ausgeschlossen. Köpfe und Füße bleiben vollständig; Füße sind auf einer gemeinsamen Grundlinie ausgerichtet.
- Dreiphasige Schuss-/Schlagbewegung mit Ausholen, Kontakt und Nachschwingen. Der Ball fliegt erst nach dem Kontakt los und verwandelt sich beim Auftreffen ins jeweilige Medium.
- Gestaffelter Hin- und Rückweg mit 1,1 Sekunden Abstand am gemeinsamen Eingang. Einräumen beginnt nach Ankunft aller Helfer; der Türsteher wartet auf die vollständige Rückkehr. Die Gesamtdauer wächst mit der Zahl der Helfer.
- Jeder Charakter wird pro Szene höchstens einmal ausgewählt, auch über mehrere Kategorien hinweg. Bei fehlenden Alternativen bleibt ein Fach ohne eigenen Helfer; Medien werden trotzdem zurückgestellt.
- Neue Abenteurer-Vorlage gesichtet; zusätzliche Charaktere sind in diesem Korrekturstand noch nicht integriert.

Die vorhandenen Laufposen werden für die Schussbewegung verwendet; dieser Entwurf enthält noch keine neu gezeichneten vollständigen Kick-Sprites. Visuelle Wirkung und externe SVG-Pose-Verweise in Firefox/Safari benötigen einen TU-Sichttest. Funktionsprüfungen kontrollieren Links, Auswahl, Ballflug und vollständiges Entfernen der Effekte.

Produktion und GitHub unverändert. Veröffentlichung erst nach ausdrücklicher Freigabe.
