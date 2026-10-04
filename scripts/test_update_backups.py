#!/usr/bin/env python3
"""Archive byte tests and mocked Docker control flow; no live Docker required."""
import importlib.util,io,json,os,subprocess,sys,tarfile,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('backup_check',ROOT/'scripts/verify_backup_archives.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
FAKE='''#!/usr/bin/env bash
set -eu
printf '%s\\n' "$*" >> "$BACKUP_TEST_LOG"
case "$*" in
  *'psql -X -At'*) printf '2\\n3\\n4\\n5\\n6\\n';;
  *'psql -X -v'*) if [[ "${BACKUP_TEST_FAIL:-0}" == 1 ]];then exit 1;fi;cat >/dev/null;;
esac
'''
with tempfile.TemporaryDirectory(prefix='bibo-backup-tests-') as temp:
    root=Path(temp);install=root/'installation';backup=install/'backups/update-fixture';backup.mkdir(parents=True)
    (install/'.env').write_text('fixture only\n');(install/'docker-compose.yml').write_text('services: {}\n')
    (install/'uploads').mkdir();(install/'uploads/cover.png').write_bytes(b'fixture image bytes')
    (install/'feedback-uploads').mkdir();(install/'feedback-uploads/private.png').write_bytes(b'private fixture')
    (backup/'database.sql').write_text('mock dump\n')
    bins=root/'bin';bins.mkdir();docker=bins/'docker';docker.write_text(FAKE);docker.chmod(0o700)
    logfile=root/'commands.log'
    env={**os.environ,'PATH':str(bins)+os.pathsep+os.environ['PATH'],'BACKUP_TEST_LOG':str(logfile),'BIBO_BACKUP_VERIFIER':str(ROOT/'scripts/verify_backup_archives.py')}
    run=subprocess.run(['bash',str(ROOT/'scripts/verify-update-backup.sh'),str(install),str(backup)],env=env,capture_output=True,text=True)
    assert run.returncode==0,run.stderr
    manifest=json.loads((backup/'SHA256-manifest.json').read_text())
    assert 'uploads.tar.gz:uploads/cover.png' in manifest
    assert 'feedback-uploads.tar.gz:feedback-uploads/private.png' in manifest
    commands=logfile.read_text();assert 'createdb' in commands and 'dropdb' in commands and 'bibo_update_check_' in commands
    assert '--if-exists' in commands and 'dropdb --if-exists -U "$POSTGRES_USER" "$1"' in commands
    # A failed restore still drops only its disposable database and fails closed.
    logfile.write_text('')
    failed=subprocess.run(['bash',str(ROOT/'scripts/verify-update-backup.sh'),str(install),str(backup)],env={**env,'BACKUP_TEST_FAIL':'1'},capture_output=True,text=True)
    assert failed.returncode!=0 and 'dropdb' in logfile.read_text()
    bad=root/'bad';bad.mkdir()
    with tarfile.open(bad/'uploads.tar.gz','w:gz') as archive:
        entry=tarfile.TarInfo('../escape');entry.size=1;archive.addfile(entry,io.BytesIO(b'x'))
    try:module.verify(bad)
    except ValueError:pass
    else:raise AssertionError('unsafe path accepted')
    (bad/'uploads.tar.gz').write_bytes(b'not gzip')
    try:module.verify(bad)
    except (OSError,tarfile.TarError):pass
    else:raise AssertionError('broken archive accepted')
    installer=(ROOT/'install.sh').read_text()
    assert installer.index('docker compose stop web scheduler',installer.index('make_code_backup\n'))<installer.index('make_database_backup\n',installer.index('make_code_backup\n'))
    assert installer.index('verify-update-backup.sh')<installer.index('log "Release v$TARGET_VERSION als Update übernehmen"')
print('OK: upload restore bytes/checksums, corrupt/path rejection, disposable DB verification/cleanup and backup-before-update sequencing (Docker mocked)')
