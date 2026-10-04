#!/usr/bin/env bash
set -Eeuo pipefail
source_dir="$(realpath -e "${1:?Releaseordner fehlt}")"
output_dir="$(realpath -m "${2:?Ausgabeordner fehlt}")"
script_dir="$(cd "$(dirname "$0")" && pwd)"
version="$(python3 - "$source_dir/app/app.py" <<'PY'
import ast,sys
t=ast.parse(open(sys.argv[1]).read())
print(next(ast.literal_eval(n.value) for n in t.body if isinstance(n,ast.Assign) and any(isinstance(a,ast.Name) and a.id=='APP_VERSION' for a in n.targets)))
PY
)"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'APT veröffentlicht nur stabile Versionen.' >&2;exit 1; }
for name in install.sh docker-compose.yml app/app.py;do test -f "$source_dir/$name";done
stage="$(mktemp -d)"
trap 'rm -rf -- "$stage"' EXIT
mkdir -p "$stage/DEBIAN" "$stage/usr/share/bibo/release" "$stage/etc" "$output_dir"
rsync -a --exclude='.git/' --exclude='.env' --exclude='test-runtime/' \
  --exclude='__pycache__/' --exclude='*.pyc' --exclude='*.zip' \
  --exclude='instance/' --exclude='uploads/' --exclude='feedback-uploads/' \
  --exclude='backups/' --exclude='updates/' --exclude='data/' \
  "$source_dir/" "$stage/usr/share/bibo/release/"
cat > "$stage/DEBIAN/control" <<EOF
Package: bibo
Version: $version-1
Architecture: all
Maintainer: Bibo Maintainers <223670750+iamtherealroot@users.noreply.github.com>
Section: web
Priority: optional
Depends: bash, python3, tar, gzip, openssl, util-linux, coreutils, docker-ce | docker.io
Homepage: https://github.com/iamtherealroot/GameCollector
Description: Bibo collection manager with Docker deployment
 Updates an existing Bibo installation with verified backups and health checks.
 Docker Compose v2 is required. Collection data remains in the existing volumes.
EOF
cp "$script_dir/postinst" "$stage/DEBIAN/postinst"
cp "$script_dir/prerm" "$stage/DEBIAN/prerm"
cp "$script_dir/postrm" "$stage/DEBIAN/postrm"
chmod 755 "$stage/DEBIAN/"{postinst,prerm,postrm}
printf 'BIBO_INSTALL_DIR=/opt/gamecollector\n' > "$stage/etc/bibo-apt.conf"
printf '/etc/bibo-apt.conf\n' > "$stage/DEBIAN/conffiles"
chmod 644 "$stage/etc/bibo-apt.conf" "$stage/DEBIAN/control" "$stage/DEBIAN/conffiles"
if [[ -n "${SOURCE_DATE_EPOCH:-}" ]];then
  find "$stage" -print0 | xargs -0 touch -h -d "@$SOURCE_DATE_EPOCH"
fi
dpkg-deb --root-owner-group --build "$stage" "$output_dir/bibo_$version-1_all.deb"
