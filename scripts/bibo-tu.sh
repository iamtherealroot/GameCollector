#!/usr/bin/env bash
# Linux desktop launcher, or root-only preparation on the headless server.
set -Eeuo pipefail
umask 077
VERSION=5.1.1
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
usage(){
  echo 'Desktop: bash bibo-tu.sh --ssh benutzer@server [--package ZIP] [--port 18095] [--open-only] [--no-open]'
  echo "Server:  sudo bash bibo-tu.sh --server /pfad/Bibo-v$VERSION.zip"
  echo 'Login in der TU: test-admin, kein Passwort. SSH/sudo behalten ihre Anmeldung.'
}
fail(){ echo "FEHLER: $*" >&2;exit 1; }
need(){ command -v "$1" >/dev/null || fail "Benötigtes Programm fehlt: $1"; }

if [[ "${1:-}" == --server ]];then
  (( EUID == 0 )) || fail 'Die Vorbereitung braucht Root-Rechte (sudo).'
  PACKAGE="${2:-}"
  [[ -f "$PACKAGE" ]] || fail "Release-ZIP fehlt. Aufruf mit --server /pfad/Bibo-v$VERSION.zip"
  for command in docker python3 unzip;do need "$command";done
  BASE=/opt/bibo-test
  DEST="$BASE/Bibo-v$VERSION"
  [[ ! -L "$BASE" && ! -L "$DEST" ]] || fail 'Testordner darf kein symbolischer Link sein.'
  # Validate archive paths/types/version before root extraction. Reject existing
  # symlink path components as well as archive traversal and symlink entries.
  python3 - "$PACKAGE" "$BASE" "$VERSION" <<'PY'
import ast, pathlib, stat, sys, zipfile
archive, base, version=sys.argv[1:]
prefix=f'Bibo-v{version}'
with zipfile.ZipFile(archive) as z:
    assert sum(i.file_size for i in z.infolist()) < 512*1024*1024, 'Paket zu groß'
    for info in z.infolist():
        path=pathlib.PurePosixPath(info.filename)
        assert path.parts and path.parts[0]==prefix and not path.is_absolute(), 'Falscher Paketordner'
        assert '..' not in path.parts and '\\' not in info.filename, 'Unsicherer Archivpfad'
        assert not stat.S_ISLNK(info.external_attr >> 16), 'Archiv enthält Symlink'
        target=pathlib.Path(base)/path
        assert all(not p.is_symlink() for p in (target,*target.parents)), 'Symlink im Zielpfad'
    tree=ast.parse(z.read(f'{prefix}/app/app.py').decode())
    actual=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='APP_VERSION' for t in n.targets))
    assert actual==version, 'Paketversion stimmt nicht'
    assert f'{prefix}/docker-compose.test.yml' in z.namelist(), 'Test-Compose fehlt'
PY
  mkdir -p "$BASE"
  if [[ ! -f "$DEST/app/app.py" ]];then unzip -n "$PACKAGE" -d "$BASE";fi
  if [[ ! -f "$DEST/test-runtime/test.env" ]];then
    PREVIOUS="$(python3 - "$BASE" "$DEST" <<'PY'
import pathlib,re,sys
base,dest=map(pathlib.Path,sys.argv[1:]);candidates=[]
for p in base.iterdir():
    m=re.fullmatch(r'Bibo-v(\d+)\.(\d+)\.(\d+)(?:-rc\.(\d+))?',p.name)
    if m and p!=dest and not p.is_symlink() and not (p/'test-runtime').is_symlink() and not (p/'test-runtime/test.env').is_symlink() and (p/'test-runtime/test.env').is_file():
        candidates.append((tuple(map(int,m.groups()[:3]))+(1 if m[4] is None else 0, int(m[4] or 0)),p))
if candidates: print(max(candidates)[1])
PY
    )"
    if [[ -n "$PREVIOUS" ]];then
      [[ ! -e "$DEST/test-runtime" ]] || fail 'Unvollständige Test-Zugangsdaten im Ziel. Bitte prüfen, nicht überschreiben.'
      cp -a "$PREVIOUS/test-runtime" "$DEST/test-runtime"
      echo 'Vorhandene private Test-Zugangsdaten übernommen. Test-Volumes bleiben erhalten.'
    fi
  fi
  cd "$DEST"
  bash scripts/docker-test.sh up
  echo 'TU vorbereitet. Den Desktop-Starter verwenden, um Tunnel und Browser zu öffnen.'
  exit 0
fi

TARGET="${BIBO_TU_SSH:-}"
PACKAGE="${BIBO_TU_PACKAGE:-}"
PORT=18095
OPEN_ONLY=0
NO_OPEN=0
while (( $# ));do
  case "$1" in
    --ssh) TARGET="${2:?SSH-Ziel fehlt}";shift 2;;
    --package) PACKAGE="${2:?Paketpfad fehlt}";shift 2;;
    --port) PORT="${2:?Port fehlt}";shift 2;;
    --open-only) OPEN_ONLY=1;shift;;
    --no-open) NO_OPEN=1;shift;;
    --help|-h) usage;exit 0;;
    *) usage;fail "Unbekanntes Argument: $1";;
  esac
done
[[ "$PORT" =~ ^[0-9]{4,5}$ ]] && (( 10#$PORT>=1024 && 10#$PORT<=65535 )) || fail 'Lokaler Port muss zwischen 1024 und 65535 liegen.'
if [[ -n "${SSH_CONNECTION:-}" && -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]];then
  fail 'Du bist auf dem Server. Diesen Starter auf dem Desktop ausführen; für reine Vorbereitung --server ZIP verwenden.'
fi
if [[ -z "$TARGET" ]];then
  [[ -t 0 ]] || fail '--ssh benutzer@server angeben.'
  read -r -p 'SSH-Ziel (benutzer@server): ' TARGET
fi
[[ "$TARGET" =~ ^[a-zA-Z0-9_.@:-]+$ && "$TARGET" != -* ]] || fail 'Ungültiges SSH-Ziel.'
for command in ssh curl python3;do need "$command";done
if (( ! OPEN_ONLY ));then
  need scp
  if [[ -z "$PACKAGE" ]];then
    for candidate in "$SCRIPT_DIR/Bibo-v$VERSION.zip" "$SCRIPT_DIR/../Bibo-v$VERSION.zip" "$PWD/Bibo-v$VERSION.zip";do
      if [[ -f "$candidate" ]];then PACKAGE="$candidate";break;fi
    done
  fi
  [[ -f "$PACKAGE" ]] || fail "Bibo-v$VERSION.zip neben diesen Starter legen oder --package ZIP angeben. Für laufende TU: --open-only"
fi
WORK="$(mktemp -d /tmp/bibo-tu-desktop-XXXXXXXX)"
SOCKET="$WORK/ssh"
cleanup(){
  ssh -S "$SOCKET" -O exit "$TARGET" >/dev/null 2>&1 || true
  rm -rf -- "$WORK"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
echo "Verbinde mit $TARGET (SSH-Anmeldung; kein Bibo-Testpasswort nötig) …"
ssh -M -S "$SOCKET" -o ControlPersist=no -o ConnectTimeout=15 -f -N "$TARGET"
if (( ! OPEN_ONLY ));then
  REMOTE_WORK="$(ssh -S "$SOCKET" "$TARGET" 'mktemp -d /tmp/bibo-tu-upload-XXXXXXXX')"
  [[ "$REMOTE_WORK" =~ ^/tmp/bibo-tu-upload-[a-zA-Z0-9]+$ ]] || fail 'Unerwarteter Uploadpfad.'
  scp -o "ControlPath=$SOCKET" "$PACKAGE" "$TARGET:$REMOTE_WORK/Bibo-v$VERSION.zip"
  scp -o "ControlPath=$SOCKET" "$SCRIPT_DIR/bibo-tu.sh" "$TARGET:$REMOTE_WORK/bibo-tu.sh"
  echo 'Bereite ausschließlich /opt/bibo-test vor (sudo kann dein Serverpasswort abfragen) …'
  if [[ "$TARGET" == root@* ]];then
    ssh -t -S "$SOCKET" "$TARGET" "bash $REMOTE_WORK/bibo-tu.sh --server $REMOTE_WORK/Bibo-v$VERSION.zip"
  else
    ssh -t -S "$SOCKET" "$TARGET" "sudo bash $REMOTE_WORK/bibo-tu.sh --server $REMOTE_WORK/Bibo-v$VERSION.zip"
  fi
  # Remove only the two upload copies from our validated temporary directory.
  ssh -S "$SOCKET" "$TARGET" "rm -f -- $REMOTE_WORK/bibo-tu.sh $REMOTE_WORK/Bibo-v$VERSION.zip && rmdir -- $REMOTE_WORK" || true
fi
ssh -S "$SOCKET" -O forward -o ExitOnForwardFailure=yes -L "127.0.0.1:$PORT:127.0.0.1:18095" "$TARGET" || fail 'Tunnel konnte nicht geöffnet werden. Bei belegtem Port --port 18096 verwenden.'
URL="http://127.0.0.1:$PORT"
curl -fsS --max-time 15 "$URL/health/deep" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("status")=="ok" and d.get("test_mode") is True, "Keine gesunde, gekennzeichnete TU am Tunnel"' || fail 'TU-Healthcheck fehlgeschlagen. --open-only benötigt den neuen Prüfentwurf mit Testbanner.'
echo "TU bereit: $URL — Login: test-admin, Passwort leer lassen."
if (( ! NO_OPEN ));then
  if [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]] && command -v xdg-open >/dev/null;then
    (xdg-open "$URL" >/dev/null 2>&1 || echo "Browser bitte manuell öffnen: $URL") &
  else
    echo "Kein Desktop-Browser erkannt. Bitte manuell öffnen: $URL"
  fi
fi
echo 'Terminal offen lassen. Enter oder Strg+C beendet nur den Tunnel; die Testcontainer bleiben bestehen.'
read -r || true
