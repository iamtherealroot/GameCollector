# Datenschutz und Datenhaltung

Bibo ist selbst gehostet. Persönliche Sammlungsdaten verbleiben in der
eigenen PostgreSQL-Datenbank und in lokalen Upload-Verzeichnissen. Externe
Anfragen entstehen nur für Funktionen, die eine Online-Metadaten- oder
Preisquelle verwenden.

Nicht in das Repository gehören:

- `.env` und API-Zugangsdaten
- PostgreSQL-Dumps und SQLite-Dateien
- hochgeladene Cover oder Fotos
- CSV-/JSON-Exporte einer Sammlung
- Logs mit privaten Netzwerkdaten
- Backup- und Updatearchive

Beim Melden eines Fehlers sollten Titel, EAN und Screenshots geprüft und bei
Bedarf anonymisiert werden.
