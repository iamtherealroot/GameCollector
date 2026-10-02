# GameCollector v2.15.1

Dieses Korrekturupdate erweitert die eigentliche Filmreihen-Detailseite. v2.15.0 hatte bereits die Titelsuche verbreitert, die Reihenansicht selbst lud jedoch weiterhin nur eine einzelne TMDB-Collection.

## Behoben

- Zusammengehörige, von TMDB getrennt geführte Film-Collections werden als Filmfamilie gemeinsam angezeigt.
- Bei Batman erscheinen dadurch neben den Filmen von 1989 bis 1997 auch passende weitere TMDB-Reihen wie „The Dark Knight“ und „The Batman“.
- Die Erkennung arbeitet über originale, übersetzte und alternative TMDB-Collection-Namen und gilt allgemein für Filmreihen.
- Bereits vorhandene Exemplare sowie manuelle Status- und Box-Zuordnungen aus den Einzelreihen bleiben erhalten.
- Derselbe Film und dieselbe physische Box werden in der Familienansicht nur einmal gezählt.

## Installation

```bash
cd /opt/gamecollector/updates/v2.15.1
sudo bash install.sh
```

Vor der Installation werden Programm und Datenbank gesichert. Anschließend folgen Container-Neubau und Deep-Healthcheck mit automatischem Rollback bei einem Fehler.
