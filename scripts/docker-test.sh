#!/usr/bin/env bash
set -Eeuo pipefail
# Isolated test project; never uses production Compose or production volumes.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
command -v docker >/dev/null || { echo 'Docker fehlt.'; exit 1; }
docker compose version >/dev/null
WORK="$(mktemp -d)"
trap 'rm -rf -- "$WORK"' EXIT
umask 077
python3 - "$WORK/test.env" <<'PY'
import secrets, sys
with open(sys.argv[1], 'w') as f:
    for key in ('BIBO_TEST_DB_PASSWORD','BIBO_TEST_SECRET','BIBO_TEST_ADMIN_PASSWORD'):
        f.write(f'{key}={secrets.token_hex(24)}\n')
PY
dc(){ docker compose -p bibo-release-test --env-file "$WORK/test.env" -f "$ROOT/docker-compose.test.yml" "$@"; }
case "${1:-check}" in
  down)
    dc down
    echo 'Testcontainer gestoppt. Testdaten bleiben erhalten.'
    exit 0;;
  migrate)
    bash "$ROOT/scripts/docker-test-migrate.sh" "${2:-/opt/gamecollector}" "${3:-}"
    exit 0;;
  check|up) ;;
  *) echo 'Aufruf: bash scripts/docker-test.sh [check|up|down|migrate /opt/gamecollector --confirm-test-overwrite]'; exit 1;;
esac
# New random credentials require a new database, not reusing an old volume.
# Persist credentials in the test-only ignored directory for later invocations.
mkdir -p "$ROOT/test-runtime"
if [[ -f "$ROOT/test-runtime/test.env" ]]; then
    cp "$ROOT/test-runtime/test.env" "$WORK/test.env"
else
    if docker volume inspect bibo-release-test_test_db >/dev/null 2>&1;then
        echo 'Testdatenbank vorhanden, aber test-runtime/test.env fehlt.'
        echo 'Übernimm test-runtime aus dem bisherigen Testordner. Es werden keine neuen Passwörter gesetzt.'
        exit 1
    fi
    cp "$WORK/test.env" "$ROOT/test-runtime/test.env"
fi
dc config -q
echo 'Baue isolierte Testimages …'
dc build init web scheduler tests
# Stop old workers (including a failed previous draft) before any migration.
dc stop web scheduler
echo 'Starte Datenbank und einmalige Initialisierung …'
dc up -d --force-recreate init
INIT_CONTAINER="$(dc ps -aq init)"
[[ -n "$INIT_CONTAINER" ]] || { echo 'Initialisierungscontainer fehlt.';exit 1; }
echo 'Warte auf Initialisierung; Ausgabe folgt live …'
docker logs --follow "$INIT_CONTAINER" &
INIT_LOG_PID=$!
INIT_RESULT="$(docker wait "$INIT_CONTAINER")"
wait "$INIT_LOG_PID" || true
[[ "$INIT_RESULT" == 0 ]] || { echo 'Datenbankinitialisierung fehlgeschlagen. Web bleibt gestoppt.';exit 1; }
dc up -d --no-deps web
EXPECTED_VERSION="$(python3 -c 'import ast,pathlib; t=ast.parse(pathlib.Path("app/app.py").read_text()); print(next(ast.literal_eval(n.value) for n in t.body if isinstance(n,ast.Assign) and any(isinstance(k,ast.Name) and k.id=="APP_VERSION" for k in n.targets)))')"
ready=0
for attempt in $(seq 1 60); do
    if dc exec -T web python -c 'import json,sys,urllib.request; assert json.load(urllib.request.urlopen("http://127.0.0.1:8000/health/deep",timeout=3))["version"]==sys.argv[1]' "$EXPECTED_VERSION" >/dev/null 2>&1; then ready=1;break;fi
    if (( attempt == 1 || attempt % 5 == 0 ));then echo "Warte auf Web-Healthcheck ($attempt/60) …";fi
    if [[ "$(dc ps --status running --services)" != *web* ]];then
        echo 'Webcontainer ist beendet. Start wird abgebrochen.';dc logs --tail=100 web;exit 1
    fi
    sleep 3
done
if [[ "$ready" != 1 ]]; then dc logs --tail=100 web db;exit 1;fi
if [[ ! -f "$ROOT/test-runtime/imported-production" ]]; then
    dc up -d --no-deps scheduler
    [[ "$(dc ps --status running --services)" == *scheduler* ]] || { echo 'Test-Scheduler läuft nicht.'; exit 1; }
else
    dc stop scheduler
    echo 'Automatische Preisbewertung bleibt nach Datenimport deaktiviert.'
fi
echo 'Test-Bibo: http://127.0.0.1:18095 (Login: test-admin)'
echo 'Test-admin benötigt kein Passwort. Loginfenster bleibt sichtbar.'
echo 'Diese Adresse gilt auf dem SERVER, nicht direkt im Desktop-Browser.'
echo 'Auf dem DESKTOP: bash bibo-tu.sh --ssh benutzer@server --open-only'
echo 'Oder dort: ssh -N -o ExitOnForwardFailure=yes -L 18095:127.0.0.1:18095 benutzer@server'
echo 'Anschließend im Desktop-Browser: http://127.0.0.1:18095'
if [[ "${1:-check}" == up ]]; then
    echo 'Datenbank-Schlüssel stehen privat in test-runtime/test.env. Nicht veröffentlichen.'
    exit 0
fi
dc run --rm -e BIBO_SKIP_BOOTSTRAP=0 tests
# Backup and restore only to an explicitly named disposable test database.
dc exec -T db pg_dump -U bibo_test -d bibo_test --no-owner --no-privileges > "$WORK/test.sql"
dc exec -T db createdb -U bibo_test bibo_restore_test
restore_cleanup(){ dc exec -T db dropdb -U bibo_test --if-exists bibo_restore_test >/dev/null; }
trap 'restore_cleanup; rm -rf -- "$WORK"' EXIT
dc exec -T db psql -v ON_ERROR_STOP=1 -U bibo_test -d bibo_restore_test < "$WORK/test.sql" >/dev/null
dc exec -T db psql -v ON_ERROR_STOP=1 -U bibo_test -d bibo_restore_test -c 'SELECT count(*) FROM feedback_ticket; SELECT count(*) FROM top10_consent;' >/dev/null
restore_cleanup
trap 'rm -rf -- "$WORK"' EXIT
echo 'Container, Regressionstests und SQL-Wiederherstellung erfolgreich. Testcontainer laufen weiter.'
