# GameCollector

GameCollector ist eine selbst gehostete Webanwendung zur Verwaltung physischer
Videospiele, Konsolen und Zubehörteile. Sammlung, Katalog, Serienfortschritt,
Zustände, Cover, Marktwerte und Preisentwicklung bleiben auf dem eigenen
Server. Die Oberfläche ist für Desktop, Tablet und Mobilgeräte ausgelegt.

## Funktionen

- gemeinsamer Spielekatalog mit EAN/UPC-, Titel- und Barcode-Suche
- Exemplare mit Zustand, Vollständigkeit, Kaufpreis und Schätzwert
- Hardwarevarianten und Zubehör einschließlich modellspezifischer Bestandteile
- Serienansicht mit Plattformvarianten, Gesamtwerten und Fortschritt
- eBay-, PrixRetro- und weitere optionale Preisquellen mit Preisverlauf
- Gewinner/Verlierer, Gesamtwertentwicklung und automatische Neubewertung
- Benutzerrollen, CSV-Datenpflege, Backup und Qualitätsprüfungen
- responsive Navigation und installierbare PWA

GameCollector konzentriert sich auf **physisch erschienene Produkte**. Rein
digitale Mobilspiele, abgeschaltete Online-Dienste sowie ausschließlich digital
vertriebene DLCs und Season Passes werden im kuratierten Serienbestand nicht
geführt.

## Schnellstart

Voraussetzungen: Linux, Git, Docker Engine und Docker Compose v2.

```bash
sudo git clone https://github.com/iamtherealroot/GameCollector.git /opt/gamecollector
sudo bash /opt/gamecollector/install.sh
```

Der Installer erzeugt eine private `.env` und startet PostgreSQL,
Webanwendung und Scheduler. Anschließend ist GameCollector standardmäßig unter
`http://SERVER-IP:8095` erreichbar.

Ohne weitere Angaben lautet die vorläufige Erstkennung `admin` / `admin`.
Nach dem ersten Login muss zwingend ein neues Passwort vergeben werden; vorher
sind alle übrigen Bereiche gesperrt. Eine eigene Erstkennung kann bei einer
leeren Datenbank vorgegeben werden:

```bash
sudo env ADMIN_USERNAME=meinadmin ADMIN_PASSWORD='Sicheres-Passwort-2026' \
  bash /opt/gamecollector/install.sh
```

Bei Updates werden vorhandene Benutzerkonten und Passwörter nicht verändert.

## Aktualisieren über GitHub

```bash
sudo bash /opt/gamecollector/install.sh
```

Der Installer prüft lokale Änderungen, erstellt ein Datenbank- und Codebackup,
führt einen Fast-Forward-Pull von `main` aus, baut die Container neu und prüft
`/health/deep`. Bei einem Fehler wird der vorherige Code wiederhergestellt.
PostgreSQL-Volume, `.env` und Uploads werden niemals durch den Pull ersetzt.

Für einen kontrollierten Test ohne Git-Pull:

```bash
sudo bash /opt/gamecollector/install.sh --no-pull
```

Eine bestehende, noch nicht mit Git verbundene Installation kann übernommen
werden. Siehe [Installations- und Migrationsanleitung](docs/INSTALLATION.md).

## Konfiguration

Alle privaten Einstellungen stehen in `/opt/gamecollector/.env`. Die Vorlage
[.env.example](.env.example) enthält keine nutzbaren Zugangsdaten. eBay kann
nach der Erstanmeldung im Nutzermanagement eingerichtet werden; RAWG ist
optional. Für HTTPS hinter einem Reverse Proxy sollte `COOKIE_SECURE=1` gesetzt
werden.

## Datensicherheit

Das Repository enthält keine Sammlung, Datenbank, Uploads, API-Schlüssel,
Benutzerkonten oder privaten Serverpfade. Diese Dateien sind per `.gitignore`
und `.dockerignore` ausgeschlossen. Trotzdem sollte vor jedem öffentlichen
Commit geprüft werden, dass keine Exporte oder `.env` hinzugefügt wurden.

## Dokumentation

- [Installation und Migration](docs/INSTALLATION.md)
- [Updates und Wiederherstellung](docs/UPDATES.md)
- [Architektur](docs/ARCHITECTURE.md)
- [Datenschutz und Datenhaltung](docs/PRIVACY.md)
- [Änderungsverlauf](CHANGELOG.md)
- [Mitwirken](CONTRIBUTING.md)

## Lizenz

GameCollector ist freie Software unter der [GNU General Public License v3.0](LICENSE).
