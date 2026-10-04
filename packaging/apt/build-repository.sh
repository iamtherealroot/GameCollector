#!/usr/bin/env bash
set -Eeuo pipefail
package="$(realpath -e "${1:?DEB fehlt}")"
output="$(realpath -m "${2:?Repository-Ausgabe fehlt}")"
key_home="$(realpath -e "${3:?GPG-Ordner fehlt}")"
fingerprint="${4:?Signatur-Fingerprint fehlt}"
[[ "$fingerprint" =~ ^[A-F0-9]{40}$ ]] || exit 1
[[ "$(dpkg-deb -f "$package" Package)" == bibo && "$(dpkg-deb -f "$package" Architecture)" == all ]] || exit 1
mkdir -p "$output/pool/main/b/bibo"
cp "$package" "$output/pool/main/b/bibo/"
cd "$output"
for arch in all amd64 arm64;do
  mkdir -p "dists/stable/main/binary-$arch"
  apt-ftparchive packages pool > "dists/stable/main/binary-$arch/Packages"
  gzip -n -9 -c "dists/stable/main/binary-$arch/Packages" > "dists/stable/main/binary-$arch/Packages.gz"
done
apt-ftparchive \
  -o APT::FTPArchive::Release::Origin=Bibo \
  -o APT::FTPArchive::Release::Label=Bibo \
  -o APT::FTPArchive::Release::Suite=stable \
  -o APT::FTPArchive::Release::Codename=bibo \
  -o APT::FTPArchive::Release::Architectures="all amd64 arm64" \
  -o APT::FTPArchive::Release::Components=main \
  -o APT::FTPArchive::Release::NotAutomatic=yes \
  -o APT::FTPArchive::Release::ButAutomaticUpgrades=yes \
  release dists/stable > dists/stable/Release
gpg --homedir "$key_home" --batch --yes --local-user "$fingerprint" \
  --digest-algo SHA256 --clearsign --output dists/stable/InRelease dists/stable/Release
gpg --homedir "$key_home" --batch --yes --local-user "$fingerprint" \
  --digest-algo SHA256 --armor --detach-sign --output dists/stable/Release.gpg dists/stable/Release
gpg --homedir "$key_home" --batch --armor --export "$fingerprint" > bibo-archive-key.asc
test -s bibo-archive-key.asc
printf '<!doctype html><title>Bibo APT</title><h1>Bibo APT repository</h1><p>Stable packages for existing Docker installations.</p>\n' > index.html
