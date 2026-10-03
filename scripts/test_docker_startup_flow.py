#!/usr/bin/env python3
"""Mock CLI test for sequencing/failure paths; does NOT execute Docker."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FAKE='''#!/usr/bin/env bash
set -eu
printf '%s\\n' "$*" >> "$STARTUP_TEST_LOG"
if [[ "$1" == wait ]];then echo "$STARTUP_TEST_RESULT";exit 0;fi
if [[ "$1" == logs ]];then exit 0;fi
if [[ "$1" == volume ]];then exit 1;fi
[[ "$1" == compose ]] || exit 1
shift
while [[ $# -gt 0 ]];do
  case "$1" in -p|--env-file|-f)shift 2;; *)break;; esac
done
if [[ "$1" == ps ]];then
  if [[ "$2" == -aq ]];then echo test-init;else printf 'web\\nscheduler\\n';fi
fi
exit 0
'''
with tempfile.TemporaryDirectory(prefix='bibo-docker-flow-') as sandbox:
    root=Path(sandbox)
    (root/'scripts').mkdir();(root/'bin').mkdir();(root/'app').mkdir();(root/'test-runtime').mkdir()
    shutil.copyfile(ROOT/'scripts/docker-test.sh',root/'scripts/docker-test.sh')
    shutil.copyfile(ROOT/'docker-compose.test.yml',root/'docker-compose.test.yml')
    (root/'app/app.py').write_text('APP_VERSION = "5.0.3"\n')
    (root/'test-runtime/test.env').write_text('BIBO_TEST_DB_PASSWORD=fixture\n')
    executable=root/'bin/docker';executable.write_text(FAKE);executable.chmod(0o700)
    logfile=root/'commands.log'
    def run(result):
        logfile.write_text('')
        env={**os.environ,'PATH':str(root/'bin')+os.pathsep+os.environ['PATH'],
             'STARTUP_TEST_LOG':str(logfile),'STARTUP_TEST_RESULT':str(result)}
        response=subprocess.run(['bash',str(root/'scripts/docker-test.sh'),'up'],env=env,capture_output=True,text=True)
        return response,logfile.read_text().splitlines()
    response,commands=run(0)
    assert response.returncode==0,response.stderr
    wait=commands.index('wait test-init')
    web=next(i for i,c in enumerate(commands) if c.endswith('up -d --no-deps web'))
    scheduler=next(i for i,c in enumerate(commands) if c.endswith('up -d --no-deps scheduler'))
    assert wait<web<scheduler
    response,commands=run(1)
    assert response.returncode!=0
    assert not any(c.endswith('up -d --no-deps web') for c in commands)
    assert not any(c.endswith('up -d --no-deps scheduler') for c in commands)
    (root/'test-runtime/imported-production').touch()
    response,commands=run(0)
    assert response.returncode==0
    assert not any(c.endswith('up -d --no-deps scheduler') for c in commands)
print('OK: mocked Docker sequencing, init failure stops startup, imported scheduler stays off')
