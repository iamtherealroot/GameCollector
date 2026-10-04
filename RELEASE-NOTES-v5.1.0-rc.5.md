# Bibo 5.1.0-rc.5 – persönliche Besitzeranzeige

Unveröffentlichter Prüfentwurf. Enthält alle Änderungen aus rc.1 bis rc.4.

- Allgemeine administrative Konten mit Benutzernamen admin bzw. test-admin werden unabhängig von Groß-/Kleinschreibung nicht als Besitzer angezeigt. Persönliche Administratoren bleiben sichtbar; es wird nicht pauschal die Admin-Rolle ausgeschlossen.
- Konten, Berechtigungen und Daten bleiben unverändert. Sind keine persönlichen Sammlungsadministratoren vorhanden, wird kein beliebiger anderer Nutzer als Besitzer erfunden.
- Cover, Exemplare, Preisgleichstände, Teilnahme-Einstellungen und übrige Änderungen bleiben erhalten.

Lokale Backend-, Rechte-, Datenschutz- und Formularregressionen bestanden, einschließlich zusätzlicher allgemeiner Admin-Konten in der Besitzeranzeige. Docker-/Sichtprüfung bleibt in der TU erforderlich. Keine Produktionsinstallation oder Veröffentlichung.
