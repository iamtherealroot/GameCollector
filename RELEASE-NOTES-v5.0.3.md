# Bibo 5.0.3 – Docker-Startkorrektur (Prüfentwurf)

Der PostgreSQL-Fehler `pg_type_typname_nsp_index` bei `CREATE TABLE user` entsteht durch konkurrierende Schema-Erstellung während des App-Imports in mehreren Gunicorn-Workern und möglicherweise dem Scheduler.

- Expliziter `init`-Dienst initialisiert Datenbank und Grunddaten vor Web und Scheduler. Docker-Worker importieren die App ohne Schema-/Grunddatenänderungen (`BIBO_SKIP_BOOTSTRAP=1`). Native Tests bleiben kompatibel.
- Der Initialisierer hält eine PostgreSQL-Advisory-Lock während der Initialisierung, damit auch zwei explizite Init-Aufrufe nicht konkurrieren.
- Compose wartet auf erfolgreichen Init-Abschluss. Bei Fehler starten Web/Scheduler nicht.
- Der Teststarter stoppt alte Test-Web-/Scheduler-Prozesse, baut auch den Init-Dienst, wartet auf dessen Ergebnis und startet danach Web, Healthcheck und gegebenenfalls Scheduler.
- Sichtbarer Healthcheck-Fortschritt; ein beendeter Webcontainer führt direkt zur Logausgabe und zum Abbruch.
- Importierte Testdaten werden nach dem Datenbankwechsel vor dem Webstart explizit initialisiert. Der Test-Scheduler bleibt aus.
- Healthcheck umfasst auch Release-, Tutorial-, Feedback- und Top-10-Tabellen.

Bestehende Test-Volumes werden nicht gelöscht. Beim Wechsel in einen neuen entpackten Ordner muss `test-runtime` inklusive `test.env` aus dem bisherigen Testordner übernommen werden. Ohne das bisherige Passwort lässt sich die bestehende Testdatenbank nicht benutzen.

Automatisierte lokale Regressionen prüfen Bootstrap auf SQLite (initialer Workerimport schreibt nicht, explizite Initialisierung, wiederholte Initialisierung ohne doppelten Admin). Der tatsächliche PostgreSQL-/Docker-Lauf muss auf dem Server geprüft werden; hier sind Docker und PostgreSQL nicht installiert. Keine Veröffentlichung ohne Freigabe. Alle bisherigen offenen Release-Prüfungen bestehen weiter.
