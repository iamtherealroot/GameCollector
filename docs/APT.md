# Bibo über APT aktualisieren

Das Paket bibo verwaltet eine bereits eingerichtete Docker-Installation.
Nach der einmaligen Übernahme aktualisiert apt upgrade Bibo direkt über den
bestehenden Installer: Backup einschließlich Wiederherstellungsprüfung,
Containerbau, Datenbankinitialisierung und Healthcheck. Währenddessen sind Web
und Scheduler kurz gestoppt. Konfiguration, Datenbank, Bilder und eigene Daten
bleiben am bisherigen Ort. Standardpfad ist /opt/gamecollector; abweichende
Pfade stehen in /etc/bibo-apt.conf.

## Einmalige Veröffentlichung auf Linux Mint

bash packaging/apt/setup-mint.sh mit der bestehenden GitHub-CLI-Anmeldung
ausführen. Der Starter fügt die Paketwerkzeuge und den APT-Workflow auf main
hinzu, richtet GitHub Pages für Actions ein und startet den ersten Paketbau.
Eine bereits anderweitig verwendete Pages-Website wird nicht überschrieben.
Bei erneuter Einrichtung auf einem anderen Rechner muss der gesicherte
Signaturschlüssel übernommen werden; der Starter wechselt ihn nicht automatisch.
Der lokale Signaturschlüssel liegt ausschließlich in
~/.local/share/bibo-apt-signing; eine Kopie wird als privates GitHub-Actions-
Secret gespeichert. Diesen Ordner privat sichern. Kein privater Schlüssel
gehört ins Repository, ZIP, Chat oder öffentliche Paketquelle.

Die Veröffentlichung läuft unter Actions → Bibo APT. Der Workflow übernimmt
immer das neueste vollständige stabile GitHub-Release, prüft dessen SHA256,
erstellt bibo_VERSION-1_all.deb und signiert die Repository-Metadaten.
Die Pakete werden als Pages-Artefakt veröffentlicht, nicht als große Git-Dateien.
Nach weiteren erfolgreichen Release-Workflows wird die APT-Quelle automatisch
aktualisiert. Eine manuelle Ausführung ist ebenfalls möglich.

## Einmalige Übernahme auf dem Server

Erst nach erfolgreichem Pages-Workflow das vom Mint-Starter ausgegebene
Serverkommando ausführen. Es vergleicht den öffentlichen Schlüssel mit dem
ausgegebenen Fingerprint, legt eine eigene Keyring-Datei und die Paketquelle
an und installiert bibo. Bei abweichendem Bibo-Pfad diesen als zweites
Argument an install-server.sh übergeben.

Danach:

~~~bash
sudo apt update
sudo apt upgrade
~~~

Nur Bibo aktualisieren:

~~~bash
sudo apt update
sudo apt install --only-upgrade bibo
~~~

apt update erneuert die Paketlisten. Erst die Installation/apt upgrade
aktualisiert die laufende Anwendung. Ein ungeprüftes Downgrade wird abgebrochen.
Bei einem fehlgeschlagenen Configure-Schritt bleibt das Paket unkonfiguriert;
nach Behebung der Ursache kann sudo dpkg --configure bibo erneut ausgeführt
werden. Der bestehende Installer versucht bei Fehlern, den vorherigen Code
wiederherzustellen; Datenbank-Backups stehen für eine gezielte Wiederherstellung
bereit. Datenbankmigrationen werden nicht durch ein bloßes Paket-Downgrade
rückgängig gemacht.

Bei apt remove bibo werden Web und Scheduler gestoppt. Datenbank, Volumes,
Konfiguration und Backups werden auch beim Purge nicht gelöscht.
Unattended-Upgrades berücksichtigen zusätzliche Paketquellen nur gemäß der
lokalen Serverkonfiguration; die Einrichtung aktiviert keine geplanten
Produktionsupdates.

GitHub Pages benötigt einmalig build_type=workflow. Der Workflow nutzt
pages: write und id-token: write für die Veröffentlichung; die Paketquelle
nutzt Signed-By, keine globale APT-Vertrauensfreigabe.

## Prüfung

Der GitHub-Workflow testet vor jeder Veröffentlichung den Paketinhalt,
Updatefehler und Wiederholungsversuche, den Downgrade-Schutz sowie den Erhalt
der Daten beim Entfernen. Eine lokale Testquelle muss von APT akzeptiert werden;
manipulierte signierte Metadaten müssen abgelehnt werden. Alle Testpfade und
Containerantworten sind isoliert. Ein fehlgeschlagener Test blockiert die
Veröffentlichung. Der Docker-Neubau wird erst auf dem echten Server ausgeführt.
