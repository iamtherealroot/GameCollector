# GameCollector v2.15.3

Dieses Update vervollständigt die Batman-Hauptfilmreihe in der Film-/Seriensammlung.

Enthalten sind chronologisch:

- Batman (1966)
- Batman (1989)
- Batmans Rückkehr (1992)
- Batman Forever (1995)
- Batman & Robin (1997)
- Batman Begins (2005)
- The Dark Knight (2008)
- The Dark Knight Rises (2012)
- The Batman (2022)

Die drei getrennten TMDB-Collections werden über stabile Collection- und Film-IDs zu einer Hauptfilmreihe verbunden. Animationsfilme, LEGO-Filme und reine Ensemblefilme bleiben eigenständige Reihen. Zukünftige Teile, die TMDB einer der verknüpften Collections hinzufügt, erscheinen weiterhin automatisch.

Eigene Exemplare und deren EAN, Edition, Medium, Zustand, Kaufdaten, Lagerort, Wert, Notizen, Besitzstatus und Box-Zuordnungen werden nicht überschrieben. Mehrere physische Exemplare bleiben einzeln bearbeitbar; Boxwerte werden weiterhin nur einmal gezählt.

Die Filmreihen-Zuordnung listet nun alle angelegten DVDs, Blu-rays und weiteren physischen Filmmedien auf, auch wenn bei einem älteren Datensatz das Herkunftsland noch fehlt. Einzel-Ausgaben verschwinden nach ihrer Zuordnung aus den anderen Film-Auswahllisten; erkannte Boxen und Mehrfilm-Ausgaben bleiben mehrfach verwendbar.

## Installation

```bash
cd /opt/gamecollector
mkdir -p updates/v2.15.3
unzip -o $HOME/Downloads/GameCollector-v2.15.3-update.zip -d updates/v2.15.3
cd updates/v2.15.3
sudo bash install.sh
```

Der Installer erstellt vor der Änderung ein Code- und Datenbank-Backup, baut Web und Scheduler neu und prüft anschließend den Healthcheck sowie die laufende Versionsnummer.
