#!/usr/bin/env bash
# Run on the Linux Mint publishing computer, not on the production server.
set -Eeuo pipefail
umask 077
repo=iamtherealroot/GameCollector
bundle="$(cd "$(dirname "$0")/../.." && pwd)"
for program in gh git gpg python3 curl;do command -v "$program" >/dev/null || { echo "$program fehlt." >&2;exit 1; };done
gh auth status >/dev/null
gh auth setup-git
work="$(mktemp -d "$HOME/bibo-apt-setup-XXXXXX")"
git clone --branch main "https://github.com/$repo.git" "$work/repo"
cd "$work/repo"
# Do not replace a pre-existing unrelated Pages website.
pages_exists=false
if gh api "repos/$repo/pages" > "$work/pages.json" 2>/dev/null;then
  pages_exists=true
  [[ -f .github/workflows/apt.yml ]] || { echo 'GitHub Pages wird bereits anderweitig verwendet. Einrichtung abgebrochen.' >&2;exit 1; }
  [[ "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("build_type",""))' "$work/pages.json")" == workflow ]] || {
    echo 'Vorhandene GitHub-Pages-Konfiguration prüfen; sie wird nicht überschrieben.' >&2;exit 1;
  }
fi
key_home="$HOME/.local/share/bibo-apt-signing"
mkdir -p "$key_home"
chmod 700 "$key_home"
if ! gpg --homedir "$key_home" --batch --list-secret-keys 'Bibo APT repository' >/dev/null 2>&1;then
  if [[ -f .github/workflows/apt.yml ]];then
    echo 'APT ist bereits eingerichtet. Gesicherten Signaturschlüssel übernehmen; automatischer Schlüsselwechsel wird verhindert.' >&2;exit 1
  fi
  gpg --homedir "$key_home" --batch --pinentry-mode loopback --passphrase '' \
    --quick-generate-key 'Bibo APT repository' rsa3072 sign 0
fi
fingerprint="$(gpg --homedir "$key_home" --batch --with-colons --list-secret-keys 'Bibo APT repository' | python3 -c \
 'import sys; rows=[r.split(":")[9] for r in sys.stdin if r.startswith("fpr:")];assert len(rows)==1;print(rows[0])')"
[[ "$fingerprint" =~ ^[A-F0-9]{40}$ ]]
gpg --homedir "$key_home" --batch --armor --export-secret-keys "$fingerprint" \
  | gh secret set BIBO_APT_SIGNING_KEY --repo "$repo"
printf '%s' "$fingerprint" | gh secret set BIBO_APT_SIGNING_FINGERPRINT --repo "$repo"
gpg --homedir "$key_home" --batch --armor --export "$fingerprint" > "$key_home/bibo-archive-key.asc"
for path in .github/workflows/apt.yml packaging/apt docs/APT.md;do
  mkdir -p "$(dirname "$path")"
  if [[ -d "$bundle/$path" ]];then
    mkdir -p "$path";cp -a "$bundle/$path/." "$path/"
  else
    cp "$bundle/$path" "$path"
  fi
done
git config user.name iamtherealroot
user_id="$(gh api user --jq '.id')"
git config user.email "$user_id+iamtherealroot@users.noreply.github.com"
git add .github/workflows/apt.yml packaging/apt docs/APT.md
bash scripts/check-public-tree.sh
if ! git diff --cached --quiet;then
  git commit -m 'Add signed Bibo APT packages and repository'
  git push origin main
fi
if [[ "$pages_exists" == false ]];then
  gh api --method POST "repos/$repo/pages" -f build_type=workflow > "$work/pages.json"
fi
gh workflow run apt.yml --repo "$repo" --ref main
printf '\nAPT-Einrichtung auf GitHub gestartet.\n'
printf 'Paketquelle: https://iamtherealroot.github.io/GameCollector/\n'
printf 'Öffentlicher Fingerprint: %s\n' "$fingerprint"
printf 'Privater Signaturschlüssel bleibt in %s und im GitHub-Actions-Secret.\n' "$key_home"
printf 'Diesen Ordner privat sichern; er ist für die dauerhaft gleiche Signatur erforderlich.\n'
printf 'Workflow prüfen: gh run list --repo %s --workflow apt.yml --limit 3\n' "$repo"
printf 'Nach erfolgreichem Workflow auf dem SERVER ausführen:\n'
printf 'curl -fL --retry 3 https://raw.githubusercontent.com/%s/main/packaging/apt/install-server.sh -o /tmp/bibo-apt-install.sh\n' "$repo"
printf 'sudo bash /tmp/bibo-apt-install.sh %s\n' "$fingerprint"
