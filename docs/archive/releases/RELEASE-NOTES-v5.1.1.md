# Bibo 5.1.1

Freigegebener Stand auf Basis von 5.1.1-rc.6. Ein gemeinsames ZIP für Neuinstallation und Update bestehender Installationen.

## Einfachere Bedienung

- Schlankeres Dashboard mit Sammlung, Suche und Scanner; weitere Werkzeuge sind aufklappbar.
- Hauptnavigation und Funktionsmenü mit klar beschrifteten Kacheln und einheitlichen SVG-Icons. Die Funktionensuche steht am Desktop und auf dem Handy bereit; Nutzer sehen nur die für sie verfügbaren Aktionen.
- Suche in drei Schritten: EAN oder Titel eingeben, Medienart auswählen, Treffer übernehmen oder neu anlegen. Passende externe Kataloge werden nach der Medienauswahl automatisch durchsucht. Lokale Treffer erscheinen zuerst.
- Einfaches Anlegen mit Titel als Pflichtfeld; der ausführliche Assistent bleibt für Boxsets und weitere Angaben verfügbar. Mehr Abstand zwischen Staffelauswahl und Zustand.
- Nach dem Speichern direkt zum Eintrag. Filter und bisherige Listenposition bleiben beim Navigieren erhalten.
- Gelöschte Exemplare lassen sich zehn Minuten lang wiederherstellen, einschließlich Preisverlauf und vorhandener Medienzuordnungen. Zugriffsrechte gelten auch für die Wiederherstellung.

## Schnellere Sammlungen und Ladefeedback

- Zwischengespeicherte Dashboard-Zusammenfassungen und Registerabgleich nur nach Datenänderungen reduzieren wiederholte Arbeit.
- Gebündelte Datenbankabfragen, zusätzliche Indizes, 40 Einträge pro Seite und verzögertes Laden der Cover entlasten große Sammlungen.
- Easter-Egg-Figuren werden erst beim Auslösen geladen.
- Der eingesendete grüne Runner mit Ladehinweis erscheint mittig im Bildschirm bei längeren Seitenwechseln, Katalogsuche und Zusatzinfosuche. Reduzierte Bewegung wird berücksichtigt.

## Medien und Zusatzinfos

- „Physisch in Deutschland?“ ist beim Anlegen mit „Ja, physisch erschienen“ vorbelegt. Andere Angaben und digitale Exemplare können weiterhin gewählt werden.
- Nach dem Speichern werden fehlende Zusatzinfos automatisch gesucht: TMDB für Filme/Serien, Open Library für Bücher, MusicBrainz für Musik, passende Kartenquellen für Sammelkarten und Spiele-/Produktquellen für Games, Hardware, Zubehör und eigene Kategorien.
- Die Automatik ergänzt fehlende Angaben bei eindeutigen Treffern; persönliche Exemplarwerte und vorhandene Angaben bleiben erhalten. Anbieterfehler verhindern das Speichern nicht. Manuelle Aktionen, einschließlich „TMDB-Metadaten aktualisieren“, bleiben verfügbar.
- Externe Quellen benötigen die jeweilige Konfiguration. Die isolierte Testumgebung verwendet eigene Schlüssel; kopierte, verschlüsselte API-Zugangsdaten müssen dort separat eingerichtet werden.

## Marvel und Filmreihen

- Lokaler Katalog mit 170 Marvel-bezogenen Werken einschließlich 38 MCU-Filmen; Kurzfilme, Specials und angekündigte Titel sind gesondert filterbar.
- Ein Film kann gleichzeitig seiner eigenen Reihe, Marvel und gegebenenfalls dem MCU angehören. Ein vorhandenes Exemplar und sein Wert werden in der Sammlung einmal gezählt. Katalogeinträge erzeugen keine zusätzlichen Exemplare.
- MCU-Filme lassen sich nach Kinostart oder Handlungschronologie anzeigen. Die Auswahl bleibt für die Sitzung gespeichert. Alternative Universen und noch nicht eingeordnete Titel stehen in der Timeline separat.
- Quellen und Stand der Handlungschronologie werden in der Ansicht genannt. Der Katalog bestätigt keine deutsche physische Veröffentlichung.

## Regal und Easter Egg

- Ausschließlich Figuren aus den eingesendeten Spritebögen; ursprüngliche gezeichnete Helfer sind entfernt. Pro Szene erscheint höchstens eine Helferfigur je Thema.
- Alle belegten Standardfächer erhalten unterschiedliche Themen. Vier Sicherheitsarbeiter bauen die Leitern auf und wieder ab; der eingesendete Vogel fliegt zum Medium und zurück.
- Angekommene Figuren stehen neben der Leiter. Beim Rückweg gehen die oberen zuerst; untere Figuren warten, bis der Weg frei ist. Getrennte Warteschlangen vermeiden Überlappungen.
- Die Tür bleibt vor dem Ereignis unsichtbar und erscheint erst nach dem letzten fallenden Medium. Keine textliche Erzählung des Ablaufs.
- Eindeutige Masken-IDs und begrenzte SVG-Bereiche verhindern vollständige Spritebögen. Mobile Regalfächer und der Abstand zur unteren Navigation sind korrigiert.

## Prüfung und Update

Die Freigabe erfolgte durch den Nutzer nach den Testkandidaten; die Animationen wurden im praktischen Test bestätigt. Automatisierte Prüfungen decken Bedienung, Berechtigungen, Erfassung, Wiederherstellung, Marvel-Mehrfachzuordnung, Suchablauf und Animationsteuerung ab. Anbieter werden dabei simuliert; tatsächliche Treffer hängen von Konfiguration und Anbieter ab. Die vollständige Darstellung auf allen Geräten ist damit nicht abgedeckt.

Der Release-Workflow veröffentlicht das Paket nach erfolgreicher GitHub-CI einschließlich Produktionsstart, Healthcheck und isolierter Docker/PostgreSQL-Regressionssuite. Vor dem Update erstellt der Installer Sicherungen. Persönliche Daten, Datenbanken und API-Schlüssel sind nicht im Paket enthalten.
