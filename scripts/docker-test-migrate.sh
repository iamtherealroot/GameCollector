#!/usr/bin/env bash
# Copies production into the isolated test project. Never restores to production.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
SOURCE="$(realpath -e "${1:-/opt/gamecollector}")"
[[ "${2:-}" == --confirm-test-overwrite ]] || {
  echo 'Kopiert Produktionsdaten in den Test. Vorhandene Testdaten werden gesichert.'
  echo 'Aufruf: bash scripts/docker-test.sh migrate /opt/gamecollector --confirm-test-overwrite'
  exit 1
}
[[ "$SOURCE" != "$ROOT" && -f "$SOURCE/docker-compose.yml" ]] || { echo 'Ungültige Produktionsquelle.';exit 1; }
[[ -f "$ROOT/test-runtime/test.env" ]] || { echo 'Zuerst: bash scripts/docker-test.sh up';exit 1; }
dc(){ docker compose -p bibo-release-test --env-file "$ROOT/test-runtime/test.env" -f "$ROOT/docker-compose.test.yml" "$@"; }
prod(){ docker compose --project-directory "$SOURCE" -f "$SOURCE/docker-compose.yml" "$@"; }
# Resolve container identity, not just directory/project labels. The production
# helper below only ever executes read-only dump/tar commands.
TEST_DB="$(dc ps -q db)"; PROD_DB="$(prod ps -q db)"; PROD_WEB="$(prod ps -q web)"
[[ -n "$TEST_DB" && -n "$PROD_DB" && -n "$PROD_WEB" && "$TEST_DB" != "$PROD_DB" ]] || { echo 'Getrennte laufende Datenbanken fehlen.';exit 1; }
[[ "$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$TEST_DB")" == bibo-release-test ]] || exit 1
[[ "$(dc exec -T db psql -U bibo_test -d bibo_test -Atc 'SELECT current_database()')" == bibo_test ]] || exit 1
BACKUP="$(mktemp -d "$ROOT/test-runtime/import-XXXXXXXX")"
echo "Private Importsicherung: $BACKUP"
echo 'Produktion wird gelesen; Test-Web und Test-Scheduler werden angehalten.'
dc stop web scheduler
failed(){ echo "Import abgebrochen. Test bleibt gestoppt. Sicherungen: $BACKUP" >&2; }
trap failed ERR
# Preserve test database and both volumes BEFORE modifying them.
dc exec -T db pg_dump -U bibo_test -d bibo_test --no-owner --no-privileges > "$BACKUP/test-before.sql"
for kind in images feedback; do
  if [[ "$kind" == images ]]; then dir=/app/app/static/uploads;else dir=/app/feedback-uploads;fi
  dc run --rm --no-deps -T --entrypoint tar web -C "$dir" -cf - . > "$BACKUP/test-$kind.tar"
done
prod exec -T db sh -c 'exec pg_dump --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$BACKUP/production.sql"
for kind in images feedback; do
  if [[ "$kind" == images ]]; then dir=/app/app/static/uploads;else dir=/app/feedback-uploads;fi
  docker exec "$PROD_WEB" sh -c 'if [ -d "$1" ]; then tar -C "$1" -cf - .; else tar -cf - --files-from /dev/null; fi' sh "$dir" > "$BACKUP/production-$kind.tar"
done
# Restore and validate a staging database before switching the test database.
SUFFIX="$(basename "$BACKUP" | tr '[:upper:]-' '[:lower:]_')"
STAGING="bibo_stage_$SUFFIX"; PREVIOUS="bibo_previous_$SUFFIX"
dc exec -T db createdb -U bibo_test "$STAGING"
dc exec -T db psql -U bibo_test -d "$STAGING" -v ON_ERROR_STOP=1 < "$BACKUP/production.sql" > "$BACKUP/restore.log" 2>&1
dc exec -T db psql -U bibo_test -d "$STAGING" -v ON_ERROR_STOP=1 -c 'SELECT count(*) FROM "user";' >/dev/null
# Safe extraction: rejects archive traversal and escaping links (Python 3.13).
# Merge into test-only volumes; stale test-only files are not deleted.
for kind in images feedback; do
  if [[ "$kind" == images ]]; then dir=/app/app/static/uploads;else dir=/app/feedback-uploads;fi
  dc run --rm --no-deps -T --entrypoint python web -c 'import sys,tarfile; tarfile.open(fileobj=sys.stdin.buffer,mode="r|*").extractall(sys.argv[1],filter="data")' "$dir" < "$BACKUP/production-$kind.tar"
done
dc exec -T db psql -U bibo_test -d postgres -v ON_ERROR_STOP=1 -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='bibo_test' AND pid <> pg_backend_pid();" >/dev/null
dc exec -T db psql -U bibo_test -d postgres -v ON_ERROR_STOP=1 -c "ALTER DATABASE bibo_test RENAME TO $PREVIOUS;" >/dev/null
if ! dc exec -T db psql -U bibo_test -d postgres -v ON_ERROR_STOP=1 -c "ALTER DATABASE $STAGING RENAME TO bibo_test;" >/dev/null; then
  dc exec -T db psql -U bibo_test -d postgres -v ON_ERROR_STOP=1 -c "ALTER DATABASE $PREVIOUS RENAME TO bibo_test;" >/dev/null
  failed;exit 1
fi
touch "$ROOT/test-runtime/imported-production"
echo 'Initialisiere das importierte Schema vor dem Webstart …'
dc run --rm --no-deps -T init
dc up -d --no-deps web
echo 'Import abgeschlossen. Test: http://127.0.0.1:18095'
echo 'Test-Scheduler bleibt aus. Produktionspasswörter der Nutzer bleiben gültig.'
echo "Alte Testdatenbank bleibt erhalten: $PREVIOUS"
echo "SQL- und Bildsicherungen: $BACKUP"
echo 'Keine Produktions-.env/API-Schlüssel kopiert. Verschlüsselte Integrationen benötigen separate Test-Zugangsdaten.'
