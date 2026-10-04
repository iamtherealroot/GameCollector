#!/usr/bin/env python3
import sys
from pathlib import Path
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.provider_cache import cached_json
with tempfile.TemporaryDirectory() as directory:
    calls=[]
    def fetch():
        calls.append(1)
        return {'parts':[{'id':1}]}
    assert cached_json(directory,'credential-A|collection/1',fetch)=={'parts':[{'id':1}]}
    assert cached_json(directory,'credential-A|collection/1',fetch)=={'parts':[{'id':1}]}
    assert len(calls)==1
    cached_json(directory,'credential-B|collection/1',fetch)
    assert len(calls)==2
    cached_json(directory,'credential-A|collection/1',fetch,ttl=0)
    assert len(calls)==3
    import hashlib
    target=Path(directory)/(hashlib.sha256(b'credential-A|collection/1').hexdigest()+'.json');target.write_text('broken')
    assert cached_json(directory,'credential-A|collection/1',fetch)=={'parts':[{'id':1}]}
    assert all('credential' not in path.name for path in Path(directory).iterdir())
    assert cached_json(directory,'missing',lambda:None) is None
print('OK: provider cache reuse, expiry, credential separation, corrupt file fallback and missing result')
