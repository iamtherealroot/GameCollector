# Abnahmetest für GameCollector v2.19.0

## 1. PWA und Offline-Erfassung

1. GameCollector über die HTTPS-Adresse `https://bibo.example.invalid` auf dem Smartphone öffnen. Die reine HTTP-IP-Adresse erlaubt in Browsern keine vollständige PWA-/Kamerafunktion.
2. Im Kontomenü **App installieren** wählen. Auf iOS alternativ **Teilen → Zum Home-Bildschirm** verwenden.
3. Die installierte App einmal online öffnen und den Scanner aufrufen.
4. WLAN und mobile Daten abschalten, einen gültigen EAN-/UPC-Code scannen und **Code verwenden** wählen.
5. Erwartet: Der Code wird als offline gespeichert angezeigt; es wird kein Bestand automatisch angelegt oder überschrieben.
6. Verbindung wieder einschalten. Die Statusleiste muss synchronisieren.
7. **Offline-Erfassungen** öffnen. Ein neuer Barcode steht auf **Identifizieren**, ein bereits vorhandener Barcode sichtbar auf **Konflikt** oder **Bestätigen**.
8. Den Eintrag prüfen und anschließend **Als erledigt markieren** wählen.

## 2. PC-Komponenten

1. Unter **Hardware** in der Familie `PC` ein Modell wie `Gaming-PC` öffnen oder anlegen.
2. Ein Exemplar hinzufügen.
3. Erwartet: Es gibt keinen Pflichtpunkt **Original-Controller**. Stattdessen erscheinen unter anderem Gehäuse, Mainboard, CPU, Kühler, RAM, GPU, primärer/weiterer Speicher, Netzteil und Netzwerk.
4. Bei CPU, RAM und GPU Hersteller/Modell/Kapazität eintragen, speichern und das Exemplar erneut öffnen.
5. Erwartet: Alle Angaben bleiben getrennt erhalten und fließen in Vollständigkeit und Setzustand ein.

## 3. Plattform- und Konsolenreihen

1. **Reihen & Sammlungen → Konsolenreihen** öffnen.
2. Erwartet: Hersteller ohne eigenes Konsolenexemplar, beispielsweise Atari, Sega oder SNK/Neo Geo, werden nicht angezeigt.
3. Sobald ein Exemplar einer solchen Familie angelegt wird, muss die Reihe erscheinen und die vollständige deutsche Soll-Liste zur Vervollständigung anzeigen.
4. `PAL Xbox 360` darf nicht als eigene Plattform neben `Xbox 360` erscheinen.
5. `Nintendo Super Nintendo Entertainment System` darf nicht zusätzlich zu `Super Nintendo (SNES)` erscheinen.
6. Bereits vorhandene Spiele, Exemplare, Preise, Modelle, Zubehör und Ziele der zusammengeführten Plattformen müssen erhalten bleiben.
