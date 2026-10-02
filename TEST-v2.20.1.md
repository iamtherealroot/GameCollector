# Abnahmetest für GameCollector v2.20.1

1. GameCollector über `https://bibo.example.invalid` öffnen.
2. Bei bestehender Verbindung und leerer Offline-Warteschlange darf keine dauerhafte Online-Statusleiste erscheinen.
3. „Sammlung“ öffnen: Alle Einträge einschließlich „Reihen & Sammlungen“ müssen vollständig sichtbar und anklickbar sein.
4. Browser offline schalten: Der Offline-Hinweis muss erscheinen, darf aber kein Navigationsmenü überdecken.
5. Browser wieder online schalten: Ohne wartende Erfassungen muss der Hinweis verschwinden.
6. Mit einer wartenden Offline-Erfassung muss die Statusleiste samt Zähler sichtbar bleiben.
