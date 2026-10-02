# GameCollector v0.7.5

## Konsolen-Dubletten bereinigen

v0.7.5 normalisiert Plattformnamen und kann doppelte Konsoleneinträge sicher zusammenführen.

Bei der geprüften Bestandsdatenbank werden beim ersten Start automatisch folgende Alias-Plattformen zusammengeführt, sofern keine Katalogkonflikte vorhanden sind:

- `Sony PlayStation` -> `PlayStation`
- `Sony PlayStation 2` -> `PlayStation 2`
- `Nintendo Wii` -> `Wii`

Vor dem Release wurde geprüft, dass zwischen diesen drei Paaren keine identischen Spielvarianten vorhanden sind.

## Dauerhafte Plattform-Normalisierung

Bekannte Provider-/Import-Aliase werden künftig auf den kanonischen Namen abgebildet, z. B.:

- PS1 / Sony PlayStation / PlayStation 1 -> PlayStation
- PS2 / Sony PlayStation 2 -> PlayStation 2
- PS3 / PS4 / PS5 -> jeweilige PlayStation-Plattform
- Nintendo Wii -> Wii
- N64 -> Nintendo 64
- GameCube -> Nintendo GameCube
- NES / SNES -> vorhandene kanonische Einträge
- Mega Drive / Genesis-Varianten -> Mega Drive / Genesis
- Xbox Series X/S, Series X und Series S -> Xbox Series X|S

CSV-Importe und automatisch erzeugte Plattformen verwenden ebenfalls die Normalisierung.

## Konsolen zusammenführen

Unter **Konsolen -> Bearbeiten** gibt es jetzt einen eigenen Bereich **Konsolen zusammenführen**.

- Quelle und Ziel auswählen
- Anzahl der zu verschiebenden Spiele wird angezeigt
- Spiele werden auf die Zielplattform verschoben
- Quellplattform wird anschließend entfernt
- Sammlung, Exemplare, Preise und Historie bleiben erhalten
- Wenn eine identische Katalogvariante bereits auf dem Ziel existiert, wird der Merge sicher abgebrochen und nichts gelöscht

## Datenbank

Es werden keine Tabellen oder Volumes gelöscht. Das bestehende PostgreSQL-Volume bleibt unverändert erhalten.
