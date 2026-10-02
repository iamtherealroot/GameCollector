# Bibo v4.6.3

Dieses Wartungsrelease korrigiert das erneute Erfassen bereits bekannter EANs.

## Neu

- Bekannte EANs zeigen eine verständliche Dublettenwarnung, blockieren das Anlegen aber nicht.
- Über „Weiteres Exemplar erfassen“ wird bei Games eine neue Kopie am bestehenden Katalogtitel angelegt.
- Bei Filmen, Serien, Büchern, Musik, Sammelkarten und eigenen Medien öffnet sich der vorausgefüllte Fragenkatalog.
- Persönliche Exemplardaten wie Zustand, Kaufpreis, Wert, Lagerort und Notizen bleiben leer und werden für jede Kopie separat erfasst.
- Inhalte von Serien-, Film- und Buchboxen werden für die neue Ausgabe vorausgefüllt.
- Zubehör kann aus dem EAN-Treffer heraus ebenfalls als weiteres eigenständiges Exemplar angelegt werden.

## Installation

```bash
cd $HOME/Downloads
unzip -o Bibo-v4.6.3-update.zip
cd Bibo-v4.6.3
sudo bash install.sh
```
