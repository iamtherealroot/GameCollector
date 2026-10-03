#!/usr/bin/env python3
"""Startup contract: workers don't write; init is explicit and repeatable."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='bibo-bootstrap-test-') as sandbox:
    env={**os.environ,'DATABASE_URL':'sqlite:///'+str(Path(sandbox)/'startup.db'),
         'ADMIN_USERNAME':'startup-admin','ADMIN_PASSWORD':'startup-test-pass',
         'BIBO_SKIP_BOOTSTRAP':'1','PYTHONPATH':str(ROOT)}
    def run(*args):
        return subprocess.run([sys.executable,*args],cwd=ROOT,env=env,
            check=True,capture_output=True,text=True).stdout
    run('-c','from app.app import app,db; from sqlalchemy import inspect; '
        'app.app_context().push(); assert inspect(db.engine).get_table_names()==[]')
    assert 'Datenbank bereit' in run('-m','app.bootstrap')
    before=Path(sandbox,'startup.db').read_bytes()
    for _ in range(2):
        run('-c','from app.app import app,db,User; app.app_context().push(); '
            'assert User.query.filter_by(username="startup-admin").count()==1')
    assert before==Path(sandbox,'startup.db').read_bytes(), 'Worker import mutated DB'
    assert 'Datenbank bereit' in run('-m','app.bootstrap')
    run('-c','from app.app import app,User; app.app_context().push(); '
        'assert User.query.filter_by(username="startup-admin").count()==1')
print('OK: explicit bootstrap, read-only worker imports, repeatable initialization')
