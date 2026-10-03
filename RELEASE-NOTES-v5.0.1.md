# Bibo 5.0.1 – zweiter 5.0-Prüfentwurf

Noch nicht veröffentlicht. Die Versionsnummer ist höher als beim ersten Entwurf, damit das lokale Startskript das Update erkennt.

## Ergänzungen

- Menügruppen bekommen sichtbare Button-Flächen wie „Startseite“.
- Globale Top 10 je Bereich: Games, Konsolen/Hardware, Zubehör, Filme, Serien, Bücher, Musik, Sammelkarten und weitere Sammlungen. Nur freiwillig freigegebene Sammlungen derselben Bibo-Installation nehmen teil.
- Jeder Nutzer kann seine eigene Top-10-Ansicht unter „Hilfe & Feedback → Globale Top 10 einstellen“ aktivieren und deaktivieren. Standard: aus. Verfügbar erst ab zwei angelegten Sammlungsdatenbanken (`CollectionSpace`); getrennte Bibo-Server zählen nicht mit.
- Freigabe von Sammlungsdaten ist ein separater Schalter für Sammlungsverwalter. Öffentliche Sammler-/Sammlungsnamen sind frei wählbar; echte Kontonamen, Notizen, Kaufpreise, Lagerorte, Bilder und private Objektlinks bleiben verborgen. Widerruf entfernt die Sammlung sofort.
- Rangliste nach Einzelwert des physischen Exemplars, nicht nach Mengen-Gesamtwert. Fixierte Werte bleiben wie in Bibo vorrangig und werden markiert; sonst automatischer Marktwert vor eigener Schätzung. Wunschlisten, digitale Spiele und Zubehörkomponenten mit bereits im Elternobjekt enthaltenem Wert werden ausgeschlossen.
- „Was ist neu?“-Dialog: Bestätigung je Konto und Anwendungsversion in der Datenbank. Nach „Verstanden“ auch auf anderen Geräten nicht erneut sichtbar. Beim nächsten Versionswechsel erscheint er wieder. Auch Leser ohne Sammlungszugriff dürfen ihren eigenen Hinweis bestätigen.
- Isolierte Docker-Testumgebung für zukünftige Releases: siehe [Anleitung](docs/DOCKER-TESTUMGEBUNG.md). Separate Testvolumes, localhost-Port 18095, Regressionstests und SQL-Wiederherstellung. In dieser Arbeitsumgebung noch nicht ausgeführt, da Docker nicht verfügbar ist.

Feedback-Portal und übrige Navigation aus dem ersten Entwurf bleiben enthalten. Neue Tabellen werden beim Start automatisch angelegt; bestehende Bestände werden nicht umgeschrieben. Vor der Installation vollständiges Backup erstellen und vorzugsweise separat testen.

## Stand der ursprünglichen 4.8-/4.9-Planung

Grundlagen aus den bisherigen Versionen und Regressionstests sind enthalten: weitere Exemplare trotz gleicher EAN, getrennte Sammlungen/Rechte, Kategorien bearbeiten und entfernen, Geldwert-Verarbeitung, gleicher Vollständigkeitsvergleich und zurückgestellte große Preissprünge mit sichtbaren Prüfhinweisen.

**Noch nicht vollständig abgeschlossen:** Prüfung sämtlicher Anlegen-/Speichern-/Bearbeiten-/Löschen-Abläufe für alle Medien, strikter Preisvergleich nach Region/Ausgabe/Zustand zusätzlich zur Vollständigkeit, vollständige Katalogbereinigung, visuelle Mobilprüfung sowie vollständige Neuinstallation/Update und Wiederherstellung einschließlich Bildern. Der frühere 4.8-/4.9-Plan ist daher nicht als komplett erledigt zu verstehen.

## Prüfen

Nach Update: Menüflächen prüfen, Top-10-Schalter bei einer/zwei Sammlungen testen, Anzeigenamen freigeben und widerrufen. Popup einmal bestätigen, neu anmelden und auf anderem Gerät prüfen. Container-Testumgebung auf einem Docker-Host ausführen. Release erst nach ausdrücklicher Freigabe.
