# Abnahmetest für GameCollector v2.17.1

1. Unter **Stapelimport** erneut `TESTDATA-v2.17.0-import.csv` auswählen.
2. Trennzeichen **Semikolon** eingestellt lassen und **CSV analysieren** anklicken.
3. Erwartete Vorschau: **5 Zeilen**, **2 neu**, **2 Konflikte**, **1 fehlerhaft**.
4. Der Bestand darf durch die Vorschau noch nicht verändert worden sein.
5. Eine Dublette als weiteres Exemplar übernehmen, die andere überspringen und den Import ausführen.
6. Erwartet werden zwei neue Katalogtitel und insgesamt drei neue, einzeln bearbeitbare Exemplare.
7. Physisch/Digital sowie die Lagerorte `Testregal A` und `Testregal B` prüfen.
8. Den Importlauf rückgängig machen. Nur die durch diesen Lauf erzeugten Titel und Exemplare dürfen entfernt werden.

Ein alter v2.17.0-Vorschau-Lauf mit fünf fehlerhaften Zeilen muss nicht ausgeführt werden.
