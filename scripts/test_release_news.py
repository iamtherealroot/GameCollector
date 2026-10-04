#!/usr/bin/env python3
import importlib,os,sys,tempfile
from pathlib import Path
from flask import g
from flask.testing import FlaskClient
from werkzeug.security import generate_password_hash

sandbox=tempfile.TemporaryDirectory(prefix='bibo-release-news-')
os.environ.update(DATABASE_URL='sqlite:///'+str(Path(sandbox.name)/'test.db'),ADMIN_USERNAME='news-admin',ADMIN_PASSWORD='news-pass')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
m=importlib.import_module('app.app');m.app.config['TESTING']=True
class IsolatedClient(FlaskClient):
    def open(self,*args,**kwargs):g.pop('_login_user',None);return super().open(*args,**kwargs)
m.app.test_client_class=IsolatedClient
with m.app.app_context():
    a=m.User(username='news-reader-a',password_hash=generate_password_hash('pass'),role='viewer')
    b=m.User(username='news-reader-b',password_hash=generate_password_hash('pass'),role='viewer')
    m.db.session.add_all([a,b]);m.db.session.commit()
    def client(name):
        c=m.app.test_client();assert c.post('/login',data={'username':name,'password':'pass'}).status_code==302;return c
    first=client(a.username);second=client(b.username)
    assert m.app.test_client().get('/api/release-news').status_code==302
    m.db.session.add(m.ReleaseAcknowledgement(user_id=a.id,version='4.7.1'));m.db.session.commit()
    news=first.get('/api/release-news');assert news.json['show'] and 'no-store' in news.headers['Cache-Control']
    payload={'version':m.APP_VERSION,'token':news.json['token']}
    # Simulate the original GET session-cookie update being lost to another
    # parallel request. A signed notice token must still validate.
    with first.session_transaction() as state:
        for key in list(state):
            if key.startswith('release-token-'):state.pop(key)
    assert second.post('/api/release-news/ack',json=payload).status_code==400
    assert first.post('/api/release-news/ack',json={'version':m.APP_VERSION}).status_code==400
    assert first.post('/api/release-news/ack',json={**payload,'version':'99.0.0'}).status_code==400
    assert first.post('/api/release-news/ack',json={**payload,'user_id':b.id}).status_code==200
    assert first.post('/api/release-news/ack',json=payload).status_code==200
    assert first.get('/api/release-news').json['show'] is False
    assert client(a.username).get('/api/release-news').json['show'] is False
    assert second.get('/api/release-news').json['show'] is True
    assert m.db.session.get(m.ReleaseAcknowledgement,(b.id,m.APP_VERSION)) is None
    tutorial=first.get('/api/tutorial').json
    assert tutorial['show'] and tutorial['steps']
    assert all(step.get('selector') for step in tutorial['steps'])
    assert 'Ein neues Objekt erfassen' not in [s['title'] for s in tutorial['steps']]
    assert 'data-dashboard-tour-home' in first.get('/').get_data(as_text=True)
    assert 'Administration' not in [s['title'] for s in tutorial['steps']]
    assert first.post('/api/tutorial/ack',json={'token':payload['token']}).status_code==400
    assert second.post('/api/tutorial/ack',json={'token':tutorial['token']}).status_code==400
    assert first.post('/api/tutorial/ack',json={'token':tutorial['token']}).status_code==200
    assert first.post('/api/tutorial/ack',json={'token':tutorial['token']}).status_code==200
    assert first.get('/api/tutorial').json['show'] is False
    assert client(a.username).get('/api/tutorial').json['show'] is False
    assert second.get('/api/tutorial').json['show'] is True
    c=m.User(username='news-returning',password_hash=generate_password_hash('pass'),role='viewer')
    m.db.session.add(c);m.db.session.commit()
    returning=client(c.username)
    state=m.db.session.get(m.app.config['RELEASE_LOGIN_MODEL'],c.id)
    state.last_version='4.7.1';state.pending='[]';m.db.session.commit()
    returning=client(c.username)
    missed=returning.get('/api/release-news').json
    versions=[row['version'] for row in missed['updates']]
    assert '5.0.4' in versions and '5.1.0-rc.1' in versions and m.APP_VERSION in versions
    assert missed['since_version']=='4.7.1' and missed['since_login']
    assert versions.index('5.0.4') < versions.index(m.APP_VERSION)
    # A second login before confirmation must not lose skipped-release notices.
    returning=client(c.username)
    assert [row['version'] for row in returning.get('/api/release-news').json['updates']]==versions
    payload=returning.get('/api/release-news').json
    assert returning.post('/api/release-news/ack',json={'version':m.APP_VERSION,'token':payload['token']}).status_code==200
    assert all(m.db.session.get(m.ReleaseAcknowledgement,(c.id,v)) is not None for v in versions)
    assert client(c.username).get('/api/release-news').json['show'] is False
    assert '5.0.4' in returning.get('/whats-new').get_data(as_text=True)
    print('OK: once-per-user/version release notice, devices, reader access and confirmation tokens')
