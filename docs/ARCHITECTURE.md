# Architektur

Bibo besteht aus drei Docker-Compose-Diensten:

| Dienst | Aufgabe |
|---|---|
| `web` | Flask/Gunicorn-Webanwendung und Schema-Migrationen beim Start |
| `scheduler` | automatische Preisbewertung; Standardstunde 03:00, konfigurierbar |
| `db` | PostgreSQL 17 mit persistentem Docker-Volume |

Die Datenbank speichert Katalog, Sammlung, Nutzer, Einstellungen und
Bewertungsverläufe. Lokale Bilder liegen getrennt in `uploads`. Zeitstempel
werden als UTC interpretiert und für die Anzeige DST-sicher nach
`Europe/Berlin` umgerechnet.

Die Anwendung besitzt additive Bestandsmigrationen in `ensure_schema()`.
Deshalb muss jeder Release-Healthcheck sowohl HTTP als auch Datenbankzugriff
prüfen.
