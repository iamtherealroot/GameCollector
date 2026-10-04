# Bibo 5.1.2

Dieses Release übernimmt den freigegebenen Teststand 5.1.2-rc.5.

- EAN-Suche zeigt bis zu drei Vorschautreffer, bevor eine Medienart gewählt wird. Lokale Treffer erscheinen sofort; weitere Kataloghinweise werden nachgeladen.
- Film- und Serien-EANs werden über bereinigte und verkürzte Produkttitel zuverlässiger aufgelöst. Ohne TMDB-Zuordnung bleiben Produkttitel als Suchhilfe verfügbar.
- Mediensuche verwendet die Relevanz-Reihenfolge der jeweiligen Datenquelle. Film- und Serientreffer werden nicht mehr nach Erscheinungsdatum umsortiert.
- Marvel Cinematic Universe (MCU) erscheint als eigenständige Filmreihe alphabetisch unter „Reihen & Sammlungen“, auch ohne vorhandene Exemplare. Die Gesamtansicht zeigt alle MCU-Filme, deinen Besitz sowie Kinostart- und MCU-Handlungsreihenfolge. Einzelreihen wie Iron Man und Guardians of the Galaxy bleiben parallel erhalten; Besitz und Wert werden in den Gesamtzahlen nicht doppelt gezählt.
- Beim Anlegen von Filmen, Serien und Musik stehen OVP, Disc/Tonträger, Booklet/Beilagen, Schuber, Bonus-Disc und Versiegelt als vorausgewählte Checkboxen bereit. Die Auswahl wird gespeichert und bleibt bei Eingabefehlern erhalten. Für digitale Exemplare entfallen diese Angaben.
- Kaufdatum und Kaufpreis stehen im erweiterten Anlegeassistenten; das einfache Anlegen bleibt schlanker. Bei Eingabefehlern bleiben die eingegebenen Kaufdaten im Assistenten erhalten.
- Menükacheln und Icons übernehmen die Farben der Sammlungskategorien.
- Ladescreen erscheint bei Seitenwechseln und automatischer Zusatzinfos-Suche erst nach 800 Millisekunden. Nach einem Seitenwechsel bleibt „Fertig“ höchstens 650 Millisekunden sichtbar.
- Die eingesendete Moped-Animation ersetzt den Läufer; reduzierte Bewegung wird berücksichtigt.
- Meldungen zur Zusatzinfos-Suche stehen im oberen Hinweisbereich bei den übrigen Meldungen.
- Die komplette Bestätigungszeile „Angaben geprüft“ aktiviert ihre Checkbox. Mehr Abstand zwischen „Weitere Angaben“ und „Speichern und öffnen“.
- Eine eigene Ausfallseite für HTTP 502, 503 und 504 mit Installationshilfe für Nginx Proxy Manager liegt unter `packaging/proxy`. Sie wird separat am Proxy eingerichtet.

Die signierte APT-Paketquelle übernimmt stabile Releases nach erfolgreicher Veröffentlichung über den bestehenden GitHub-Workflow.
