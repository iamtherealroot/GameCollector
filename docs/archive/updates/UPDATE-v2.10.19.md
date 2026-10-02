# Collector v2.10.19

- Yu-Gi-Oh!-Setcode-Suche: `cardsetsinfo` ist nur noch Fast-Path; fehlende Printings werden über das Set aufgelöst.
- Sprachabfragen korrigiert: Englisch nutzt den Provider-Default; lokalisierte Datensätze werden nach Identifikation per Karten-ID geladen.
- Physische DE/FR/IT/PT-Setcodes bleiben die Identität des Sammlungsexemplars; EN-Codes dienen nur der Provider-Auflösung.
- Alte Release-Verzeichnisse und alte Update-ZIPs werden erst nach erfolgreichem Healthcheck gelöscht; Backups/Daten/Uploads/.env bleiben unberührt.
