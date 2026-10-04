# Bibo 5.1.0-rc.6 – Stabilisierung vor der Freigabe

Unveröffentlichter Prüfentwurf. Enthält sämtliche rc.1–rc.5-Änderungen. Kein automatisches Produktiv-Update oder GitHub-Release.

## Preisqualität

- Preisdetails und globale Top 10 warnen bei alten Bewertungen (bestehende 45-Tage-Grenze), fehlendem Datum, niedriger/vorläufiger Konfidenz sowie unbestätigten Preissprüngen. eBay-Angebote werden ausdrücklich als Angebotspreise statt abgeschlossene Verkäufe bezeichnet.
- eBay-Spielangebote mit erkennbar widersprechender PAL/USA/Japan-Region oder Sonderausgabe werden ausgeschlossen. Nichtstandard-Ausgaben benötigen passende Editionswörter. Lose/CIB/Sealed-Trennung und Sprungbestätigung bleiben erhalten.
- Fehlende Regions-/Editionsinformationen werden nicht als bewiesene Übereinstimmung ausgegeben. Dies ist keine vollständige Neukatalogisierung und keine rückwirkende Preisänderung. Andere Quellen behalten ihre bisherigen Bewertungswege.

## Speicherabläufe und Bilder

- Ungültige Geldbeträge, negative/unendliche Werte und ungültige Kaufdaten werden vor Spiele-, Hardware- und Zubehöränderungen abgefangen. Deutsche Dezimalbeträge bleiben unterstützt. Leere Felder können Werte weiterhin bewusst leeren.
- Zubehör darf keinem Hauptobjekt aus einer fremden aktiven Sammlung zugeordnet werden.
- Neue Regressionen prüfen Anlegen, Bearbeiten und Löschen der drei Inventartypen, Katalogerhalt, Viewer-Rechte, Sammlungsgrenzen und ausbleibende Teiländerungen nach Eingabefehlern. Das ersetzt keine vollständige Sicht-/Geräteprüfung sämtlicher Erfassungswege.
- Defekte Bilder im Inhaltsbereich erhalten einen zugänglichen Platzhalter. Nachgeladene Bilder werden ebenfalls berücksichtigt. Keine Netzabfragen zum Prüfen durch den Server.

## Update-Backup

- Vor dem Datenbankbackup pausieren Web und Scheduler. Während des Updates entsteht daher eine kurze Nichtverfügbarkeit; externe direkte DB-Schreiber müssen separat gestoppt sein.
- Datenbank-Dump wird mit ON_ERROR_STOP in eine zufällig benannte separate Prüf-Datenbank eingespielt. Inventar-/Nutzerzahlen werden verglichen; ausschließlich diese Prüfdatenbank wird anschließend entfernt, nicht die Produktivdatenbank.
- uploads, feedback-uploads und vorhandene ältere app/static/uploads-Verzeichnisse werden separat gesichert. Archive werden gelesen, Uploaddateien isoliert entpackt und Dateiinhalte über SHA256 verglichen; Prüfsummen werden im privaten Backupverzeichnis gespeichert. Unsichere Archivpfade/Sonderdateien verhindern das Update.
- Fehlgeschlagene Prüfungen verhindern die Paketübernahme und starten den alten Programmstand wieder. Bestehender Rollback stellt Programmcode wieder her; eine automatische destruktive Datenbank-Rücksetzung erfolgt ausdrücklich nicht.
- Genügend Platz für Dump, Prüfdatenbank, Archive und temporäre Dateikopien sowie Rechte zum Anlegen einer temporären Datenbank sind erforderlich. Prüflogs und Dumps bleiben privat und dürfen nicht veröffentlicht werden.

## Prüfung in der TU

Lokale Backend-, Formular-, Rechte-, Datenschutz- und Bild-Vertragstests bestanden. Archivtests führen tatsächliche Dateiwiederherstellung aus; Docker-Abläufe sind lokal simuliert. Tatsächlicher Docker-Lauf und SQL-Restore müssen auf dem Server geprüft werden.

1. In der TU alle drei Inventartypen anlegen, ändern und löschen; jeweils auch einen ungültigen Betrag ausprobieren.
2. Top 10, Besitzer, Cover/Fallback und Preishinweise prüfen.
3. Auf dem Server aus /opt/bibo-test/Bibo-v5.1.0-rc.6 mit `bash scripts/docker-test.sh check` Regressionen und SQL-Wiederherstellung prüfen. Dieser Befehl bleibt in der isolierten TU.
4. Erst nach erfolgreicher Prüfung explizit für 5.1.0 freigeben. Danach stabilen Versionsstand und GitHub-Veröffentlichung vorbereiten.
