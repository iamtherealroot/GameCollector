# Abnahmetest für GameCollector v2.17.0

## 1. Installation prüfen

```bash
cd /opt/gamecollector
docker compose exec -T web python -c 'from app.app import APP_VERSION; print(APP_VERSION)'
docker compose exec -T web python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8000/health/deep").status)'
```

Erwartet: `2.17.0` und `200`.

## 2. Vorschau ohne Bestandsänderung

1. Vorher die Anzahl der Spiele und Exemplare auf der Startseite notieren.
2. `Verwaltung → Import` öffnen.
3. `TESTDATA-v2.17.0-import.csv` mit Semikolon hochladen.
4. Nur „CSV analysieren“ wählen.

Erwartet:

- 5 Zeilen
- 2 neue Titel
- 2 Konflikte innerhalb der Datei
- 1 fehlerhafte Zeile
- Der Bestand hat sich noch nicht verändert.

## 3. Entscheidungen und einzelne Exemplare

In der Vorschau einstellen:

- `GameCollector Test Physisch`: Titel + Exemplar
- `GameCollector Test Digital`: Titel + Exemplar
- zweite physische Zeile: Weiteres Exemplar
- zweite digitale Zeile: Überspringen
- fehlerhafte Zeile bleibt übersprungen

Danach „Import ausführen“ wählen.

Erwartet:

- 2 neue Katalogtitel
- 3 neue Exemplare
- das digitale Spiel ist als „Digital“ markiert
- beide physischen Exemplare sind einzeln bearbeitbar
- Lagerorte `Testregal A` und `Testregal B` sind getrennt gespeichert

## 4. Import rückgängig machen

Auf der Seite des ausgeführten Importlaufs „Import rückgängig“ wählen.

Erwartet:

- beide Testtitel und alle drei Testexemplare verschwinden
- vorher vorhandene Spiele und Exemplare bleiben unverändert
- der Importlauf bleibt als „Rückgängig“ im Protokoll sichtbar

## 5. Echte Bestandsdublette testen

Optional eine CSV-Zeile mit Titel, Plattform und EAN eines bereits vorhandenen Spiels analysieren.

Erwartet:

- Kennzeichnung „Bereits vorhanden“ oder „EAN-Dublette“
- Auswahl „Weiteres Exemplar“
- es entsteht kein zweiter Katalogtitel, sondern ein separat bearbeitbares Exemplar

## 6. Katalogdubletten zusammenführen

Unter `Verwaltung → Datenpflege` einen erkannten Dublettenkandidaten öffnen und die gewünschte Richtung `2 → 1` oder `1 → 2` wählen.

Erwartet:

- nur ein Katalogtitel bleibt bestehen
- alle Exemplare beider Titel bleiben einzeln vorhanden
- fehlende Metadaten des Zieltitels werden aus der entfernten Dublette ergänzt

Nicht zusammengehörige Treffer mit „Kein Duplikat“ dauerhaft ausblenden.
