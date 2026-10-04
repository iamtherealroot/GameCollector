# Bibo 5.1.1-rc.4

Unveröffentlichter Testkandidat. Enthält alle Änderungen aus RC.1 bis RC.3.

## Medien anlegen und Zusatzinfos

- „Physisch in Deutschland?“ ist beim einfachen und ausführlichen Anlegen mit „Ja, physisch erschienen“ vorbelegt. Explizite andere Angaben und digitale Exemplare werden weiterhin berücksichtigt.
- Nach dem Speichern startet die geöffnete Seite eine einmalige Suche nach fehlenden Zusatzinfos: TMDB für Filme/Serien, Open Library für Bücher, MusicBrainz für Musik, TCGdex/Scryfall/YGOPRODeck für Karten, RAWG/Produktquellen für Games sowie Produktquellen für Hardware, Zubehör und eigene Kategorien. Verfügbare Beschreibungen aus derselben Sammlung werden zusätzlich verwendet.
- Das Speichern und der erste Seitenaufruf warten nicht auf externe Datenquellen. Ohne eindeutigen Treffer oder verfügbare Quelle bleibt der gespeicherte Eintrag erhalten. Die manuellen Metadatenaktionen einschließlich TMDB bleiben erhalten.
- Automatik ergänzt ausschließlich fehlende Angaben. Titel, vorhandenes Cover/Jahr, eigene Beschreibungen, Kaufpreis, Zustand, Vollständigkeit und Lagerort bleiben erhalten. Karten werden bei mehreren Editionen nicht geraten.
- Der eingesendete grüne Runner begleitet die Zusatzinfosuche und längere Seitenwechsel. Vier Ausschnitte aus dem unveränderten Originalbogen laufen als CSS-Spriteanimation; reduzierte Bewegung hält die Figur an. Erfolg, kein Treffer und Quellenfehler haben eigenes Ladefeedback. Automatisches Neuladen unterbleibt, sobald Nutzer Eingaben geändert haben.

## Marvel und mehrere Filmreihen

- Lokaler Katalog mit 170 Titeln, Stand 04.10.2026. Enthält Kino-, TV- und Animationsfilme, Marvel-Imprints sowie separat gekennzeichnete Kurzfilme und Serials. Standardansicht: 133 Titel ohne Kurzfilme/Serials. Drei angekündigte Filme und der unveröffentlichte Fantastic-Four-Film von 1994 sind gesondert markiert.
- Die 38 veröffentlichten MCU-Kinofilme sind zusätzlich dem MCU zugeordnet. Iron Man, Spider-Man und Guardians of the Galaxy bleiben gleichzeitig in ihren Einzelreihen und in Marvel. Weitere Verbindungen wie Wolverine/X-Men werden berücksichtigt.
- Neue Datenbankverknüpfungen nutzen die bestehende Mehrfachzuordnung von Werk zu Filmreihen. Gespeicherte Filme werden anhand eindeutiger Titel/Originaltitel/Aliasse und Jahr demselben Katalogwerk zugeordnet. Mehrdeutige Titel wie Fantastic Four ohne Jahresangabe werden nicht geraten.
- Der Katalog erzeugt keine Exemplare, Kaufpreise oder bestätigten deutschen Disc-Veröffentlichungen. Übergreifende Marvel-Zahlen werden nicht erneut in den Gesamtwert der Reihenübersicht eingerechnet. Vorhandene Exemplare anderer Sammlungen bleiben privat.
- Der Katalog ist aus Filme und Filmreihen erreichbar, lässt sich nach Reihe, Medientyp und Titel filtern und zeigt maximal 40 Titel pro Seite. Kataloglesen benötigt keine externen Abfragen. Serien und Mitgliedschaften werden beim Registerabgleich aus vorbereiteten Zuordnungen gelesen.

Katalogquellen: https://en.wikipedia.org/wiki/List_of_films_based_on_Marvel_Comics,
https://en.wikipedia.org/wiki/List_of_Marvel_Cinematic_Universe_films,
https://www.sonypictures.com/movies/spidermanbrandnewday.
Filmtitel und Jahre dienen als bibliografische Fakten; Artikeltexte werden nicht übernommen. Weitere Entwicklungsprojekte ohne gesicherten Katalogeintrag sind nicht als veröffentlichte Filme enthalten.

## Leiterwege

- Oben angekommene Helfer treten von der Leiter und warten neben ihr. Beim Rückweg gehen die oberen zuerst; die unteren warten neben dem Einstieg, bis die oberen vorbei sind.
- Hin- und Rückwege haben getrennte Warteschlangen. Helfer derselben Leiter starten mit mindestens 6,4 Sekunden Abstand; der Szenenabbau wartet auf die gesamte Rückkehr.

## Prüfung und Grenzen

- Regressionen prüfen die Medienadapter mit simulierten Quellen, Erhalt von Nutzerwerten, Rechte/Isolation, einmalige Suche, Fehlerfälle, physische Vorgaben sowie Marvel-Mehrfachzuordnung, idempotente Katalogpflege und unveränderte Inventarwerte.
- Interaktionstests prüfen Leiterabstände, Rückkehrreihenfolge, eingesendete Figuren, Vogelflug und Szenenabbau. Die Silhouettenmasken aus RC.3 bleiben enthalten.
- Die vollständige Animation auf iPhone/Firefox und die Docker/PostgreSQL-Umgebung benötigen weiterhin den praktischen SSH-Test. Externe Quellen wurden in automatisierten Tests simuliert; tatsächliche Treffer hängen von Quelle und Konfiguration ab.

Nicht auf GitHub veröffentlicht.
