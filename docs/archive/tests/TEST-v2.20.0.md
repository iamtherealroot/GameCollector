# Abnahmetest für GameCollector v2.20.0

## Installation

1. v2.20.0 direkt über die weiterhin laufende v2.18.0 installieren.
2. Prüfen, dass der Installer nicht mehr mit „Unerwartete Paketversion“ abbricht.
3. Version `2.20.0` und Healthcheck `200` kontrollieren.

## Konsolenmodellbild

1. Hardware öffnen und ein vorhandenes Konsolenmodell auswählen.
2. „Modell bearbeiten“ öffnen.
3. Ein JPEG-, PNG- oder WebP-Bild mit höchstens 8 MB auswählen und speichern.
4. Prüfen, dass das Bild anschließend in Modellansicht, Hardwarekatalog und Konsolenreihe erscheint.
5. Ein zweites Bild hochladen und prüfen, dass es das erste ersetzt.
6. „Aktuelles Modellbild entfernen“ markieren, speichern und die leere Bildanzeige prüfen.
7. Optional eine externe HTTPS-Bild-URL hinterlegen und speichern.

## Sicherheit und Bestand

1. Eine Textdatei mit umbenannter `.jpg`-Endung hochladen; sie muss abgewiesen werden.
2. Prüfen, dass Exemplare, Komponenten, Preise und Notizen beim Bildwechsel unverändert bleiben.
3. Ein Komplettbackup erstellen und prüfen, dass `uploads/hardware-models/` enthalten ist.

Für PWA, PC-Komponenten, Plattformnormalisierung und Konsolenreihen gelten zusätzlich die Tests aus `TEST-v2.19.0.md`.
