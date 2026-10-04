# Bibo 5.0.0 – Prüfentwurf

Nicht auf GitHub veröffentlicht. Veröffentlichung erst nach ausdrücklicher Freigabe.

## Verständliche Navigation

Ein gemeinsames Menü für Desktop und mobile Geräte mit Icons, erklärten Funktionen und markiertem aktuellem Bereich: Meine Sammlung, Hinzufügen, Werte & Preise, Verwalten, Hilfe & Feedback und berechtigungsabhängige Administration. Eigene Sammlungskategorien werden eingebunden. Mobile Gruppen öffnen per Antippen; das Menü bietet eine Funktionensuche. Unter „Welche Funktion finde ich wo?“ steht ein durchsuchbares Verzeichnis bereit. Bestehende URLs bleiben erhalten.

Direkte Dashboard-Aktionen: Objekt hinzufügen, Barcode scannen, Feedback senden und Funktionen finden. Änderungsaktionen werden bei reinem Lesezugriff ausgeblendet.

## Privates Feedback-Portal

Nutzer können Verbesserungen und Fehler mit Titel, Beschreibung, Bereich und Screenshots einsenden. Die Bibo-Version wird automatisch ergänzt. „Meine Meldungen“ zeigt eigene Einreichungen und Antworten; auch Nutzer ohne Sammlungszugriff können Feedback senden.

Systemadministratoren können alle Meldungen durchsuchen, nach Typ und Status filtern, priorisieren, einer geplanten Version zuordnen und beantworten. Interne Admin-Notizen und ihre Bilder sind für Nutzer und Sammlungsverwalter nicht zugänglich. Status: Eingereicht, In Prüfung, Geplant, In Arbeit, Erledigt, Abgelehnt und Duplikat. Status und Zielversion werden im öffentlichen Verlauf der jeweiligen privaten Meldung dokumentiert. Es gibt keine öffentliche Meldungsübersicht und keine automatische Übertragung an GitHub.

Uploads: PNG, JPEG und WebP, maximal vier Bilder je Beitrag und 20 je Meldung, fünf MB und zwölf Megapixel je Bild. Bilder werden geprüft, verkleinert, als JPEG neu erzeugt und von eingebetteten Metadaten befreit. Die private Bildroute prüft Anmeldung, Eigentümer und Adminrechte; Antworten werden nicht gecacht. Sitzungstoken schützen neue Aktionen, Revisionsprüfung verhindert überschreibende gleichzeitige Bearbeitung. Begrenzung: zehn neue Meldungen je 24 Stunden und 30 Antworten je Stunde und Konto.

## Installation, Speicherung und Sicherung

Vollständiges Paket für Neuinstallation und Update: `Bibo-v5.0.0.zip`. Außerhalb der bestehenden Installation entpacken und `sudo bash install.sh` starten. Alternativ mit dem Startskript aus Downloads installieren. Vor einem Test auf dem bestehenden Server ein vollständiges Backup erstellen; vorzugsweise zunächst separat testen.

Drei neue Datenbanktabellen werden beim Start angelegt. Bestehende Sammlungsdaten werden nicht umgebaut. Private Bilder liegen im neuen persistenten Ordner `feedback-uploads/`, **außerhalb** von `uploads/` und des öffentlichen Static-Verzeichnisses. Docker bindet ihn separat ein. Nicht über Nginx oder andere Dateifreigaben öffentlich zugänglich machen.

Das Bibo-Komplettbackup enthält die Feedbackbilder; ein reiner SQL-Export enthält nur ihre Metadaten. Bei Wiederherstellung `feedback-uploads/` neben `uploads/` zurückspielen. Updates überschreiben diesen Ordner nicht. Ein Code-Rollback lässt die neuen Tabellen bestehen, macht das Portal in älteren Versionen aber nicht verfügbar.

## Noch vor Release prüfen

Automatisierte Prüfungen erfolgreich: alle neun vorhandenen/neuen Regressionstestskripte einschließlich sieben Preisstabilitätsfällen, 113 Templates, 216 Routen sowie Anmeldung und 17 Kernseiten. Der Test für Zugriffsanfragen nutzt getrennte Login-Kontexte; Nutzer ohne Sammlungsrechte können nun ihre eigene Zugriffsanfrage tatsächlich absenden.

- Desktop: Gruppen öffnen, Unterpunkte verstehen, aktuelle Bereiche erkennen, Tastatur/Escape testen.
- iPhone: Menü antippen, nach Funktionen suchen, Bilder auswählen und Meldung senden.
- Nutzer: ausschließlich eigene Meldungen sehen und auf Admin-Rückfragen antworten.
- Systemadministrator: Status/Zielversion ändern und interne Notizen samt Bildern prüfen.
- Container-Update, persistente Bilder nach Neustart und Komplettbackup auf einer Testinstallation prüfen.

Keine Produktionseinrichtung oder GitHub-Veröffentlichung in diesem Entwurf. Browserdarstellung und Docker-Betrieb sind hier noch nicht visuell bzw. im Container geprüft.
