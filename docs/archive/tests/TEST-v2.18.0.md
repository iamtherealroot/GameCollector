# Abnahmetest für GameCollector v2.18.0

## 1. Preiszentrum

1. **Auswertung → Preiszentrum** öffnen.
2. Die Warteschlange muss Einträge aus mehreren Bereichen zusammenfassen und Zähler für **Ohne Marktwert**, **Veraltet**, **Fehler**, **Auffällig** und **Fixiert** zeigen.
3. Suche, Bereichsfilter und Statusfilter ausprobieren. Eine leere Filterkombination darf keinen Fehler auslösen.
4. Bei einem Eintrag **Quelle, Variante und Aktionen** öffnen. Kaufpreis, automatischer Marktwert, verwendeter Wert, Quelle, Preisspanne und Variante müssen getrennt erkennbar sein.

## 2. Reversible Preisfixierung

1. Einen bereits automatisch bewerteten Eintrag auswählen.
2. Einen leicht abweichenden Testwert und als Begründung `Test v2.18.0` eintragen.
3. Nach dem Speichern muss der Eintrag als **Fixiert** erscheinen. Der automatische Marktwert bleibt daneben sichtbar; nur **Verwendeter Wert** wechselt auf den Testwert.
4. **Fixierung aufheben** anklicken. Sofort muss wieder der vorherige automatische Marktwert verwendet werden.

## 3. NES-Hardwarepreis

1. Im Preiszentrum nach `NES Frontloader` beziehungsweise dem angelegten NES-Modell suchen.
2. **Eintrag neu bewerten** anklicken.
3. Erwartet wird ein Marktwert mit Quelle **eBay Browse API** oder **PriceCharting**. SNES-, NES-Classic/Mini-, Famicom- und Toploader-Angebote dürfen den Frontloaderpreis nicht bestimmen.
4. Falls weiterhin kein Marktwert entsteht, im selben Eintrag den nun sichtbaren Quellenstatus und die Fehlermeldung notieren; sie unterscheiden insbesondere API-Fehler, zu wenige Treffer und fehlende PriceCharting-Zuordnung.

## 4. Bestandsschutz

- Dashboard und Gesamtwert müssen einen gesetzten Fixpreis verwenden.
- Nach dem Aufheben müssen sie wieder den automatischen Preis verwenden.
- Spiele, Exemplare, Kaufpreise und bisherige Preisverläufe dürfen sich dabei nicht verändern.
