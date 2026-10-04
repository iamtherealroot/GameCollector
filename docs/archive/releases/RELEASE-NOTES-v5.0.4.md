# Bibo 5.0.4 – Feedback, globale Top 10 & Dashboard-Führung

Am 3. Oktober 2026 zur GitHub-Veröffentlichung freigegeben. Enthält die Änderungen der Prüfentwürfe 5.0.0 bis 5.0.4; 4.8 und 4.9 wurden nicht als eigenständige Releases veröffentlicht.

## Seit dem letzten veröffentlichten Release 4.7.1

- Privates Verbesserungsportal mit Bildern, Kommentaren und Bearbeitungsstatus; Systemadministratoren verwalten alle Vorschläge, Sammlungsverwalter erhalten keinen globalen Nutzerzugriff.
- Globale Top 10 der wertvollsten physischen Produkte je Kategorie innerhalb derselben Bibo-Instanz. Erst ab zwei angelegten Sammlungsdatenbanken verfügbar. Persönliche Anzeige und Teilnahme einer Sammlung sind getrennt und standardmäßig deaktiviert; öffentliche Anzeigen verwenden freigegebene Aliase.
- Verständlich gruppierte Desktop-/Mobilnavigation und Funktionssuche.
- Einmaliges „Was ist neu“-Fenster je Nutzer und Release, mit gespeicherter Bestätigung und verbessertem Fehlerverhalten.
- Separater, gesperrter Datenbank-Initialisierungsschritt vor Web-Workern und Scheduler verhindert konkurrierende Schemaerstellung.
- Isolierte Docker-TU, Testbefehle und expliziter Produktionsdatenimport ausschließlich in die TU, mit Sicherung des vorherigen Teststands. Kein Zurückimport in Produktion.

## Dashboard und Teststarter

- Bücherregal mit warmem Holz, bunten Buchrücken und leicht versetzten Büchern; kein sichtbarer Text auf dem Startseitenbutton, weiterhin zugängliche Beschriftung. Hoverbewegung respektiert reduzierte Animationen.
- Neue Einführung direkt im Dashboard: hervorgehobene reale Elemente für Suche, Konto/Sammlungswechsel, Erfassung, Sammlungsbereiche, Gesamtwert und verfügbare Menüs. Die Tour öffnet die passende Desktop-/Mobilnavigation, erklärt Funktionen daneben und bietet Zurück/Weiter/Überspringen. Tastaturfokus bleibt in der Hilfe; Escape beendet bzw. bestätigt sie. Verborgene oder nicht berechtigte Ziele werden übersprungen.
- Abschluss wird pro Nutzer gespeichert. Die neue Dashboard-Tour ist unabhängig vom alten dialogbasierten Tutorial, damit auch bisherige Tester sie sehen. Erneut unter Hilfe & Feedback starten.
- Dauerhaftes TESTUMGEBUNG-Banner inklusive Version, auch auf dem Login.
- TU: test-admin vorausgefüllt, Anmeldung ohne Passwort. Kein automatisches Login; andere Nutzer benötigen weiterhin ihr Passwort. Die Freischaltung erfordert explizite Testflags, Test-admin-Konfiguration und die isolierte PostgreSQL-Datenbank bibo_test. Produktions-Compose setzt diese Flags nicht.
- Verständliche Leerzustände mit passendem Erfassungslink und Hinweisen bei Leserechten. Top-10-Status erklärt fehlende zweite Datenbank, deaktivierte persönliche Anzeige oder fehlende Freigaben.
- Dashboard für neue Nutzer ohne zugewiesene Sammlung: fehlende Besitzer-ID bei eigenen Kategorien wird abgefangen statt einen internen Fehler auszulösen.
- Desktop-Starter `scripts/bibo-tu.sh`: überträgt das Paket per SSH/SCP, richtet ausschließlich /opt/bibo-test ein, übernimmt vorherige Test-Zugangsdaten, startet TU und lokalen Tunnel und öffnet den Browser. `--open-only` öffnet nur eine laufende TU. Enter/Strg+C schließt nur den eigenen Tunnel, nicht Container.
- SSH-/sudo-Anmeldung bleiben notwendig. Nur der Bibo-Testlogin ist passwortlos. Testport bleibt an Server-Loopback gebunden, es wird kein LAN-/Internet-Port freigegeben.
- Startablauf aus 5.0.3 bleibt erhalten. Kein automatischer Import von Produktionsdaten. Die vorgeschlagene TU-Freigabeoberfläche ist für einen späteren Entwurf vorgesehen und nicht enthalten.

## Prüfung und Grenzen

Lokale Backend-Regressions-, Shell-Syntax-, DOM-Vertrags- und simulierte Launcher-Tests bestanden. Der Nutzer hat Docker-TU, Produktionsdatenimport in die TU und ersten Sichtcheck bestätigt. Ein erfolgreicher Produktions-Updateabschluss wurde zum Zeitpunkt der Freigabe noch nicht dokumentiert. DOM-Vertragstests ersetzen keine vollständige visuelle Prüfung auf Desktop/iPhone.

Offene 4.8-/4.9-Punkte bleiben ausdrücklich offen: umfassende CRUD-Prüfung aller Medien, strikter Preisabgleich nach Region/Edition/Zustand, weitere Katalogbereinigung und vollständiger Datei-Backup-/Restore-Test. Details in RELEASE-NOTES-v5.0.1.md. Installation und Update erfolgen mit `bash install.sh`; vorhandene Produktionsdaten und Konfiguration werden beibehalten, Testflags sind im Produktions-Compose nicht gesetzt.
