# Bibo 5.1.5

- Sammlung: Große Bereichsschaltflächen mit Symbolen, deutlich markierter Auswahl, Tastaturfokus und zweispaltigem Raster auf dem Handy.
- Menü: Dashboard-Verknüpfungen nicht mehr doppelt anzeigen (Sammlung, Hinzufügen, Scanner, Werte, Top 10, Entdecken, Feedback und Funktionsübersicht).
- Mobile Kopfzeile: Abstand zur iPhone-Statusleiste wiederhergestellt. Der Testumgebungshinweis berücksichtigt den sicheren Bereich ohne doppelten Abstand.
- Sammlungsbereiche direkt auf der Seite „Sammlung“ filtern, einschließlich eigener Kategorien. Suche und Besitzstatus bleiben beim Wechsel erhalten.
- Einzelne Sammlungsbereiche aus dem Funktionsmenü entfernt.
- Die Medienauswahl öffnet standardmäßig wieder den passenden fünfstufigen Fragenkatalog. Die einfache Erfassung bleibt über `?simple=1` erreichbar.
- eBay-Produkte werden nicht mehr pauschal als DVD / Blu-ray eingeordnet. Erkannte Spieleplattformen werden an die Spieleübernahme weitergereicht.
- Spiele gelangen nicht in die TMDB-Filmsuche; der Treffer bietet direkt die Spieleübernahme an.
- Bewertungsprotokoll: „Details passender Angebote wurden geprüft“ ersetzt den technischen Begriff `getItem`.

## Prüfung

Automatisierte Prüfung mit temporärer SQLite-Datenbank und simulierten Anbieterdaten: PS5-EAN erkennen, Katalogtitel anlegen, Exemplarformular öffnen und Exemplar speichern. Keine Live-Anbieter oder Produktionsdaten für diesen Test.

## Installation und Update

Das ZIP enthält die vollständige Installation und das Update für vorhandene Bibo-Installationen. Der normale Bibo-Updater bezieht diese stabile Version über GitHub.
