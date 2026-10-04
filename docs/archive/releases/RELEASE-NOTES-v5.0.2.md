# Bibo 5.0.2 – Prüfentwurf, nicht veröffentlicht

- „Verstanden“ und „Alle Änderungen ansehen“ nutzen eine signierte, nutzer-/sitzungsgebundene Bestätigung ohne neues Session-Cookie beim Laden. Damit entfällt ein möglicher Konflikt bei parallelen Requests. Die konkrete Ursache des Serverfehlers aus dem Screenshot ist ohne HTTP-Status/Serverlog nicht endgültig belegt.
- Erneuter Versuch lädt einen frischen Bestätigungstoken; bei Fehler lässt sich das Fenster trotzdem schließen. Die einmalige Anzeige bleibt pro Nutzer und Version gespeichert.
- Einführungstutorial erklärt die verfügbaren Menübereiche und Funktionen, mit Zurück/Weiter, Abschluss und „Tutorial überspringen“. Nur berechtigte Funktionen erscheinen. Überspringen/Abschluss gilt nutzerbezogen geräteübergreifend; erneuter Start unter Hilfe & Feedback.
- Startseitenbutton: Bücherregal-Symbol, kein sichtbarer Text, zugängliche Beschriftung und Tooltip.
- Docker-Testmigration kopiert die Produktionsdatenbank und Bilddateien in das separate Testprojekt. Vorherige Testdaten werden gesichert; SQL wird zunächst in einer Staging-Datenbank geprüft. Die vorherige Testdatenbank bleibt erhalten. Bilder werden zusammengeführt, alte reine Testbilder bleiben liegen. Produktion wird nicht verändert.
- Nach Import bleibt der Test-Scheduler deaktiviert. Produktions-.env und API-Schlüssel werden nicht kopiert. Verschlüsselte Integrationseinstellungen können mit dem separaten Testschlüssel nicht entschlüsselt werden.

Docker-Ausführung und visuelle Prüfung sind in dieser Arbeitsumgebung nicht möglich. Gemeinsamer Test auf dem Server steht aus. Die offenen Punkte aus 5.0.1 bestehen weiter. Keine GitHub-Veröffentlichung ohne ausdrückliche Freigabe.
