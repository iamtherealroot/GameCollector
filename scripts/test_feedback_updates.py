#!/usr/bin/env python3
"""Feedback triage, attention, notifications and test-only approval contracts."""
import importlib
import os
import re
import sys
import tempfile
from pathlib import Path
from flask import g
from flask.testing import FlaskClient
from werkzeug.security import generate_password_hash

sandbox = tempfile.TemporaryDirectory(prefix='bibo-feedback-updates-')
os.environ.update(DATABASE_URL='sqlite:///'+str(Path(sandbox.name)/'test.db'),
    ADMIN_USERNAME='updates-admin', ADMIN_PASSWORD='updates-password', BIBO_TEST_MODE='0')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
m = importlib.import_module('app.app')
from app.feedback import classify_feedback
from app.test_release import code_fingerprint, production_command, CHECKS
m.app.testing = True
class Client(FlaskClient):
    def open(self, *args, **kwargs):
        g.pop('_login_user', None)
        return super().open(*args, **kwargs)
m.app.test_client_class = Client

def field(html, name):
    return re.search(r'name="'+name+r'" value="([^"]*)"', html).group(1)
def ticket_form(client, url, **values):
    html = client.get(url).get_data(as_text=True)
    return dict(feedback_token=field(html,'feedback_token'), revision=field(html,'revision'), **values)

assert classify_feedback('Datenverlust!', 'Alle Daten sind nach dem Speichern verloren.', 'bug')[:2] == ('bug', 'urgent')
assert classify_feedback('Kein Datenverlust', 'Es handelt sich nur um ein kleines Layoutproblem.', 'bug')[1] == 'normal'
assert classify_feedback('Neues Menü', 'Das Menü soll verständlicher werden.', 'improvement')[0] == 'quality'
assert classify_feedback('Neue Funktion', 'Bitte eine neue Funktion hinzufügen.', 'improvement')[0] == 'feature'
with m.app.app_context():
    admin = m.User.query.filter_by(username='updates-admin').one()
    owner = m.User(username='updates-owner', role='viewer', password_hash=generate_password_hash('pass'))
    other = m.User(username='updates-other', role='viewer', password_hash=generate_password_hash('pass'))
    m.db.session.add_all([owner,other]); m.db.session.commit()
    def login(name, password='pass'):
        client=m.app.test_client()
        assert client.post('/login',data=dict(username=name,password=password)).status_code==302
        return client
    a=login(admin.username,'updates-password'); u=login(owner.username); o=login(other.username)
    html=u.get('/feedback/new').get_data(as_text=True)
    assert u.post('/feedback/new',data=dict(feedback_token=field(html,'feedback_token'),title='Datenverlust beim Speichern',
        description='Meine Daten sind nach dem Speichern verloren.',kind='bug',area='Allgemein')).status_code==302
    ticket=m.FeedbackTicket.query.one(); url=f'/feedback/{ticket.id}'
    assert ticket.priority=='urgent' and ticket.triage.category=='bug'
    Notification=m.app.config['FEEDBACK_NOTIFICATION_MODEL']
    assert 'Admin-Aufgaben · 1 offen' in a.get('/').get_data(as_text=True)
    assert '1 eigene offene Meldung' in u.get('/').get_data(as_text=True)
    assert 'Admin-Aufgaben' not in u.get('/').get_data(as_text=True)
    personal=ticket_form(u,url,action='personal_complete')
    revision=ticket.revision
    assert u.post(url,data=personal).status_code==302
    assert u.post(url,data=personal).status_code==302
    assert ticket.status=='submitted' and ticket.revision==revision
    assert 'eigene offene Meldung' not in u.get('/').get_data(as_text=True)
    assert 'Admin-Aufgaben · 1 offen' in a.get('/').get_data(as_text=True)
    assert 'Datenverlust beim Speichern' in a.get('/admin/feedback?open=1').get_data(as_text=True)
    assert 'Datenverlust beim Speichern' not in u.get('/feedback?open=1').get_data(as_text=True)
    assert 'Für mich abgeschlossen' in u.get('/feedback').get_data(as_text=True)
    assert a.post(url,data=ticket_form(a,url,action='personal_complete')).status_code==403
    assert u.post(url,data=ticket_form(u,url,action='personal_reopen')).status_code==302
    assert '1 eigene offene Meldung' in u.get('/').get_data(as_text=True)
    assert a.post(url,data=ticket_form(a,url,action='reply',body='INTERN GEHEIM',internal='1')).status_code==302
    assert Notification.query.count()==0
    assert a.post(url,data=ticket_form(a,url,action='reply',body='Wir prüfen deinen Fehler.',internal='0')).status_code==302
    notice=Notification.query.one()
    assert notice.user_id==owner.id and notice.read_at is None
    assert '1 ungelesene Nachricht' in u.get('/').get_data(as_text=True)
    assert 'INTERN GEHEIM' not in u.get('/feedback/messages').get_data(as_text=True)
    assert 'Wir prüfen deinen Fehler.' not in o.get('/feedback/messages').get_data(as_text=True)
    assert notice.read_at is None, 'GET must not mark notifications read'
    other_token=field(o.get('/feedback/messages').get_data(as_text=True),'feedback_token') if Notification.query.filter_by(user_id=other.id).count() else None
    # Fetch signed-in inbox CSRF even if it has no notifications.
    with o.session_transaction() as s: other_token=s[f'feedback-token-{other.id}-inbox']
    assert o.post('/feedback/messages',data=dict(feedback_token=other_token,notification_id=notice.id)).status_code==404
    assert u.post('/feedback/messages',data=dict(notification_id=notice.id)).status_code==400
    own_token=field(u.get('/feedback/messages').get_data(as_text=True),'feedback_token')
    assert u.post('/feedback/messages',data=dict(feedback_token=own_token,notification_id=notice.id)).status_code==302
    assert notice.read_at is not None
    assert u.post(url,data=ticket_form(u,url,action='reply',body='Vielen Dank')).status_code==302
    assert Notification.query.count()==1, 'No notification for own replies'
    values=ticket_form(a,url,action='manage',status='done',priority='low',category='quality',target_version='5.1.0-rc.2')
    assert a.post(url,data=values).status_code==302
    assert a.post(url,data=values).status_code==409
    assert Notification.query.count()==2 and ticket.triage.overridden
    assert ticket.triage.category=='quality' and ticket.priority=='low'
    assert 'Datenverlust beim Speichern' in a.get('/admin/feedback?category=quality&priority=low&status=done&kind=bug').get_data(as_text=True)
    assert 'Admin-Aufgaben · 0 offen' in a.get('/').get_data(as_text=True)
    assert 'Datenverlust beim Speichern' not in a.get('/admin/feedback?open=1').get_data(as_text=True)
    # Persistent personal tutorial setting does not affect another user or news.
    data=u.get('/api/tutorial').get_json()
    assert u.post('/api/tutorial/ack',json={'token':data['token'],'disabled':True,'user_id':other.id}).status_code==200
    assert u.get('/api/tutorial').get_json()['disabled'] is True
    assert u.get('/api/tutorial').get_json()['show'] is False
    assert o.get('/api/tutorial').get_json()['disabled'] is False
    settings=u.get('/help/tutorial-settings').get_data(as_text=True)
    settings_token=field(settings,'token')
    assert o.post('/help/tutorial-settings',data={'token':settings_token,'enabled':'1'}).status_code==400
    assert u.post('/help/tutorial-settings',data={'token':settings_token,'enabled':'1'}).status_code==302
    assert u.get('/api/tutorial').get_json()['show'] is True
    assert u.post('/help/tutorial-settings',data={'token':settings_token}).status_code==302
    second_device=login(owner.username)
    assert second_device.get('/api/tutorial').get_json()['disabled'] is True
    assert second_device.get('/api/release-news').get_json()['show'] is True
    assert u.post('/api/tutorial/ack',json={'token':data['token'],'disabled':'yes'}).status_code==400
    assert 'Datenverlust beim Speichern' in a.get('/admin/feedback?category=quality&priority=low').get_data(as_text=True)
    old=m.FeedbackTicket(user_id=owner.id,title='Alte Meldung',description='Ein altes Problem',kind='bug',area='Allgemein',app_version='5.0.4',priority='high')
    m.db.session.add(old);m.db.session.commit();m.app.config['FEEDBACK_BACKFILL']()
    assert old.priority=='high' and old.triage and Notification.query.count()==2
    # Production exposes no test approval route or menu, even for system admins.
    assert a.get('/admin/test-release').status_code==404
    assert o.get('/admin/test-release').status_code==403
    m.app.config['BIBO_TEST_MODE']=True
    assert a.get('/admin/test-release').status_code==200
    page=a.get('/admin/test-release').get_data(as_text=True)
    approval=dict(token=field(page,'token'), version=m.APP_VERSION, action='approve')
    Model=m.app.config['TU_APPROVAL_MODEL']
    assert a.post('/admin/test-release',data=approval).status_code==302 and Model.query.count()==0
    assert a.post('/admin/test-release',data={**approval,'token':'bad'}).status_code==400
    assert a.post('/admin/test-release',data={**approval,'version':'5.0.4'}).status_code==400
    assert a.post('/admin/test-release',data={**approval,**{k:'1' for k in CHECKS}}).status_code==302
    page=a.get('/admin/test-release').get_data(as_text=True)
    assert 'Produktiv-Update vorbereiten' in page and 'BIBO_ALLOW_PRERELEASE=1' in page
    assert Model.query.one().action=='approve'
    module=importlib.import_module('app.test_release')
    original=module.code_fingerprint
    module.code_fingerprint=lambda root: '0'*64
    assert '<pre class="release-command">' not in a.get('/admin/test-release').get_data(as_text=True)
    assert a.post('/admin/test-release',data={**approval,**{k:'1' for k in CHECKS}}).status_code==400
    module.code_fingerprint=original
    assert a.post('/admin/test-release',data=dict(token=field(page,'token'),version=m.APP_VERSION,action='revoke')).status_code==302
    assert '<pre class="release-command">' not in a.get('/admin/test-release').get_data(as_text=True)
    m.app.testing=False
    assert a.get('/admin/test-release').status_code==404, 'Test flag alone cannot enable non-test SQLite'
    m.app.testing=True
    # Fingerprint changes on installer changes, not only application changes.
    base=Path(sandbox.name)/'fingerprint'; (base/'app').mkdir(parents=True);(base/'scripts').mkdir()
    (base/'app/test.py').write_text('test');(base/'install.sh').write_text('first')
    before=code_fingerprint(base/'app');(base/'install.sh').write_text('second')
    assert before!=code_fingerprint(base/'app')
    command=production_command(m.APP_VERSION, before)
    assert 'docker compose' not in command and 'test.env' not in command
    snippet=command.split("<<'PY'\n",1)[1].split('\nPY',1)[0]
    compile(snippet,'generated-production-validator','exec')
print('OK: triage, manual override, persistent attention, private notifications, backfill and isolated approval')
