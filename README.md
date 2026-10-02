<p align="center">
  <img src="app/static/branding/bibo-hero.png" alt="Bibo" width="720">
</p>

# Bibo

**Bibo** ist eine self-hosted Sammlungsverwaltung für physische Spiele, Filme, Serien, Bücher, Musik, Sammelkarten, Konsolen, Hardware, Zubehör und eigene Sammlungskategorien.

Statt nur Titel in einer Liste zu speichern, trennt Bibo bewusst zwischen **Katalogeintrag**, **konkretem Exemplar**, **Marktwert**, **persönlichen Angaben** und **Sammlungsfortschritt**. Mehrere physische Exemplare desselben Artikels – auch mit identischer EAN – bleiben deshalb eigenständige Datensätze mit eigenem Zustand, Kaufpreis, Lagerort, Notizen und Bewertung.

> Das Projekt hieß ursprünglich **GameCollector**. Der interne Installationspfad `/opt/gamecollector` bleibt aus Update- und Backup-Kompatibilitätsgründen bestehen.

## Highlights

- 🎮 Spielekatalog mit Plattformen, Editionen, Regionen, Produktcodes und Spielreihen
- 📦 beliebig viele konkrete Exemplare pro Katalogtitel
- 📷 mobiler EAN-/UPC-Scanner und Offline-Erfassungswarteschlange
- 🎬 Filme & Serien inklusive Boxsets, Staffeln und Reihenfortschritt
- 📚 Bücher mit ISBN, Autor, Verlag und Reihen
- 💿 Musik auf CD, Vinyl und weiteren Formaten
- 🃏 Sammelkarten inklusive TCG-spezifischer Daten
- 🕹 Konsolen, Hardwaremodelle und Zubehör
- 🗂 eigene Sammlungskategorien für Figuren, Modelle, Brettspiele usw.
- 💶 automatische und manuelle Marktwerte mit Preisverlauf
- 🧩 Serien-/Franchise-Fortschritt nur für die aktive Sammlung
- 👥 mehrere Benutzer und logisch getrennte Sammlungen mit Rollen/Rechten
- 🔐 Sammlungsverwalter sehen nur Mitglieder ihrer Sammlung und konkrete Zugriffsanfragen
- 💾 automatische Backups beim Update und Healthcheck nach Installation
- 📱 responsive Oberfläche und installierbare PWA

## Installation und Update

Jedes GitHub-Release enthält **ein einziges Paket**:

```text
Bibo-vX.Y.Z.zip
```

ZIP auf dem Server entpacken und aus dem entpackten Verzeichnis starten:

```bash
sudo bash install.sh
```

Die Installationsroutine erkennt selbstständig, welcher Modus benötigt wird.

### Neuinstallation

Wenn unter `/opt/gamecollector` noch keine Installation vorhanden ist, richtet der Installer Bibo vollständig ein:

- erzeugt `.env`, Datenbankpasswort und `SECRET_KEY`
- fragt das erste Administratorkonto ab
- startet PostgreSQL, Web-Anwendung und Scheduler
- prüft die Installation über den Deep-Healthcheck

Standardmäßig ist Bibo danach über den in `.env` gesetzten `APP_PORT` erreichbar.

### Update einer vorhandenen Installation

Sind `/opt/gamecollector/.env` und `/opt/gamecollector/docker-compose.yml` vorhanden, wechselt dieselbe Routine automatisch in den Update-Modus:

1. Code-Backup erstellen
2. PostgreSQL-Dump erstellen
3. neue Version übernehmen
4. Container neu bauen
5. Healthcheck durchführen
6. bei einem Fehler den vorherigen Programmstand wiederherstellen

Ein unvollständiger oder fremder Inhalt im Zielverzeichnis wird **nicht überschrieben**.

Ein anderer Installationspfad ist möglich:

```bash
sudo BIBO_INSTALL_DIR=/opt/bibo bash install.sh
```

Ausführliche Hinweise: [docs/INSTALLATION.md](docs/INSTALLATION.md)

## Sammlungsmodell

Bibo unterscheidet zwischen dem gemeinsamen Metadaten-Katalog und dem tatsächlichen Besitz einer Sammlung.

Ein Spiel kann beispielsweise einmal im Katalog vorhanden sein, während drei physische Exemplare dieses Spiels existieren. Jedes Exemplar kann unabhängig voneinander enthalten:

- Zustand und Vollständigkeit
- Kaufpreis und Kaufdatum
- automatischen Marktwert oder eigene Schätzung
- Lagerort
- Fotos
- Notizen und Tags
- Spielstatus

Eine bereits bekannte EAN blockiert deshalb **kein weiteres Exemplar**. Bibo bietet in diesem Fall gezielt „Weiteres Exemplar erfassen“ an.

## Benutzer, Sammlungen und Datenschutz

Bibo unterstützt mehrere logisch getrennte Sammlungen innerhalb derselben Installation.

Rollen innerhalb einer Sammlung:

| Rolle | Rechte |
|---|---|
| Lesen | Bestand und Auswertungen ansehen |
| Bearbeiten | Einträge und Metadaten pflegen |
| Verwalten | zusätzlich Benutzerrechte dieser Sammlung verwalten |
| Systemadministrator | globale Benutzer-/Sammlungsverwaltung und Systemeinstellungen |

Sammlungsverwalter erhalten **keine globale Benutzerliste**. Ein Benutzer kann stattdessen unter **Konto → Zugriff anfragen** eine konkrete Sammlung auswählen und um Lese- oder Bearbeitungszugriff bitten. Erst diese Anfrage wird dem jeweiligen Verwalter angezeigt.

## Eigene Sammlungskategorien

Neben Games, Filmen, Serien, Büchern, Musik und Karten lassen sich eigene Bereiche anlegen, zum Beispiel:

- Figuren
- Brettspiele
- Modelle
- Steelbooks
- Merchandise

Nach dem Erstellen öffnet Bibo die neue Kategorie direkt und bietet dort **„Objekt anlegen“** an. Die Zuordnung wird am einzelnen Sammlungsobjekt gespeichert.

## Spielreihen und Fortschritt

Serien-Metadaten können global im Katalog vorhanden sein, die Fortschrittsanzeige ist jedoch sammlungsbezogen. Eine neue oder leere Sammlung sieht daher keine Reihen einer anderen Sammlung als künstliche `0/x`-Einträge.

Für bekannte Reihen können lokale kuratierte Daten und optional RAWG-Metadaten kombiniert werden. Physischer Besitz und Marktwerte werden ausschließlich aus den Exemplaren der aktiven Sammlung ermittelt.

## Bewertung und Datenquellen

Je nach Medientyp kann Bibo verschiedene Quellen verwenden. Unterstützt bzw. vorbereitet sind unter anderem:

- eBay Browse API
- PriceCharting
- PrixRetro
- VGPreise
- RAWG
- RetroBase Collection
- TMDB
- OpenLibrary
- TCGdex

Spielepreise aus eBay-Angeboten vergleichen gleiche Vollständigkeit und benötigen mindestens fünf passende Angebote. Große Preissprünge bleiben bis zu einem bestätigenden Abruf frühestens 24 Stunden später zur Prüfung vorgemerkt.

Externe Metadaten und Preise ersetzen keine sammlungsspezifischen Angaben wie Zustand, Kaufpreis, Lagerort oder persönliche Notizen.

## Architektur

- Python / Flask
- Gunicorn
- PostgreSQL 17
- Docker Compose
- separater Scheduler
- PWA / mobiler Scanner
- Reverse-Proxy-fähig, z. B. mit Nginx Proxy Manager

Weitere Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Screenshots

Die README verwendet bereits das Bibo-Branding. Für die öffentliche GitHub-Seite sind zusätzlich echte Screenshots vorgesehen, idealerweise:

1. Startseite / Sammlungsbereiche
2. Bibliothek
3. Spiele- oder Medien-Detailansicht mit mehreren Exemplaren
4. Scanner auf dem Smartphone
5. Reihen-/Fortschrittsansicht
6. Bewertungsdashboard

Die Bilder können unter `docs/images/` abgelegt und danach hier direkt eingebunden werden. So zeigen wir den tatsächlichen Release-Stand statt künstlicher Mockups.

## Backup

Updates erzeugen automatisch ein Backup des bisherigen Programmstands und einen PostgreSQL-Dump. Zusätzlich bietet Bibo eine eigene Backup-Funktion für vollständige Sicherungen.

Vor größeren manuellen Änderungen sollte trotzdem ein externes Backup des Installationshosts vorhanden sein.

## Entwicklung und Tests

Wichtige Regressionstests liegen unter `scripts/`, darunter:

```bash
python scripts/test_game_price_stability.py
python scripts/test_duplicate_ean.py
python scripts/test_collection_isolation.py
python scripts/release_smoke.py
```

Für Release-Builds:

```bash
bash scripts/build_release.sh 4.6.6
```

Dadurch entstehen `Bibo-v4.6.6.zip` und die passende SHA256-Prüfsumme.

## Datenschutz

Bibo ist für Self-Hosting ausgelegt. Sammlungsdaten liegen in der eigenen PostgreSQL-Datenbank. Externe Dienste werden nur für die jeweils konfigurierten Metadaten-/Preisfunktionen angesprochen.

Details: [docs/PRIVACY.md](docs/PRIVACY.md)

## Lizenz

Siehe [LICENSE](LICENSE).

## Projektstatus

Bibo wird aktiv weiterentwickelt. Release-Änderungen stehen im [CHANGELOG](CHANGELOG.md); größere technische Änderungen werden zusätzlich in versionsbezogenen Update-/Release-Notizen dokumentiert.
