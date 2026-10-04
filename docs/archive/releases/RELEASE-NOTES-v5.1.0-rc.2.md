# Bibo 5.1.0-rc.2 – persönlicher Meldungsabschluss und Tutorial-Schalter

Unveröffentlichter Prüfentwurf. Enthält alle Änderungen aus 5.1.0-rc.1.

- „Für mich als erledigt markieren“ bestätigt die Aufnahme einer eigenen Meldung und entfernt sie aus den eigenen offenen Meldungen. Der technische Bearbeitungsstatus, die Priorität und die Admin-Aufgabe bleiben unverändert. Persönlicher Abschluss lässt sich rückgängig machen.
- Eigene offene Meldungen und Admin-Aufgaben besitzen getrennte Buttons/Zähler. Der Admin-Aufgaben-Button bleibt als Übersicht auch bei null offenen Aufgaben sichtbar. Admins dürfen fremde Meldungen nicht für deren Ersteller persönlich abschließen.
- Die persönliche Übersicht zeigt „Für mich abgeschlossen“; der Filter „Nur offene Meldungen“ berücksichtigt diesen Zustand. Neue öffentliche Antworten werden weiterhin als Nachrichten zugestellt, auch wenn die Meldung persönlich abgeschlossen ist.
- „Tutorial dauerhaft ausschalten“ direkt in der Dashboard-Führung sowie Einstellungen unter Hilfe & Feedback und Mein Konto. Die Einstellung gilt pro Nutzer, geräteübergreifend und versionsunabhängig. Andere Nutzer bleiben unbeeinflusst.
- Nach erfolgreicher Anmeldung zeigt „Was ist neu?“ alle dokumentierten Update-Einträge seit dem vorherigen Login, einschließlich übersprungener Versionen und noch unbestätigter Hinweise, chronologisch. Die Bestätigung speichert sämtliche angezeigten Versionen; neue Anmeldungen verlieren keine noch ungelesenen Hinweise. Bestehende Konten ohne Login-Datensatz verwenden den zuletzt bestätigten Versionsstand, neue Konten zunächst die aktuelle Version. Login-Historie wird ab diesem Entwurf erfasst, nicht rückwirkend erfunden.
- Bewusstes manuelles Starten des Tutorials ist weiterhin möglich. Erneutes Aktivieren erlaubt die automatische Einführung wieder. „Was ist neu?“ bleibt ein separater einmaliger Release-Hinweis.
- Neue Tabellen werden beim einmaligen Init angelegt; bestehende Meldungsstatus und Nutzerpräferenzen bleiben erhalten. Release-/RC-Regeln aus rc.1 gelten unverändert.

Lokale Backend-/Rechte-/Datenschutz-/Bestätigungsregressionen, JavaScript-DOM-Vertragstests und Shell-/Templateprüfung bestanden. Tatsächlicher Docker-Lauf und visuelle Prüfung dieses Prüfstands sind noch in der TU erforderlich; hier ist Docker nicht verfügbar. Keine Veröffentlichung oder Produktionsinstallation durchgeführt. Offene 4.8-/4.9-Punkte sowie OVP-Meldung #1 bleiben offen.
