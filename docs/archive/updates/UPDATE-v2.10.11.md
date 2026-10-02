# Collector v2.10.11 – Revision 2

## Änderungen
- „Reihen & Sammlungen“ wieder als Kachelansicht mit Fortschritt, sofern eine belastbare Gesamtzahl bekannt ist.
- Bewertungszentrale als Collector-weite Übersicht beschriftet.
- „Neueste Einträge“ mischt Spiele, Filme, Serien, Bücher, Musik und Sammelkarten chronologisch.
- Zusätzliche Ranglisten: Wertvollste Serien, Filme, Bücher, Musik und Sammelkarten.
- TV-Serien werden in der Wert-Rangliste nach Serie zusammengefasst; Staffel-/Box-Werte werden zum Serienwert addiert.
- Mengen werden bei Collector-Objekten im Ranglistenwert berücksichtigt.
- Lokaler ZIP-Installer übernimmt das Paket selbst, schützt .env/Uploads/Daten/Backups, erstellt Code- und PostgreSQL-Backup und prüft Version + Healthcheck vor Abschluss.

## Installation
```bash
cd /opt/gamecollector
mkdir -p updates/v2.10.11
unzip -o $HOME/Downloads/GameCollector-v2.10.11-r2-update.zip -d /opt/gamecollector/updates/v2.10.11
cd /opt/gamecollector/updates/v2.10.11
bash install.sh
```
