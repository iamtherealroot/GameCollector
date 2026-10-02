<p align="center">
  <img src="app/static/branding/bibo-hero.png" alt="Bibo – deine Sammlung an einem Ort" width="720">
</p>

<h1 align="center">Bibo</h1>
<p align="center"><strong>Deine Sammlung. Dein Server.</strong><br>Spiele, Filme, Bücher, Musik und mehr übersichtlich verwalten.</p>
<p align="center">
  <a href="https://github.com/iamtherealroot/GameCollector/releases/latest"><img src="https://img.shields.io/github/v/release/iamtherealroot/GameCollector?label=Release" alt="Aktuelles Release"></a>
  <a href="https://github.com/iamtherealroot/GameCollector/actions/workflows/ci.yml"><img src="https://github.com/iamtherealroot/GameCollector/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/Lizenz-GPL--3.0-blue" alt="GPL-3.0"></a>
</p>
<p align="center">
  <a href="https://github.com/iamtherealroot/GameCollector/releases/latest">Download</a> ·
  <a href="docs/INSTALLATION.md">Installation</a> ·
  <a href="docs/README.md">Dokumentation</a> ·
  <a href="https://github.com/iamtherealroot/GameCollector/issues">Fehler melden</a>
</p>

## Was kannst du sammeln?

| Bereich | Beispiele |
|---|---|
| 🎮 Spiele | Plattformen, Editionen, EAN, Produktcodes und Spielreihen |
| 🎬 Filme & Serien | Einzelveröffentlichungen, Boxsets und Staffeln |
| 📚 Bücher & 💿 Musik | ISBN, Autoren, CDs, Vinyl und weitere Formate |
| 🃏 Sammelkarten | TCG-spezifische Angaben und Sammlungsdaten |
| 🕹 Hardware & Zubehör | Konsolenmodelle, Varianten und konkrete Exemplare |
| 🗂 Eigene Kategorien | Figuren, Brettspiele, Modelle oder Merchandise |

**Jedes Exemplar zählt.** Mehrere Kopien mit derselben EAN können jeweils einen eigenen Zustand, Kaufpreis, Lagerort, Fotos und Notizen haben. Katalogdaten und persönlicher Besitz werden getrennt verwaltet.

Eigene Dashboard-Kategorien lassen sich bearbeiten oder entfernen. Objekte können einzeln oder gemeinsam neu zugeordnet werden; beim Entfernen einer Kategorie bleibt ihr Bestand erhalten. [Anleitung](docs/CATEGORIES.md)

## Das steckt drin

- **Schnell erfassen:** EAN-/UPC-Scanner auf dem Smartphone, Suche und CSV-Import.
- **Den Überblick behalten:** Reihenfortschritt, Marktwerte, Preisverlauf und Auswertungen für deine aktive Sammlung.
- **Gemeinsam sammeln:** getrennte Sammlungen, Lese-/Bearbeitungsrechte und Zugriffsanfragen. Sammlungsverwalter sehen Mitglieder ihrer Sammlung und konkrete Anfragen.
- **Mobil nutzen:** responsive Oberfläche und installierbare PWA.
- **Selbst betreiben:** Docker Compose mit PostgreSQL, Webanwendung und Scheduler; automatische Backups beim Update.

### Preise mit vergleichbaren Exemplaren

Lose Spiele werden mit losen, komplette mit kompletten und versiegelte mit versiegelten Angeboten verglichen. Der eBay-Vergleich benötigt mindestens fünf passende Angebote. Große Preissprünge werden erst nach einem bestätigenden Abruf frühestens 24 Stunden später übernommen; bis dahin bleibt der bisherige Wert erhalten.

Metadaten und Preisquellen sind je nach Bereich optional, etwa eBay, PrixRetro, VGPreise, RAWG, TMDB und OpenLibrary. API-Zugänge und Verfügbarkeit unterscheiden sich je Anbieter.

## Installation & Update

**Ein Paket, ein Installer:** Lade `Bibo-vX.Y.Z.zip` aus den [Releases](https://github.com/iamtherealroot/GameCollector/releases/latest) auf deinen Server und entpacke es **außerhalb des Installationsverzeichnisses**. Beispiel für v4.7.1:

```bash
unzip Bibo-v4.7.1.zip
cd Bibo-v4.7.1
sudo bash install.sh
```

Der Installer erkennt eine vorhandene Installation und führt ein Update durch. Bei einer Neuinstallation fragt er das erste Administratorkonto ab. Für Updates sichert er Programmstand, Konfiguration und Datenbank und prüft danach den Anwendungsstart.

**Voraussetzungen:** Linux, Docker Engine mit Compose v2, `tar`, `flock`, `openssl`; für Updates außerdem Python 3. Standardport: **8095**.

Der Standardpfad bleibt `/opt/gamecollector`, damit vorhandene Installationen weiter aktualisiert werden können. Das Projekt hieß zuvor **GameCollector**; der Repository-Name bleibt für bestehende Links erhalten.

[Installationsanleitung](docs/INSTALLATION.md) · [Update & Wiederherstellung](docs/UPDATES.md)

## Dokumentation

| Thema | Anleitung |
|---|---|
| Installieren und konfigurieren | [Installation](docs/INSTALLATION.md) |
| Aktualisieren und sichern | [Updates & Wiederherstellung](docs/UPDATES.md) |
| Dienste und Datenhaltung | [Architektur](docs/ARCHITECTURE.md) |
| Eigene Daten und externe Anbieter | [Datenschutz](docs/PRIVACY.md) |
| Änderungen dieser Version | [Release-Notizen v4.7.1](RELEASE-NOTES-v4.7.1.md) |
| Entwicklungsgeschichte | [Changelog](CHANGELOG.md) · [Dokumentationsarchiv](docs/archive/README.md) |

## Mitmachen

Fehler oder Ideen? Öffne ein [Issue](https://github.com/iamtherealroot/GameCollector/issues). Hinweise für Beiträge stehen in [CONTRIBUTING.md](CONTRIBUTING.md), der Umgang mit Sicherheitsmeldungen in [SECURITY.md](SECURITY.md).

Lokale Preisvergleichstests benötigen nur Python:

```bash
python3 scripts/test_game_price_stability.py
```

Weitere Prüfungen laufen in [GitHub Actions](https://github.com/iamtherealroot/GameCollector/actions). Für ein Release mit passender `APP_VERSION`:

```bash
bash scripts/build_release.sh 4.7.1
```

Bibo steht unter der [GPL-3.0](LICENSE).

### Automatisch das neueste Paket installieren

`scripts/bibo-update-latest.sh` vergleicht lokale Bibo-ZIPs in Downloads mit dem neuesten stabilen GitHub-Release. Die höchste Version wird installiert; bei gleicher Version wird das lokale Paket verwendet. Start: `sudo bash scripts/bibo-update-latest.sh`. Ein anderer Ordner kann über `BIBO_DOWNLOAD_DIR` angegeben werden. `BIBO_CHECK_ONLY=1` prüft nur das gewählte Paket.
