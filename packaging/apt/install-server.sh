#!/usr/bin/env bash
set -Eeuo pipefail
(( EUID == 0 )) || { echo 'Mit sudo oder als root auf dem Bibo-Server starten.' >&2;exit 1; }
fingerprint="${1:?Öffentlichen Fingerprint aus der Mint-Einrichtung angeben}"
[[ "$fingerprint" =~ ^[A-F0-9]{40}$ ]] || { echo 'Ungültiger Fingerprint.' >&2;exit 1; }
install_dir="${2:-/opt/gamecollector}"
[[ "$install_dir" == /* && "$install_dir" != / && "$install_dir" != *$'\n'* ]] || exit 1
[[ -f "$install_dir/.env" && -f "$install_dir/docker-compose.yml" ]] || {
  echo 'Bestehende Bibo-Installation fehlt. Optional den Installationspfad als zweites Argument angeben.' >&2;exit 1;
}
docker compose version >/dev/null
arch="$(dpkg --print-architecture)"
[[ "$arch" == amd64 || "$arch" == arm64 ]] || { echo 'Unterstützt werden amd64 und arm64.' >&2;exit 1; }
apt-get update
apt-get install -y ca-certificates curl gnupg
work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT
base=https://iamtherealroot.github.io/GameCollector
curl -fL --retry 3 "$base/bibo-archive-key.asc" -o "$work/key.asc"
actual="$(gpg --batch --with-colons --show-keys "$work/key.asc" | python3 -c \
 'import sys; rows=[r.split(":")[9] for r in sys.stdin if r.startswith("fpr:")];assert len(rows)==1;print(rows[0])')"
[[ "$actual" == "$fingerprint" ]] || { echo 'APT-Schlüssel stimmt nicht mit dem erwarteten Fingerprint überein.' >&2;exit 1; }
gpg --batch --yes --dearmor --output "$work/bibo.gpg" "$work/key.asc"
if [[ -f /etc/apt/keyrings/bibo.gpg ]];then
  existing_key="$(gpg --batch --with-colons --show-keys /etc/apt/keyrings/bibo.gpg | python3 -c 'import sys;print(next(r.split(":")[9] for r in sys.stdin if r.startswith("fpr:")))')"
  [[ "$existing_key" == "$fingerprint" ]] || { echo 'Vorhandener APT-Schlüssel weicht ab; kein automatischer Schlüsselwechsel.' >&2;exit 1; }
fi
install -d -m 755 /etc/apt/keyrings
install -m 644 "$work/bibo.gpg" /etc/apt/keyrings/bibo.gpg
if [[ -f /etc/bibo-apt.conf ]];then
  existing="$(bash -c 'source /etc/bibo-apt.conf;printf "%s" "$BIBO_INSTALL_DIR"')"
  [[ "$existing" == "$install_dir" ]] || { echo 'Bestehender APT-Installationspfad weicht ab; Konfiguration wird nicht überschrieben.' >&2;exit 1; }
else
  printf 'BIBO_INSTALL_DIR=%q\n' "$install_dir" > /etc/bibo-apt.conf
  chmod 644 /etc/bibo-apt.conf
fi
cat > /etc/apt/sources.list.d/bibo.sources <<EOF
Types: deb
URIs: $base/
Suites: stable
Components: main
Architectures: $arch
Signed-By: /etc/apt/keyrings/bibo.gpg
EOF
chmod 644 /etc/apt/sources.list.d/bibo.sources
apt-get update
apt-get -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold install -y bibo
printf '\nBibo ist jetzt über APT verwaltet.\nKünftige Updates: sudo apt update && sudo apt upgrade\n'
