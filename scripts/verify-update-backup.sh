#!/usr/bin/env bash
# Verify a paused installation's dump in a new temporary database, never in production.
set -Eeuo pipefail
umask 077
INSTALL="${1:?Installationspfad fehlt}"
BACKUP="${2:?Backuppfad fehlt}"
[[ -f "$INSTALL/docker-compose.yml" && -f "$INSTALL/.env" ]] || exit 1
[[ "$BACKUP" == "$INSTALL"/backups/update-* && -s "$BACKUP/database.sql" ]] || exit 1
cd "$INSTALL"
VERIFY_DB="bibo_update_check_$(python3 -c 'import secrets; print(secrets.token_hex(8))')"
[[ "$VERIFY_DB" =~ ^bibo_update_check_[0-9a-f]{16}$ ]] || exit 1
CREATED=0
cleanup(){
  if (( CREATED ));then docker compose exec -T db sh -c 'dropdb --if-exists -U "$POSTGRES_USER" "$1"' sh "$VERIFY_DB" >/dev/null;fi
}
trap cleanup EXIT
docker compose exec -T db sh -c 'createdb -U "$POSTGRES_USER" "$1"' sh "$VERIFY_DB"
CREATED=1
docker compose exec -T db sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1"' sh "$VERIFY_DB" < "$BACKUP/database.sql" > "$BACKUP/restore-check.log" 2>&1
docker compose exec -T db sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1" -c "SELECT count(*) FROM collection_item; SELECT count(*) FROM \"user\";"' sh "$VERIFY_DB" >> "$BACKUP/restore-check.log" 2>&1
SQL='SELECT count(*) FROM collection_item; SELECT count(*) FROM "user"; SELECT count(*) FROM hardware_item; SELECT count(*) FROM accessory_item; SELECT count(*) FROM collector_item;'
SOURCE_COUNTS="$(docker compose exec -T db sh -c 'psql -X -At -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$1"' sh "$SQL")"
RESTORED_COUNTS="$(docker compose exec -T db sh -c 'psql -X -At -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1" -c "$2"' sh "$VERIFY_DB" "$SQL")"
[[ "$SOURCE_COUNTS" == "$RESTORED_COUNTS" ]] || { echo 'Backup-Datensatzzahlen stimmen nicht überein.' >&2;exit 1; }
for path in uploads feedback-uploads app/static/uploads;do
  if [[ -d "$INSTALL/$path" ]];then tar -czf "$BACKUP/${path//\//-}.tar.gz" -C "$INSTALL" "$path";fi
done
python3 "${BIBO_BACKUP_VERIFIER:?}" "$BACKUP"
cleanup
CREATED=0
printf 'Backup-Wiederherstellungsprobe erfolgreich.\n'
