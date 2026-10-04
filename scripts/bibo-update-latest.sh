#!/usr/bin/env bash
set -Eeuo pipefail
# Installiert das neueste lokale Paket oder veröffentlichte GitHub-Release.
# Optional: BIBO_DOWNLOAD_DIR=/pfad und BIBO_CHECK_ONLY=1 (nur prüfen).
[[ $EUID -eq 0 ]] || { echo 'Bitte als root starten: sudo bash bibo-update-latest.sh'; exit 1; }
INSTALL_DIR="${BIBO_INSTALL_DIR:-${GAMECOLLECTOR_INSTALL_DIR:-/opt/gamecollector}}"
START_DIR="$PWD"
for cmd in curl unzip python3; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        apt-get update
        apt-get install -y curl unzip python3
        break
    fi
done
WORK="$(mktemp -d /root/bibo-release-XXXXXX)"
trap 'rm -rf -- "$WORK"' EXIT

echo 'Suche Bibo-Pakete lokal und auf GitHub ...'
if ! curl -fsSL --retry 1 --connect-timeout 10 --max-time 25 \
    https://api.github.com/repos/iamtherealroot/GameCollector/releases/latest \
    -o "$WORK/release.json"; then
    echo 'GitHub nicht erreichbar. Verwende ein lokales Paket, falls vorhanden.'
    rm -f "$WORK/release.json"
fi

python3 - "$WORK/release.json" "$WORK/selection.json" "$START_DIR" <<'PY'
import glob, json, os, pathlib, re, sys
candidates = []
directories = [sys.argv[3], '/root', '/root/Downloads', '/root/downloads']
directories += glob.glob('/home/*/Downloads') + glob.glob('/home/*/downloads')
directories += glob.glob('/home/*/Download')
if os.environ.get('BIBO_DOWNLOAD_DIR'):
    directories.insert(0, os.environ['BIBO_DOWNLOAD_DIR'])
seen = set()
for directory in directories:
    for path in sorted(pathlib.Path(directory).glob('Bibo-v*.zip')):
        # Browserkopien wie Bibo-v4.7.1(1).zip sind ebenfalls zulässig.
        match = re.fullmatch(r'Bibo-v(\d+)\.(\d+)\.(\d+)(?:\s*\(\d+\))?\.zip', path.name)
        if not match or not path.is_file() or str(path.resolve()) in seen:
            continue
        seen.add(str(path.resolve()))
        version = tuple(map(int, match.groups()))
        tag = 'v' + '.'.join(map(str, version))
        candidates.append((version, 1, {'tag': tag, 'source': 'local', 'path': str(path.resolve())}))
try:
    release = json.loads(pathlib.Path(sys.argv[1]).read_text())
    tag = release.get('tag_name', '')
    match = re.fullmatch(r'v(\d+)\.(\d+)\.(\d+)', tag)
    assets = {a['name'] for a in release.get('assets', [])}
    if match and not release.get('draft') and not release.get('prerelease') and {f'Bibo-{tag}.zip', f'Bibo-{tag}-SHA256SUMS.txt'} <= assets:
        candidates.append((tuple(map(int, match.groups())), 0, {'tag': tag, 'source': 'github', 'path': ''}))
    else:
        print('GitHub liefert kein vollständiges stabiles Installationspaket.')
except (OSError, ValueError, KeyError, TypeError):
    pass
if not candidates:
    raise SystemExit('Kein Bibo-Paket gefunden. ZIP in Downloads ablegen oder BIBO_DOWNLOAD_DIR setzen.')
# Höchste Versionsnummer gewinnt; bei Gleichstand das lokale Paket.
chosen = max(candidates, key=lambda c: (c[0], c[1]))[2]
pathlib.Path(sys.argv[2]).write_text(json.dumps(chosen))
PY
mapfile -d '' -t CHOICE < <(python3 - "$WORK/selection.json" <<'PY'
import json, sys
selection = json.load(open(sys.argv[1]))
for key in ('tag', 'source', 'path'):
    sys.stdout.write(selection[key] + '\0')
PY
)
TAG="${CHOICE[0]}"
SOURCE_KIND="${CHOICE[1]}"
LOCAL_ZIP="${CHOICE[2]}"
CURRENT=""
if [[ -f "$INSTALL_DIR/docker-compose.yml" ]]; then
    CURRENT="$(cd "$INSTALL_DIR" && docker compose exec -T web python -c \
        'import json, urllib.request; print(json.load(urllib.request.urlopen("http://127.0.0.1:8000/health/deep", timeout=5)).get("version", ""))' 2>/dev/null)" || CURRENT=""
fi
echo "Ausgewählt: $TAG | Quelle: $SOURCE_KIND | Installiert: ${CURRENT:-unbekannt}"
if [[ -n "$CURRENT" ]] && python3 - "$CURRENT" "${TAG#v}" <<'PY'
import re, sys
def key(v):
    m = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:-rc\.(\d+))?', v)
    if not m: raise ValueError(v)
    return tuple(map(int, m.groups()[:3])) + (1 if m[4] is None else 0, int(m[4] or 0))
try:
    raise SystemExit(0 if key(sys.argv[1]) >= key(sys.argv[2]) else 1)
except ValueError:
    raise SystemExit(1)
PY
then
    echo 'Diese oder eine neuere Version ist bereits installiert.'
    exit 0
fi
ZIP="Bibo-${TAG}.zip"
if [[ "$SOURCE_KIND" == local ]]; then
    echo "Verwende: $LOCAL_ZIP"
    cp -- "$LOCAL_ZIP" "$WORK/$ZIP"
    LOCAL_SUM="$(dirname "$LOCAL_ZIP")/Bibo-${TAG}-SHA256SUMS.txt"
    if [[ -f "$LOCAL_SUM" ]]; then
        cp -- "$LOCAL_SUM" "$WORK/checksum.txt"
    else
        echo 'Keine lokale Prüfsummendatei vorhanden; prüfe ZIP-Inhalt und Paketversion.'
    fi
else
    BASE="https://github.com/iamtherealroot/GameCollector/releases/download/${TAG}"
    echo "Lade $ZIP herunter ..."
    curl -fsSL --retry 3 --connect-timeout 15 --max-time 300 "$BASE/$ZIP" -o "$WORK/$ZIP"
    curl -fsSL --retry 3 --connect-timeout 15 --max-time 60 \
        "$BASE/Bibo-${TAG}-SHA256SUMS.txt" -o "$WORK/checksum.txt"
fi
if [[ -f "$WORK/checksum.txt" ]]; then
    python3 - "$WORK/checksum.txt" "$ZIP" "${LOCAL_ZIP##*/}" > "$WORK/SHA256SUMS" <<'PY'
import pathlib, re, sys
matches = []
for line in pathlib.Path(sys.argv[1]).read_text().splitlines():
    parts = line.split(None, 1)
    if len(parts) == 2 and pathlib.PurePosixPath(parts[1].lstrip('*')).name in sys.argv[2:]:
        if re.fullmatch(r'[0-9a-fA-F]{64}', parts[0]):
            matches.append(parts[0])
if len(matches) != 1:
    raise SystemExit('Keine eindeutige passende SHA256-Prüfsumme gefunden.')
print(f'{matches[0]}  {sys.argv[2]}')
PY
    (cd "$WORK" && sha256sum -c SHA256SUMS)
fi
# Nur vollständige Pakete mit zur Dateiversion passender Anwendung ausführen.
python3 - "$WORK/$ZIP" "$TAG" <<'PY'
import pathlib, re, stat, sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
    root = f'Bibo-{sys.argv[2]}'
    for info in z.infolist():
        path = pathlib.PurePosixPath(info.filename)
        if path.is_absolute() or '..' in path.parts or stat.S_ISLNK(info.external_attr >> 16):
            raise SystemExit('Unzulässiger Pfad im ZIP-Paket.')
    if z.testzip():
        raise SystemExit('ZIP-Paket ist beschädigt.')
    if f'{root}/install.sh' not in z.namelist():
        raise SystemExit('install.sh fehlt im vollständigen Bibo-Paket.')
    app = z.read(f'{root}/app/app.py').decode('utf-8')
    version = re.search(r'^APP_VERSION = "([^"]+)"', app, re.M)
    if not version or version[1] != sys.argv[2][1:]:
        raise SystemExit('Paketname und Anwendungsversion stimmen nicht überein.')
PY
unzip -q "$WORK/$ZIP" -d "$WORK/package"
SOURCE="$WORK/package/Bibo-${TAG}"
if [[ "${BIBO_CHECK_ONLY:-0}" == 1 ]]; then
    echo "Prüfung erfolgreich: $TAG. Installer wurde nicht gestartet."
    exit 0
fi
cd "$SOURCE"
echo "Starte Installation/Update auf $TAG ..."
BIBO_INSTALL_DIR="$INSTALL_DIR" bash ./install.sh
