#!/usr/bin/env python3
"""Launcher contract with mocked network/desktop commands, no remote writes."""
import os,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='bibo-tu-launcher-') as sandbox:
    base=Path(sandbox);log=base/'calls.log'
    for name in ('ssh','scp','curl'):
        path=base/name
        path.write_text('#!/usr/bin/env bash\nset -eu\nprintf "%s\\n" "'+name+' $*" >> "$TU_LAUNCHER_LOG"\n'+
            ('if [[ "$*" == *"mktemp -d"* ]];then echo /tmp/bibo-tu-upload-Fixture123;fi\n' if name=='ssh' else '')+
            ('printf \'{"status":"ok","test_mode":true}\\n\'\n' if name=='curl' else ''))
        path.chmod(0o700)
    env={**os.environ,'PATH':str(base)+os.pathsep+os.environ['PATH'],'TU_LAUNCHER_LOG':str(log),'SSH_CONNECTION':'','DISPLAY':':fixture'}
    def run(*args):
        log.write_text('')
        result=subprocess.run(['bash',str(ROOT/'scripts/bibo-tu.sh'),*args],env=env,input='\n',capture_output=True,text=True)
        return result,log.read_text()
    result,calls=run('--ssh','reader@testhost','--open-only','--no-open')
    assert result.returncode==0,(result.stdout,result.stderr)
    assert '127.0.0.1:18095:127.0.0.1:18095' in calls and '-O exit' in calls
    assert 'scp ' not in calls and 'sudo ' not in calls
    result,calls=run('--ssh','reader@testhost','--open-only','--no-open','--port','18096')
    assert result.returncode==0 and '127.0.0.1:18096:127.0.0.1:18095' in calls
    result,calls=run('--ssh','reader@testhost','--port','invalid','--open-only')
    assert result.returncode!=0 and not calls
    package=base/'Bibo-v5.0.4.zip';package.write_bytes(b'fixture; remote validation is mocked')
    result,calls=run('--ssh','reader@testhost','--package',str(package),'--no-open')
    assert result.returncode==0,(result.stdout,result.stderr)
    assert 'scp ' in calls and 'sudo bash /tmp/bibo-tu-upload-Fixture123/bibo-tu.sh --server' in calls
    assert '/opt/gamecollector' not in calls
    result,calls=run('--ssh','root@testhost','--package',str(package),'--no-open')
    assert result.returncode==0 and 'sudo bash' not in calls
print('OK: mocked TU launcher, preparation/open-only, custom port, validation, owned tunnel cleanup')
