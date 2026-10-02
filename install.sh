#!/usr/bin/env bash
set -Eeuo pipefail

INSTALL_DIR="${BIBO_INSTALL_DIR:-${GAMECOLLECTOR_INSTALL_DIR:-/opt/gamecollector}}"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCK_FILE="/var/lock/bibo-install.lock"
BACKUP_DIR=""
TARGET_VERSION=""
MODE=""

log(){ printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"; }
fail(){ printf 'FEHLER: %s\n' "$*" >&2; exit 1; }
need(){ command -v "$1" >/dev/null 2>&1 || fail "Benötigtes Programm fehlt: $1"; }
random_hex(){ openssl rand -hex "$1"; }

(( EUID == 0 )) || fail "Bitte mit Root-Rechten starten: sudo bash install.sh"
for cmd in docker tar flock openssl; do need "$cmd"; done
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 fehlt. Bitte Docker Engine mit Compose-Plugin installieren."
exec 9>"$LOCK_FILE"; flock -n 9 || fail "Eine andere Bibo-Installation läuft bereits."

[[ "$SOURCE_DIR" != "$INSTALL_DIR" ]] || fail "Das Releasepaket außerhalb des Installationsverzeichnisses entpacken und dort starten."
[[ -f "$SOURCE_DIR/app/app.py" ]] || fail "Release-Payload app/app.py fehlt."
[[ -f "$SOURCE_DIR/docker-compose.yml" ]] || fail "Release-Payload docker-compose.yml fehlt."
TARGET_VERSION="$(sed -n 's/^APP_VERSION = "\([^"]*\)"/\1/p' "$SOURCE_DIR/app/app.py" | head -1)"
[[ -n "$TARGET_VERSION" ]] || fail "Paketversion konnte nicht ermittelt werden."

has_env=0
has_compose=0
[[ -f "$INSTALL_DIR/.env" ]] && has_env=1
[[ -f "$INSTALL_DIR/docker-compose.yml" ]] && has_compose=1

if (( has_env == 1 && has_compose == 1 )); then
  MODE="update"
elif (( has_env == 0 && has_compose == 0 )); then
  if [[ -d "$INSTALL_DIR" ]] && find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null | grep -q .; then
    fail "$INSTALL_DIR ist nicht leer, aber keine vollständige Bibo-Installation. Bitte Verzeichnis prüfen."
  fi
  MODE="install"
else
  fail "Unvollständige Installation unter $INSTALL_DIR erkannt (.env/docker-compose.yml). Bitte zuerst den Installationsstand prüfen."
fi

log "Bibo v$TARGET_VERSION: Modus '$MODE' automatisch erkannt"

fresh_install(){
  local admin_username="${BIBO_ADMIN_USERNAME:-admin}"
  local admin_password="${BIBO_ADMIN_PASSWORD:-}"
  local app_port="${BIBO_APP_PORT:-8095}"
  local tz_value="${BIBO_TZ:-Europe/Berlin}"
  local postgres_password secret_key installed_version tries

  if [[ -t 0 ]]; then
    printf 'Admin-Benutzer [%s]: ' "$admin_username"
    read -r input_user || true
    [[ -n "${input_user:-}" ]] && admin_username="$input_user"
    if [[ -z "$admin_password" ]]; then
      while true; do
        read -r -s -p 'Admin-Passwort: ' pass1; printf '\n'
        read -r -s -p 'Admin-Passwort wiederholen: ' pass2; printf '\n'
        [[ ${#pass1} -ge 10 ]] || { printf 'Bitte mindestens 10 Zeichen verwenden.\n' >&2; continue; }
        [[ "$pass1" == "$pass2" ]] || { printf 'Passwörter stimmen nicht überein.\n' >&2; continue; }
        admin_password="$pass1"; break
      done
    fi
  fi
  [[ -n "$admin_password" ]] || fail "Kein Admin-Passwort gesetzt. Interaktiv starten oder BIBO_ADMIN_PASSWORD setzen."

  postgres_password="${BIBO_POSTGRES_PASSWORD:-$(random_hex 24)}"
  secret_key="${BIBO_SECRET_KEY:-$(random_hex 48)}"

  log "Neuinstallation nach $INSTALL_DIR"
  mkdir -p "$INSTALL_DIR"
  tar --exclude='.git' --exclude='.env' --exclude='backups' --exclude='updates' --exclude='releases' \
      --exclude='__pycache__' --exclude='*.pyc' --exclude='*.zip' \
      -cf - -C "$SOURCE_DIR" . | tar -xf - -C "$INSTALL_DIR"
  mkdir -p "$INSTALL_DIR/uploads" "$INSTALL_DIR/backups" "$INSTALL_DIR/updates"

  cat > "$INSTALL_DIR/.env" <<ENV
POSTGRES_DB=gamecollector
POSTGRES_USER=gamecollector
POSTGRES_PASSWORD=$postgres_password
SECRET_KEY=$secret_key
ADMIN_USERNAME=$admin_username
ADMIN_PASSWORD=$admin_password
APP_PORT=$app_port
BARCODE_LOOKUP_URL=
RAWG_API_KEY=
PRICECHARTING_TOKEN=
VGPREISE_AUTH_CODE=
TZ=$tz_value
AUTOMATIC_REVALUE_HOUR=3
ENV
  chmod 600 "$INSTALL_DIR/.env"

  cd "$INSTALL_DIR"
  docker compose config -q

  log "Datenbank und Bibo starten"
  docker compose up -d --build db web scheduler

  log "Healthcheck ausführen"
  tries=45
  until docker compose exec -T web python -c \
    "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8000/health/deep', timeout=5); assert r.status == 200" >/dev/null 2>&1; do
    (( tries-- > 0 )) || { docker compose logs --tail=180 web db scheduler; fail "Bibo wurde nicht rechtzeitig betriebsbereit."; }
    sleep 4
  done
  installed_version="$(docker compose exec -T web python -c 'from app.app import APP_VERSION; print(APP_VERSION)' | tail -n1 | tr -d '\r')"
  [[ "$installed_version" == "$TARGET_VERSION" ]] || fail "Container meldet v$installed_version statt v$TARGET_VERSION."

  printf '\nBibo %s wurde erfolgreich neu installiert.\n' "$installed_version"
  printf 'Pfad: %s\n' "$INSTALL_DIR"
  printf 'Port: %s\n' "$app_port"
  printf 'Admin: %s\n' "$admin_username"
  printf 'Healthcheck: OK\n'
  printf 'Hinweis: Zugangsdaten liegen geschützt in %s/.env.\n' "$INSTALL_DIR"
}

update_install(){
  need python3
  local stamp installed_version tries status
  stamp="$(date -u '+%Y%m%dT%H%M%SZ')"
  BACKUP_DIR="$INSTALL_DIR/backups/update-v${TARGET_VERSION}-$stamp"
  mkdir -p "$BACKUP_DIR"

  make_code_backup(){
    log "Programmstand sichern"
    tar --exclude='.git' --exclude='backups' --exclude='updates' --exclude='data' \
        --exclude='uploads' --exclude='app/static/uploads' --exclude='__pycache__' --exclude='*.pyc' \
        -czf "$BACKUP_DIR/code.tar.gz" -C "$INSTALL_DIR" .
    cp -a "$INSTALL_DIR/.env" "$BACKUP_DIR/env.backup"
  }

  make_database_backup(){
    log "PostgreSQL sichern"
    cd "$INSTALL_DIR"
    docker compose up -d db
    local db_tries=30
    until docker compose exec -T db sh -lc 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; do
      (( db_tries-- > 0 )) || fail "PostgreSQL wurde nicht rechtzeitig bereit."
      sleep 2
    done
    docker compose exec -T db sh -lc 'pg_dump --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$BACKUP_DIR/database.sql"
  }

  restore_code(){
    [[ -s "$BACKUP_DIR/code.tar.gz" ]] || return 0
    log "Vorherigen Programmstand wiederherstellen"
    tar -xzf "$BACKUP_DIR/code.tar.gz" -C "$INSTALL_DIR"
    cp -a "$BACKUP_DIR/env.backup" "$INSTALL_DIR/.env"
  }

  rollback(){
    status=$?
    trap - ERR
    printf '\nFEHLER: Update auf v%s fehlgeschlagen.\n' "$TARGET_VERSION" >&2
    restore_code || true
    (cd "$INSTALL_DIR" && docker compose up -d --build web scheduler) || true
    printf 'Backup: %s\n' "$BACKUP_DIR" >&2
    exit "$status"
  }
  trap rollback ERR

  make_code_backup
  make_database_backup

  log "Release v$TARGET_VERSION als Update übernehmen"
  tar --exclude='.git' --exclude='.env' --exclude='uploads' --exclude='app/static/uploads' \
      --exclude='backups' --exclude='updates' --exclude='data' --exclude='releases' \
      --exclude='__pycache__' --exclude='*.pyc' --exclude='*.before-*' --exclude='*.debug-backup' \
      -cf - -C "$SOURCE_DIR" . | tar -xf - -C "$INSTALL_DIR"

  cd "$INSTALL_DIR"
  python3 -m py_compile app/app.py app/scheduler.py
  docker compose config -q

  log "Web und Scheduler neu bauen"
  docker compose build web scheduler
  docker compose up -d --force-recreate web scheduler

  log "Healthcheck ausführen"
  tries=30
  until docker compose exec -T web python -c \
    "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8000/health/deep', timeout=5); assert r.status == 200" >/dev/null 2>&1; do
    (( tries-- > 0 )) || { docker compose logs --tail=150 web; false; }
    sleep 4
  done
  installed_version="$(docker compose exec -T web python -c 'from app.app import APP_VERSION; print(APP_VERSION)' | tail -n1 | tr -d '\r')"
  [[ "$installed_version" == "$TARGET_VERSION" ]] || fail "Healthcheck OK, aber Container meldet v$installed_version statt v$TARGET_VERSION."

  trap - ERR
  printf '\nBibo %s wurde erfolgreich aktualisiert.\n' "$installed_version"
  printf 'Backup: %s\n' "$BACKUP_DIR"
  printf 'Healthcheck: OK\n'
}

case "$MODE" in
  install) fresh_install ;;
  update)  update_install ;;
  *) fail "Interner Fehler: unbekannter Installationsmodus '$MODE'." ;;
esac
