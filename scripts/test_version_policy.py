#!/usr/bin/env python3
"""Stable updater excludes RCs and cannot downgrade a newer RC installation."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'scripts/bibo-update-latest.sh').read_text()
comparison=source.split('"${TAG#v}" <<\'PY\'\n',1)[1].split('\nPY',1)[0]
for current, candidate, expected in [('5.1.0-rc.1','5.0.4',0),('5.1.0-rc.1','5.1.0',1),
    ('5.1.0','5.1.0',0),('5.1.1','5.1.0',0),('5.0.4','5.1.0',1),('5.1.0-rc.10','5.0.9',0)]:
    result=subprocess.run([sys.executable,'-c',comparison,current,candidate])
    assert result.returncode==expected,(current,candidate,result.returncode)
selection=source.split('"$START_DIR" <<\'PY\'\n',1)[1].split('\nPY',1)[0]
with tempfile.TemporaryDirectory(prefix='bibo-version-policy-') as folder:
    base=Path(folder);(base/'Bibo-v5.0.4.zip').write_bytes(b'fixture');(base/'Bibo-v5.1.0-rc.1.zip').write_bytes(b'fixture')
    output=base/'selection.json'
    result=subprocess.run([sys.executable,'-c',selection,str(base/'missing.json'),str(output),str(base)],
                          env={**os.environ,'BIBO_DOWNLOAD_DIR':str(base)},capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert json.loads(output.read_text())['tag']=='v5.0.4'
assert '--prerelease' in (ROOT/'.github/workflows/release.yml').read_text()
assert 'BIBO_ALLOW_PRERELEASE' in (ROOT/'install.sh').read_text()
print('OK: stable/RC ordering, stable-only selection, prerelease publication and explicit install guard')
