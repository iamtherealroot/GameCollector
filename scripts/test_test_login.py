#!/usr/bin/env python3
import importlib,os,sys,tempfile
from pathlib import Path
from flask import g
from flask.testing import FlaskClient
from werkzeug.security import generate_password_hash

sandbox=tempfile.TemporaryDirectory(prefix='bibo-test-login-')
os.environ.update(DATABASE_URL='sqlite:///'+str(Path(sandbox.name)/'test.db'),
    ADMIN_USERNAME='test-admin',ADMIN_PASSWORD='private-bootstrap-pass',BIBO_TEST_MODE='1',BIBO_TEST_PASSWORDLESS='1')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
m=importlib.import_module('app.app');m.app.testing=True
class Client(FlaskClient):
    def open(self,*args,**kwargs):g.pop('_login_user',None);return super().open(*args,**kwargs)
m.app.test_client_class=Client
with m.app.app_context():
    other=m.User(username='normal-reader',password_hash=generate_password_hash('real-pass'),role='viewer')
    m.db.session.add(other);m.db.session.commit()
    html=m.app.test_client().get('/login').get_data(as_text=True)
    assert 'TESTUMGEBUNG' in html and 'value="test-admin"' in html
    assert 'autocomplete="current-password" required' not in html
    assert m.app.test_client().post('/login',data={'username':'test-admin','password':''}).status_code==302
    assert m.app.test_client().post('/login',data={'username':'normal-reader','password':''}).status_code==200
    assert m.app.test_client().post('/login',data={'username':'normal-reader','password':'real-pass'}).status_code==302
    m.app.config['BIBO_TEST_MODE']=False
    assert m.app.test_client().post('/login',data={'username':'test-admin','password':''}).status_code==200
    html=m.app.test_client().get('/login').get_data(as_text=True)
    assert 'TESTUMGEBUNG' not in html and 'autocomplete="current-password" required' in html
    m.app.config['BIBO_TEST_MODE']=True;m.app.config['BIBO_TEST_PASSWORDLESS']=False
    assert m.app.test_client().post('/login',data={'username':'test-admin','password':''}).status_code==200
    m.app.config['BIBO_TEST_PASSWORDLESS']=True;m.app.testing=False
    assert not m.test_passwordless_enabled(), 'Non-test SQLite must not bypass passwords'
    m.app.testing=True
    os.environ['ADMIN_USERNAME']='production-admin'
    assert not m.test_passwordless_enabled(), 'Non-test admin configuration must not bypass passwords'
print('OK: prefilling/test banner, test-only blank login, normal and production passwords remain required')
