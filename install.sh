#!/usr/bin/env bash
set -Eeuo pipefail

INSTALL_DIR="${GAMECOLLECTOR_INSTALL_DIR:-/opt/gamecollector}"
BRANCH="${GAMECOLLECTOR_BRANCH:-main}"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:-auto}"
LOCK_FILE="/var/lock/gamecollector-install.lock"
BACKUP_DIR=""
OLD_COMMIT=""
IS_FRESH=0
IS_ADOPTION=0
BOOTSTRAP_ADMIN_USERNAME=""
BOOTSTRAP_ADMIN_PASSWORD=""

log() { printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"; }
fail() { printf 'FEHLER: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || fail "Benötigtes Programm fehlt: $1"; }

if [[ "$MODE" != "auto" && "$MODE" != "--adopt" && "$MODE" != "--no-pull" ]]; then
  fail "Aufruf: sudo bash install.sh [--adopt|--no-pull]"
fi
if (( EUID != 0 )); then
  fail "Bitte mit Root-Rechten starten: sudo bash install.sh"
fi

need docker
need git
need openssl
need tar
need flock
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 fehlt."

exec 9>"$LOCK_FILE"
flock -n 9 || fail "Eine andere GameCollector-Installation läuft bereits."

repository_url() {
  if [[ -n "${GAMECOLLECTOR_REPOSITORY:-}" ]]; then
    printf '%s\n' "$GAMECOLLECTOR_REPOSITORY"
  elif git -C "$SOURCE_DIR" remote get-url origin >/dev/null 2>&1; then
    git -C "$SOURCE_DIR" remote get-url origin
  else
    printf '%s\n' "https://github.com/iamtherealroot/GameCollector.git"
  fi
}

secret_hex() { openssl rand -hex "$1"; }

create_env() {
  local env_file="$1"
  local db_password secret_key admin_password admin_username force_password_change
  db_password="$(secret_hex 24)"
  secret_key="$(secret_hex 48)"
  admin_username="${ADMIN_USERNAME:-admin}"
  [[ "$admin_username" =~ ^[A-Za-z0-9._-]{2,64}$ ]] || \
    fail "ADMIN_USERNAME darf nur Buchstaben, Zahlen, Punkt, Unterstrich und Bindestrich enthalten."
  if [[ -n "${ADMIN_PASSWORD:-}" ]]; then
    admin_password="$ADMIN_PASSWORD"
    [[ ${#admin_password} -ge 8 && "$admin_password" != *[$'\n\r\t ']* ]] || \
      fail "ADMIN_PASSWORD muss mindestens 8 Zeichen lang sein und darf keine Leerzeichen enthalten."
    force_password_change=0
  else
    admin_password="admin"
    force_password_change=1
  fi
  BOOTSTRAP_ADMIN_USERNAME="$admin_username"
  BOOTSTRAP_ADMIN_PASSWORD="$admin_password"
  umask 077
  {
    printf 'APP_PORT=8095\nAPP_BIND=0.0.0.0\nTZ=Europe/Berlin\n'
    printf 'COOKIE_SECURE=0\nSESSION_DAYS=30\nAUTOMATIC_REVALUE_HOUR=3\n'
    printf 'POSTGRES_DB=gamecollector\nPOSTGRES_USER=gamecollector\n'
    printf 'POSTGRES_PASSWORD=%s\n' "$db_password"
    printf 'POSTGRES_VOLUME_NAME=gamecollector_postgres_data\n'
    printf 'SECRET_KEY=%s\n' "$secret_key"
    printf 'ADMIN_USERNAME=%s\nADMIN_PASSWORD=%s\nADMIN_FORCE_PASSWORD_CHANGE=%s\n' "$admin_username" "$admin_password" "$force_password_change"
    printf 'RAWG_API_KEY=\nEBAY_CLIENT_ID=\nEBAY_CLIENT_SECRET=\nEBAY_DEV_ID=\n'
    printf 'EBAY_MARKETPLACE=EBAY_DE\nEBAY_ENVIRONMENT=production\n'
  } > "$env_file"
  chmod 600 "$env_file"
}

append_or_replace_env() {
  local key="$1" value="$2" file="$3"
  if grep -q "^${key}=" "$file"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$file"
  else
    printf '%s=%s\n' "$key" "$value" >> "$file"
  fi
}

detect_db_volume() {
  local container
  container="$(cd "$INSTALL_DIR" && docker compose ps -q db 2>/dev/null || true)"
  [[ -n "$container" ]] || return 0
  docker inspect "$container" --format '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Name}}{{end}}{{end}}' 2>/dev/null || true
}

make_code_backup() {
  [[ -d "$INSTALL_DIR" ]] || return 0
  mkdir -p "$BACKUP_DIR"
  tar --exclude='.git' --exclude='backups' --exclude='data' --exclude='updates' \
      --exclude='uploads' -czf "$BACKUP_DIR/code.tar.gz" -C "$INSTALL_DIR" .
  [[ ! -f "$INSTALL_DIR/.env" ]] || cp -a "$INSTALL_DIR/.env" "$BACKUP_DIR/env.backup"
}

make_database_backup() {
  mkdir -p "$BACKUP_DIR"
  cd "$INSTALL_DIR"
  docker compose up -d db
  local tries=30
  until docker compose exec -T db sh -lc 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; do
    (( tries-- > 0 )) || fail "PostgreSQL wurde nicht rechtzeitig bereit."
    sleep 2
  done
  docker compose exec -T db sh -lc \
    'pg_dump --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
    > "$BACKUP_DIR/database.sql"
}

restore_code() {
  [[ -n "$BACKUP_DIR" && -s "$BACKUP_DIR/code.tar.gz" ]] || return 0
  log "Vorherigen Programmstand wiederherstellen"
  tar -xzf "$BACKUP_DIR/code.tar.gz" -C "$INSTALL_DIR"
  [[ ! -f "$BACKUP_DIR/env.backup" ]] || cp -a "$BACKUP_DIR/env.backup" "$INSTALL_DIR/.env"
}

rollback() {
  local status=$?
  trap - ERR
  printf '\nFEHLER: Installation oder Update fehlgeschlagen.\n' >&2
  if [[ -n "$OLD_COMMIT" && -d "$INSTALL_DIR/.git" ]]; then
    git -C "$INSTALL_DIR" reset --hard "$OLD_COMMIT" >/dev/null 2>&1 || true
  else
    restore_code || true
  fi
  if [[ -f "$INSTALL_DIR/docker-compose.yml" && -f "$INSTALL_DIR/.env" ]]; then
    (cd "$INSTALL_DIR" && docker compose up -d --build web scheduler) || true
  fi
  [[ -z "$BACKUP_DIR" ]] || printf 'Backup: %s\n' "$BACKUP_DIR" >&2
  exit "$status"
}
trap rollback ERR

REPOSITORY="$(repository_url)"
if [[ "$MODE" == "--adopt" ]]; then
  [[ "$SOURCE_DIR" != "$INSTALL_DIR" ]] || fail "--adopt muss aus einem separaten Git-Clone gestartet werden."
  [[ -d "$INSTALL_DIR" && -f "$INSTALL_DIR/docker-compose.yml" ]] || fail "Keine bestehende Installation in $INSTALL_DIR gefunden."
  [[ -d "$SOURCE_DIR/.git" ]] || fail "Der Quellordner ist kein Git-Clone."
  [[ ! -d "$INSTALL_DIR/.git" ]] || fail "$INSTALL_DIR ist bereits mit Git verbunden; --adopt ist nicht nötig."
  IS_ADOPTION=1
  stamp="$(date -u '+%Y%m%dT%H%M%SZ')"
  BACKUP_DIR="$INSTALL_DIR/backups/adoption-$stamp"
  old_volume="$(detect_db_volume)"
  make_code_backup
  make_database_backup
  log "Bestehende Installation in das GitHub-Projekt übernehmen"
  tar --exclude='.git' --exclude='.env' --exclude='uploads' --exclude='backups' \
      -cf - -C "$SOURCE_DIR" . | tar -xf - -C "$INSTALL_DIR"
  cp -a "$SOURCE_DIR/.git" "$INSTALL_DIR/.git"
  if [[ -n "$old_volume" ]]; then
    append_or_replace_env POSTGRES_VOLUME_NAME "$old_volume" "$INSTALL_DIR/.env"
  fi
elif [[ ! -d "$INSTALL_DIR/.git" ]]; then
  if [[ -e "$INSTALL_DIR" && -n "$(find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
    fail "$INSTALL_DIR ist nicht leer. Für eine bestehende Installation --adopt verwenden."
  fi
  log "GameCollector aus GitHub klonen"
  mkdir -p "$(dirname "$INSTALL_DIR")"
  rmdir "$INSTALL_DIR" 2>/dev/null || true
  git clone --branch "$BRANCH" --single-branch "$REPOSITORY" "$INSTALL_DIR"
  IS_FRESH=1
fi

cd "$INSTALL_DIR"
if [[ ! -f .env ]]; then
  create_env .env
  IS_FRESH=1
fi
mkdir -p uploads backups
chown -R 10001:10001 uploads
chmod 750 uploads
chmod 700 backups

if [[ "$MODE" != "--no-pull" && "$IS_ADOPTION" -eq 0 ]]; then
  [[ -z "$(git status --porcelain --untracked-files=no)" ]] || fail "Lokale Änderungen an versionierten Dateien gefunden. Update abgebrochen."
  OLD_COMMIT="$(git rev-parse HEAD)"
  stamp="$(date -u '+%Y%m%dT%H%M%SZ')"
  BACKUP_DIR="$INSTALL_DIR/backups/update-$stamp-${OLD_COMMIT:0:8}"
  make_code_backup
  docker compose config -q
  make_database_backup
  log "Änderungen von GitHub abrufen"
  git fetch --prune origin "$BRANCH"
  git merge --ff-only "origin/$BRANCH"
fi

docker compose config -q
if [[ -z "$BACKUP_DIR" ]]; then
  stamp="$(date -u '+%Y%m%dT%H%M%SZ')"
  BACKUP_DIR="$INSTALL_DIR/backups/install-$stamp"
  make_database_backup
fi

log "Container bauen und starten"
docker compose up -d --build --remove-orphans

log "Healthcheck ausführen"
tries=30
until docker compose exec -T web python -c \
  "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8000/health/deep', timeout=5); assert r.status == 200" \
  >/dev/null 2>&1; do
  (( tries-- > 0 )) || { docker compose logs --tail=120 web; false; }
  sleep 4
done

VERSION="$(docker compose exec -T web python -c 'from app.app import APP_VERSION; print(APP_VERSION)' | tail -n1 | tr -d '\r')"
trap - ERR
printf '\nGameCollector %s ist betriebsbereit: http://SERVER-IP:%s\n' "$VERSION" "$(grep '^APP_PORT=' .env | cut -d= -f2)"
printf 'Backup: %s\n' "$BACKUP_DIR"
if [[ -n "$BOOTSTRAP_ADMIN_PASSWORD" ]]; then
  printf 'Erstanmeldung: %s / %s\n' "$BOOTSTRAP_ADMIN_USERNAME" "$BOOTSTRAP_ADMIN_PASSWORD"
  if [[ "$BOOTSTRAP_ADMIN_USERNAME" == "admin" && "$BOOTSTRAP_ADMIN_PASSWORD" == "admin" ]]; then
    printf 'Beim ersten Login muss zwingend ein neues Passwort vergeben werden.\n'
  fi
fi
printf '\nKünftige Updates: sudo bash %s/install.sh\n' "$INSTALL_DIR"
