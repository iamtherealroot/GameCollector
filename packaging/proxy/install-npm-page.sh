#!/usr/bin/env bash
set -Eeuo pipefail
container="${1:?Name des Nginx-Proxy-Manager-Containers als Argument angeben}"
directory="$(cd "$(dirname "$0")" && pwd)"
image="$(docker inspect --format '{{.Config.Image}}' "$container")"
[[ "$image" == *nginx-proxy-manager* ]] || { echo 'Der angegebene Container ist kein Nginx Proxy Manager.' >&2;exit 1; }
docker exec "$container" mkdir -p /data/bibo-errors
docker cp "$directory/bibo-unavailable.html" "$container:/data/bibo-errors/bibo-unavailable.html"
docker exec "$container" chmod 755 /data/bibo-errors
docker exec "$container" chmod 644 /data/bibo-errors/bibo-unavailable.html
printf '\nSeite gespeichert. Jetzt beim Bibo-Proxy-Host unter Advanced eintragen:\n\n'
cat "$directory/npm-advanced.conf"
