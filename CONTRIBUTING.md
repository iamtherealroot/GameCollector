# Zu Bibo beitragen

Fehlermeldungen, Verbesserungsvorschläge und Pull Requests sind willkommen.

1. Erstelle einen Fork und einen Branch für eine klar abgegrenzte Änderung.
2. Halte `.env`, API-Zugangsdaten, Datenbankdumps, Uploads und persönliche Exporte aus dem Repository heraus.
3. Prüfe die Python-Syntax: `python3 -m py_compile app/app.py app/scheduler.py`.
4. Führe für Änderungen an Spielepreisen `python3 scripts/test_game_price_stability.py` aus. Weitere gezielte Regressionstests liegen unter `scripts/`.
5. Für Anwendungstests installiere `requirements.txt` in einer eigenen Python-Umgebung und verwende eine separate Testdatenbank. Der CI-Ablauf in `.github/workflows/ci.yml` zeigt die Prüfungen für Seiten, Templates und Docker-Dienste.
6. Beschreibe im Pull Request das Problem, das neue Verhalten und die durchgeführten Prüfungen. Erläutere Auswirkungen auf Schema und Migrationen, sofern vorhanden.

Aktuelle Anleitungen liegen unter [docs/](docs/README.md), historische Notizen im [Dokumentationsarchiv](docs/archive/README.md). Behalte den Root-Pfad der aktuellen `RELEASE-NOTES-vX.Y.Z.md` bei: Der Release-Workflow verwendet ihn zur Veröffentlichung.

Beiträge werden unter der [GPL-3.0](LICENSE) veröffentlicht.
