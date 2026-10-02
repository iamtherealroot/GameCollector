# Bibo v4.6.2 installieren

```bash
cd $HOME/Downloads
unzip -o Bibo-v4.6.2-update.zip
cd Bibo-v4.6.2
sudo bash install.sh
```

Das Update ist kumulativ. Frühere v4-Pakete müssen vorher nicht installiert werden.

Vorhandene Titel besitzen jetzt einen persönlichen Rezensionseintrag mit Gesamtwertung, medienabhängigen Einzelwertungen, Freitext, Stärken, Schwächen, Empfehlung, Favorit und Spoilerkennzeichnung. Diese Angaben sind vollständig von der automatischen Marktwertbewertung getrennt.

Nach erfolgreicher Installation verschiebt Bibo alle Ordner und ZIP-Dateien mit dem Namen `Bibo-v*` automatisch aus `$HOME/Downloads` nach `/opt/gamecollector/updates`. Dadurch werden auch die auf dem Screenshot sichtbaren älteren Bibo-Versionen aufgeräumt. Andere Dateien im Downloads-Ordner bleiben unverändert.
