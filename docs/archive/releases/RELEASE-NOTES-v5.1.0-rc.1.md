# Bibo 5.1.0-rc.1 – Feedback-Orientierung und TU-Testfreigabe

Unveröffentlichter Prüfentwurf auf Basis des freigegebenen 5.0.4-Releases. Keine GitHub-Veröffentlichung oder Produktionsinstallation ohne ausdrücklichen Auftrag.

## Meldungen und Nachrichten

- Lokale, regelbasierte Kategorie-/Dringlichkeitsvorschläge: Fehler, Qualitätsverbesserung, neue Funktion, Änderung oder unklar; kritisch/hoch/normal/niedrig. Kein externer KI-Dienst, keine automatische Erledigung. Negierte kritische Begriffe werden in einfachen Fällen berücksichtigt; sprachliche Mehrdeutigkeit erfordert Admin-Prüfung.
- Admins können Vorschläge korrigieren. Kategorie und interne Dringlichkeit bleiben getrennt; Nutzer sehen keine interne Priorität.
- Offene Meldungen bleiben mit einem Admin-Zähler sichtbar, auch nach dem Öffnen. Nur erledigt/abgelehnt/Duplikat schließen den Hinweis. Filter nach Status, Kategorie, Typ und Dringlichkeit; offene kritische Meldungen zuerst.
- Öffentliche Antworten und Status-/Zielversionsänderungen erzeugen persönliche Nachrichten für den Ersteller, außer bei eigenen Antworten. Explizites „Als gelesen markieren“, dauerhafte Speicherung, keine Nachrichten aus internen Notizen, kein Zugriff auf Nachrichten anderer Nutzer.
- Bestehende Meldungen werden beim Init kategorisiert. Bereits gesetzte Prioritäten bleiben erhalten; alte Antworten werden nicht als neue Nachrichten wiederholt.

## Testfreigabe

- Nur für Systemadministratoren in einer explizit aktivierten TU mit isolierter Datenbank bibo_test.
- Prüfliste, versioniertes Protokoll und Rücknahme der Freigabe. Versions-/Sitzungsbindung und Fingerabdruck verhindern die Weiterverwendung bei geändertem Stand.
- Nach Freigabe wird ein Bash-Befehl für das Produktions-Update angezeigt. Keine automatische Ausführung, kein Rückimport von TU-Daten, keine GitHub-Freigabe. Der Befehl prüft Archivpfade und den getesteten Paketstand inklusive App, Skripten, Installer, Abhängigkeiten und Compose-Dateien.
- Die Freigabe bestätigt ein Prüfergebnis, nicht automatisch die Sicherheit aller Datenbankmigrationen. Produktionsinstaller sichert Code und SQL; Bilder werden erhalten, aber nicht als vollständiges neues Dateibackup im Update-Backup gesichert.

## Versionsfolge

- X.Y.Z: Hauptversion / neue kompatible Funktionen / Korrekturen. Prüfstände X.Y.Z-rc.1, rc.2 usw.; nach Freigabe X.Y.Z. Keine Umnummerierung alter Releases.
- Stabile automatische Updates wählen keine RC-Pakete. Ein neuerer installierter RC wird nicht durch ein älteres stabiles Release ersetzt. Direkte RC-Installation nur bewusst mit BIBO_ALLOW_PRERELEASE=1.
- GitHub-Workflow kennzeichnet später ausdrücklich veröffentlichte RCs als Prerelease; dieser Entwurf wird nicht hochgeladen.

## Prüfung

Backend-, Datenschutz-, Rechte-, Einstufungs-, Nachrichten-, TU-Freigabe- und Versionsregressionen sowie Shell-/Template-/JavaScript-Vertragstests werden lokal geprüft. Docker und visuelle Browserprüfung dieses neuen Entwurfs müssen in der TU erfolgen; in dieser Arbeitsumgebung ist Docker nicht verfügbar. Offene 4.8-/4.9-Punkte und der OVP-Hinweis aus Meldung #1 sind nicht mit diesem Entwurf behoben.
