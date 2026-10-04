# Bibo-Fehlerseite für Nginx Proxy Manager

Die eigenständige Seite benötigt keine Dateien von der Bibo-Anwendung und
keine externen Schriftarten, Bilder oder Dienste. Sie bleibt bei einem
Bibo-Ausfall verfügbar, solange Nginx Proxy Manager selbst erreichbar ist.
Sie prüft alle 15 Sekunden /health und meldet die Wiedererreichbarkeit.
Navigation erfolgt ausschließlich durch einen Klick auf den Button.
Es gibt keine automatische Wiederholung von Formularen.

## Einrichtung auf dem Rechner mit Nginx Proxy Manager

ZIP entpacken und den Namen des NPM-Containers ermitteln:

~~~bash
docker ps --format 'table {{.Names}}\t{{.Image}}'
~~~

Danach (CONTAINERNAME durch den NPM-Namen ersetzen):

~~~bash
sudo bash Bibo-502-Seite/install-npm-page.sh CONTAINERNAME
~~~

Das Skript kopiert nur die HTML-Datei in das persistente /data-Verzeichnis.
Es verändert keine Proxy-Konfiguration. /data muss wie bei der üblichen
NPM-Installation durch einen persistenten Volume-Mount gesichert sein.

In Nginx Proxy Manager den Proxy Host games.it-messer.de bearbeiten.
Unter Advanced den Inhalt von npm-advanced.conf zusätzlich eintragen.
Vorhandene Einstellungen beibehalten. Falls dort bereits error_page-Direktiven
für 502, 503 oder 504 existieren, diese durch die neuen ersetzen.
Speichern. NPM übernimmt die Konfiguration über seine Oberfläche.

## Verhalten

502, 503 und 504 zeigen die Bibo-Seite; der ursprüngliche HTTP-Fehlerstatus
bleibt erhalten. Die interne HTML-Adresse ist nicht öffentlich aufrufbar.
Andere Fehler und die normalen Bibo-Seiten werden nicht ersetzt.
Die lokale Vorschau zeigt erwartungsgemäß keinen erreichbaren /health-Endpunkt.

Zum Rückbau die hinzugefügten Zeilen aus Advanced entfernen und speichern.
Die HTML-Datei kann anschließend aus /data/bibo-errors entfernt werden.
