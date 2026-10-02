# Bibo v4.6.5 – Sammlungen, Nutzer und GitHub-Release

## Behoben

- Eigene Sammlungskategorien öffnen nach dem Anlegen direkt ihre neue Kategorie; dort kann sofort das erste Objekt hinzugefügt werden.
- Spielreihen aus globalen Katalogdaten erscheinen nicht mehr als `0/x`-Geistereinträge in leeren oder anderen Sammlungen.
- Der vorhandene Mehrfach-Exemplar-Workflow bleibt auch bei identischer EAN/UPC erhalten.
- Die kombinierte `install.sh` bleibt der einzige Einstiegspunkt für Neuinstallation und Update.

## Benutzer & Rechte

- Sammlungsverwalter sehen nicht mehr sämtliche Systembenutzer.
- Die Rechteansicht zeigt nur bestehende Mitglieder der aktiven Sammlung.
- Benutzer können unter **Konto → Zugriff anfragen** selbst Lese- oder Bearbeitungszugriff beantragen.
- Sammlungsverwalter können diese Anfragen genehmigen oder ablehnen.
- Neue Benutzer werden nicht mehr bei jedem Start automatisch der Standardsammlung hinzugefügt.
- Beim einmaligen Upgrade einer historischen Ein-Sammlungs-Installation bleiben bestehende Berechtigungen kompatibel.
- Systemadministratoren können bei der Benutzeranlage optional direkt eine Sammlung und Anfangsrolle auswählen.

## GitHub / Dokumentation

- README vollständig auf Bibo ausgerichtet.
- Installation und Update als ein gemeinsamer Ablauf dokumentiert.
- Funktionen, Rechtekonzept, Architektur, Datenquellen, Backup und Tests übersichtlich beschrieben.
- Bibo-Branding in die README eingebunden; echte Anwendungsscreenshots können unter `docs/images/` ergänzt werden.

## Upgrade

```bash
unzip Bibo-v4.6.5.zip
cd Bibo-v4.6.5
sudo bash install.sh
```

Die Routine erkennt automatisch, ob es sich um eine Neuinstallation oder ein Update handelt.
