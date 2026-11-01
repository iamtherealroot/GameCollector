# Bibo 5.1.5-rc.1 – Testversion

- Sammlungsbereiche direkt auf der Seite „Sammlung“ filtern, einschließlich eigener Kategorien. Suche und Besitzstatus bleiben beim Wechsel erhalten.
- Einzelne Sammlungsbereiche aus dem Funktionsmenü entfernt.
- Die Medienauswahl öffnet standardmäßig wieder den passenden fünfstufigen Fragenkatalog. Die einfache Erfassung bleibt über `?simple=1` erreichbar.
- eBay-Produkte werden nicht mehr pauschal als DVD / Blu-ray eingeordnet. Erkannte Spieleplattformen werden an die Spieleübernahme weitergereicht.
- Spiele gelangen nicht in die TMDB-Filmsuche; der Treffer bietet direkt die Spieleübernahme an.
- Bewertungsprotokoll: „Details passender Angebote wurden geprüft“ ersetzt den technischen Begriff `getItem`.

## Prüfung

Automatisierte Prüfung mit temporärer SQLite-Datenbank und simulierten Anbieterdaten: PS5-EAN erkennen, Katalogtitel anlegen, Exemplarformular öffnen und Exemplar speichern. Keine Live-Anbieter oder Produktionsdaten für diesen Test.

## Testumgebung

Im ausgecheckten Testzweig: `bash scripts/docker-test.sh check`.
Die Docker-Testumgebung verwendet eigene Container und Datenbankvolumes. Diese Version ist ein Prüfkandidat; keine automatische Produktionsfreigabe.
