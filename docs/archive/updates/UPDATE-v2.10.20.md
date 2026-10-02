# GameCollector v2.10.20

## Yu-Gi-Oh!-Setcode-Fix

- Repariert den Fallback fuer Printings, die YGOPRODeck nicht in `cardsetsinfo`/`card_sets` fuehrt.
- Wiki-Suchergebnisse wie `Card Gallery:Slifer the Sky Dragon` werden auf den echten Kartennamen normalisiert, bevor die stabile YGOPRODeck-Karten-ID geladen wird.
- Keine unscharfe Karten-Zuordnung im letzten Fallback: nur exakte Kartennamen werden akzeptiert.
- Deutsche physische Setcodes bleiben Inventaridentitaet; der EN-Code dient nur als Referenz.
- Regression: bestehender Pfad `YGLD-DEC04` bleibt unveraendert.

## Installer

- Alte Update-Verzeichnisse und alte `GameCollector-v*-update.zip` werden weiterhin erst nach erfolgreichem Healthcheck entfernt.
- Backups, `.env`, Daten, Uploads und Datenbank/Volumes bleiben unangetastet.
