# Versionen und Freigabe

Verbindliches Format: `X.Y.Z` für stabile Releases und `X.Y.Z-rc.N` für Prüfstände (N ab 1).

- X: inkompatible Änderungen / neue Hauptgeneration.
- Y: neue, kompatible Funktionen.
- Z: Korrekturen ohne neue Funktionen.
- RC-Zähler vergleichen wir numerisch: rc.10 kommt nach rc.9, die stabile Version nach allen RCs derselben Basis.

5.1.0 ist nach ausdrücklicher Nutzerfreigabe zur stabilen Veröffentlichung vorbereitet. Bereits verwendete Nummern bleiben unverändert.

TU-Freigabe dokumentiert nur den Test und bereitet einen Produktionsbefehl vor. Sie erteilt keine GitHub-Veröffentlichungsfreigabe. Prüfstände bleiben lokal, bis die Veröffentlichung ausdrücklich beauftragt wird. Änderungen auf main lösen den bestehenden CI-/Release-Workflow aus: dort nur ausdrücklich freigegebene Stände übernehmen. Veröffentlichte RCs erhalten die GitHub-Prerelease-Markierung; automatische Produktionsupdates wählen ausschließlich stabile Pakete.
