#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

failed=0
while IFS= read -r path; do
  case "$path" in
    .env|*.db|*.sqlite|*.sqlite3|*.sql|*.zip|*.tar.gz|backups/*|data/*|updates/*|feedback-uploads/*|instance/*|test-runtime/*)
      printf 'Nicht veröffentlichen: %s\n' "$path" >&2
      failed=1
      ;;
    uploads/*)
      [[ "$path" == "uploads/.gitkeep" ]] || {
        printf 'Privater Upload im Repository: %s\n' "$path" >&2
        failed=1
      }
      ;;
  esac
done < <(git ls-files)

patterns='/home/[[:alnum:]_.-]+/Downloads|192\.168\.|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|AKIA[0-9A-Z]{16}'
if git grep -nEI "$patterns" -- ':!scripts/check-public-tree.sh' ':!LICENSE'; then
  printf 'Mögliche persönliche Daten oder Geheimnisse gefunden.\n' >&2
  failed=1
fi

if (( failed )); then
  exit 1
fi
printf 'Öffentlichkeitsprüfung: OK\n'
