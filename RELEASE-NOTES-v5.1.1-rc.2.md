# Bibo 5.1.1-rc.2

Unveröffentlichter Testkandidat. Enthält alle Dashboard-, Such-, Bedienungs- und Leistungsänderungen aus RC.1.

- Drei zusätzlich eingesendete Spritebögen unverändert als Bildquellen aufgenommen: Berufe, Klassen mit Vogel-Flugposen und besondere Berufe.
- Neue Helferalternativen: Bäckerin, Medizin, Bau, Mechanik, Büro, Imkerei, Erkundung, Tauchen, Vogelpflege, Schmiede sowie Post, Küche, Bergbau und Waldhüterin.
- Sechs belegte Standardfächer erhalten sechs unterschiedliche Themen. Die vier Regalspalten bekommen wieder ihre gemeinsamen Leitern. Ein zusätzliches Fach kann das siebte Thema verwenden.
- Die Waldhüterin wird bevorzugt bei Büchern eingesetzt. Ihr Vogel fliegt mit den eingesendeten Flugbildern zum jeweiligen Medium, wendet und fliegt zurück. Vogel und Szene werden danach vollständig entfernt.
- Nur eingesendete Figuren; kein Ablauftext, Tür vor Auslösung verborgen, Sicherheitsgruppe und vollständiger Auf-/Abbau bleiben erhalten.

Geprüft: JavaScript-Interaktionen einschließlich sechs Helfern, vier Leitern, Vogelziel, Rückflug, Szenenabbau und reduzierter Bewegung; Python-Tests für Dashboard, einfache Bedienung und Versionsregeln; Öffentlichkeitsprüfung.

Die tatsächliche Darstellung der neuen Spriteausschnitte und die Flugbewegung müssen noch im Browser der SSH-Testumgebung geprüft werden. Lokaler Browserstart und Docker/PostgreSQL-Prüfung stehen weiterhin aus. Keine Veröffentlichung auf GitHub.
