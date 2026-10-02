# GameCollector / Collector v2.10.18

## Yu-Gi-Oh!-Suche
- Deutsche physische Setcodes werden weiterhin nur für die Provider-Suche auf den EN-Referenzcode normalisiert; gespeichert/angezeigt bleibt der eingegebene physische Code.
- Setcode-Suche besitzt jetzt einen zweiten Auflösungsweg: Wenn `cardsetsinfo.php` ein Printing nicht auflöst, wird der Set-Präfix über `cardsets.php` bestimmt und das Set über `cardinfo.php?cardset=...` durchsucht.
- Dadurch können Printings gefunden werden, die im normalen Kartenbestand vorhanden sind, aber über den separaten Printing-Endpunkt nicht sauber auflösbar sind.
- Nach Identifikation wird weiterhin die deutsche Karte per Karten-ID geladen; alle bekannten Printings der Karte werden angeboten.

## Installer
- Alte entpackte Release-Verzeichnisse unter `/opt/gamecollector/updates/` werden erst nach erfolgreichem Healthcheck gelöscht; das aktuelle Release bleibt erhalten.
- Alte `GameCollector-v*-update.zip` in `$HOME/Downloads/` werden nach erfolgreichem Healthcheck gelöscht; das aktuelle ZIP bleibt erhalten.
- Backups, `.env`, Datenbank/Volumes, `data/` und Uploads bleiben unberührt.
