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

## Globale Top 10 innerhalb dieser Installation

Ab 5.1.0 ist die globale Top-10-Ansicht und Teilnahme einer Sammlung
standardmäßig aktiv, sobald mindestens zwei Sammlungsdatenbanken bestehen.
Die Übersicht ist nur für angemeldete Nutzer dieser Bibo-Installation sichtbar,
nicht eine Veröffentlichung an einen externen Dienst. Ohne angepasste
Anzeigenamen werden neutrale Sammlungsnamen verwendet. Ab Prüfentwurf rc.4
erscheinen zusätzlich Cover und Besitzer-Benutzernamen. Bei gemeinsam
verwalteten Sammlungen werden die zugeordneten Administratoren genannt,
nicht technische Sammlungskonten. Notizen, Lagerorte, Kaufpreise und private
Objektlinks werden nicht gezeigt.

Nutzer können die Ansicht ausschalten. Sammlungsverwalter können unabhängig
davon die Teilnahme der aktiven Sammlung unter „Teilnahme verwalten“ beenden.
Bereits gespeicherte Abmeldungen werden durch Updates nicht zurückgesetzt.
