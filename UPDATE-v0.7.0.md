# GameCollector v0.7.0

Komfort- und Sammlungsupdate auf Basis von v0.6.0.

## Neu / erweitert
- Duplikat-Erkennung im Scanner: vorhandene Exemplare öffnen oder direkt ein weiteres Exemplar erfassen.
- CSV-Import kann bekannte Titel überspringen oder als weiteres Exemplar übernehmen.
- Benutzerrollen: Administrator, Bearbeiter, Nur Lesen.
- Erweiterte Wunschliste mit Priorität, Wunschpreis, CIB/Loose/Sealed, Händler/Link, Notiz und „Gekauft“.
- Sammlungsziele mit Unterreihe und automatischer Zielgröße (`0 = automatisch`).
- Preisverlauf zeigt 30/90/365 Tage/Alle sowie Hoch, Tief und prozentuale Änderung.
- Dashboard mit Datenpflege-KPIs, hoher Wunschlisten-Priorität und letzter Team-Aktivität.
- Massenbearbeitung für Status, Lagerplatz, Tags, Spielstatus, Region, Plattform und Vollständigkeitsbestandteile.
- CSV-/JSON-Export und Admin-SQL-Backup über die Oberfläche.
- Scanner mit Dauer-Scanmodus und klareren Duplikat-Aktionen.
- Eigene Fotos je physischem Exemplar: Vorderseite, Rückseite, Disc/Modul.
- Lagerplatz pro Exemplar.
- Tags pro Exemplar.
- Spielstatus: unbespielt, angefangen, durchgespielt, 100 %.
- PWA-Service-Worker mit eingeschränktem Offline-Cache für bereits besuchte Sammlungs-/Spielseiten.

## Persistente Uploads
`docker-compose.yml` bindet `./uploads` nach `/app/app/static/uploads` ein. Fotos bleiben damit Container-Neubauten erhalten.

## Datenbank
Die Migration ergänzt nur neue Spalten. Bestehende Sammlung und Preisverläufe bleiben erhalten. Kein Volume löschen.

## Backup
Vor dem Update empfohlen:

```bash
cd ~/Downloads/gamecollector-v0.2
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > gamecollector-before-v0.7.0.sql
```
