#!/usr/bin/env bash
set -Eeuo pipefail
version="${1:?Version fehlt}"
[[ "$version" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-rc\.[1-9][0-9]*)?$ ]] || { echo 'Ungültige Version; erwartet X.Y.Z oder X.Y.Z-rc.N'; exit 1; }
root="$(cd "$(dirname "$0")/.." && pwd)"
outdir="${2:-$(cd "$root/.." && pwd)}"
mkdir -p "$outdir"

actual="$(sed -n 's/^APP_VERSION = "\([^"]*\)"/\1/p' "$root/app/app.py" | head -1)"
[[ "$actual" == "$version" ]] || { echo "FEHLER: app/app.py meldet v${actual:-unbekannt}, erwartet v$version" >&2; exit 1; }

stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
base="$stage/Bibo-v${version}"
mkdir -p "$base"

rsync -a \
  --exclude '.git/' --exclude 'work/' --exclude 'instance/' --exclude '__pycache__/' \
  --exclude '*.pyc' --exclude '*.zip' --exclude '.env' --exclude 'releases/' --exclude 'feedback-uploads/' --exclude 'test-runtime/' \
  --exclude 'scripts/install_fresh.sh' \
  --exclude 'app/*.before-*' --exclude 'app/*.debug-backup' --exclude 'gamecollector-before*.sql' \
  "$root/" "$base/"

archive="$outdir/Bibo-v${version}.zip"
(cd "$stage" && zip -qr "$archive" "Bibo-v${version}")
unzip -tq "$archive"
sha256sum "$archive" | tee "$outdir/Bibo-v${version}-SHA256SUMS.txt"
printf '\nRelease-Artefakt erstellt:\n%s\n' "$archive"
