#!/usr/bin/env python3
"""Private feedback remains isolated from collection rights and other users."""
import importlib
import io
import os
import re
import sys
import tempfile
from pathlib import Path
from flask import g
from flask.testing import FlaskClient
from PIL import Image
from werkzeug.security import generate_password_hash

sandbox = tempfile.TemporaryDirectory(prefix='bibo-feedback-tests-')
root = Path(sandbox.name)
os.environ.update(DATABASE_URL='sqlite:///' + str(root/'test.db'), ADMIN_USERNAME='feedback-admin',
                  ADMIN_PASSWORD='feedback-password', FEEDBACK_UPLOAD_DIR=str(root/'private-images'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
m = importlib.import_module('app.app')
m.app.config.update(TESTING=True)
class IsolatedClient(FlaskClient):
    def open(self,*args,**kwargs):
        g.pop('_login_user',None)
        return super().open(*args,**kwargs)
m.app.test_client_class=IsolatedClient

def token(page):
    return re.search(r'name="feedback_token" value="([^"]+)"',page).group(1)

def form(client,url,**data):
    page=client.get(url).get_data(as_text=True)
    return dict(feedback_token=token(page),revision=re.search(r'name="revision" value="(\d+)"',page).group(1),**data)

def image():
    out=io.BytesIO();Image.new('RGB',(30,20),'red').save(out,format='PNG');out.seek(0)
    return out,'screenshot.png'

with m.app.app_context():
    admin=m.User.query.filter_by(username='feedback-admin').one()
    viewer=m.User(username='feedback-viewer',password_hash=generate_password_hash('pass'),role='viewer')
    other=m.User(username='feedback-other',password_hash=generate_password_hash('pass'),role='viewer')
    manager=m.User(username='feedback-manager',password_hash=generate_password_hash('pass'),role='editor')
    m.db.session.add_all([viewer,other,manager]);m.db.session.flush()
    space=m.CollectionSpace.query.first()
    m.db.session.add_all([m.CollectionPermission(user_id=viewer.id,collection_id=space.id,role='viewer'),
                          m.CollectionPermission(user_id=manager.id,collection_id=space.id,role='manager')])
    m.db.session.commit()
    def login(user,password='pass'):
        c=m.app.test_client();assert c.post('/login',data={'username':user,'password':password}).status_code==302;return c
    user=login(viewer.username); outsider=login(other.username);mgr=login(manager.username);sysadmin=login(admin.username,'feedback-password')
    anonymous=m.app.test_client()
    assert anonymous.get('/feedback').status_code==302
    assert mgr.get('/admin/feedback').status_code==403
    assert user.get('/admin/feedback').status_code==403
    assert user.get('/feedback/new').status_code==200
    initial=token(user.get('/feedback/new').get_data(as_text=True))
    data=dict(title='Besseres Dashboard',description='Das Menü soll besser erklärt werden.',kind='improvement',area='Navigation')
    assert user.post('/feedback/new',data=data).status_code==400
    assert user.post('/feedback/new',data={**data,'feedback_token':initial,'images':image()}).status_code==302
    ticket=m.FeedbackTicket.query.one();url=f'/feedback/{ticket.id}'
    assert ticket.user_id==viewer.id and ticket.app_version==m.APP_VERSION
    attachment=m.FeedbackAttachment.query.one();img_url=f'/feedback/images/{attachment.id}'
    response=user.get(img_url)
    assert response.status_code==200 and response.mimetype=='image/jpeg'
    assert 'no-store' in response.headers['Cache-Control']
    assert outsider.get(url).status_code==404 and outsider.get(img_url).status_code==404
    assert anonymous.get(img_url).status_code==302
    assert mgr.get(url).status_code==404 and mgr.get(img_url).status_code==404
    assert 'Besseres Dashboard' not in outsider.get('/feedback').get_data(as_text=True)
    assert sysadmin.get(img_url).status_code==200
    # Internal notes and their images must not appear in the user's HTML or routes.
    reply=form(sysadmin,url,action='reply',body='VERTRAULICHE ADMINNOTIZ',internal='1')
    assert sysadmin.post(url,data={**reply,'images':image()}).status_code==302
    internal=m.FeedbackAttachment.query.filter_by(internal=True).one()
    assert user.get(f'/feedback/images/{internal.id}').status_code==404
    assert 'VERTRAULICHE ADMINNOTIZ' not in user.get(url).get_data(as_text=True)
    assert 'VERTRAULICHE ADMINNOTIZ' in sysadmin.get(url).get_data(as_text=True)
    # Forged management/internal replies and missing confirmation cannot mutate.
    assert user.post(url,data=form(user,url,action='manage',status='done',priority='high')).status_code==403
    assert user.post(url,data=form(user,url,action='reply',body='Internal?',internal='1')).status_code==403
    assert user.post(url,data={'action':'reply','body':'No token'}).status_code==400
    manage=form(sysadmin,url,action='manage',status='planned',priority='high',target_version='5.0.1')
    assert sysadmin.post(url,data=manage).status_code==302
    assert sysadmin.post(url,data=manage).status_code==409
    assert '5.0.1' in user.get(url).get_data(as_text=True)
    assert user.post(url,data=form(user,url,action='reply',body='Danke für die Rückmeldung!')).status_code==302
    # Reject unsupported files atomically, including previously written images.
    before=m.FeedbackTicket.query.count();files_before=set((root/'private-images').iterdir())
    bad={**data,'feedback_token':initial,'images':[image(),(io.BytesIO(b'<svg>unsafe</svg>'),'bad.svg')]}
    assert user.post('/feedback/new',data=bad).status_code==400
    assert m.FeedbackTicket.query.count()==before and set((root/'private-images').iterdir())==files_before
    oversized={**data,'feedback_token':initial,'images':(io.BytesIO(b'x'*(5*1024*1024+1)),'large.jpg')}
    assert user.post('/feedback/new',data=oversized).status_code==400
    # Feedback works even for accounts without collection permissions.
    no_collection=token(outsider.get('/feedback/new').get_data(as_text=True))
    assert outsider.post('/feedback/new',data={**data,'feedback_token':no_collection}).status_code==302
    assert m.FeedbackTicket.query.filter_by(user_id=other.id).count()==1
    assert sysadmin.get('/admin/feedback?status=planned&q=Dashboard').status_code==200
    assert 'Besseres Dashboard' in sysadmin.get('/admin/feedback?status=planned&q=Dashboard').get_data(as_text=True)
    # Navigation is explained, all links resolve, and editing controls are hidden for viewers.
    nav=user.get('/help/navigation').get_data(as_text=True)
    assert 'Meine Sammlung' in nav and 'Hilfe &amp; Feedback' in nav and 'data-nav-search' in nav
    assert '/admin/feedback' not in nav and '/collection/bulk' not in nav
    for client in (user,sysadmin):
        page=client.get('/help/navigation').get_data(as_text=True)
        for link in set(re.findall(r'href="([^"]+)" data-nav-link',page)):
            assert client.get(link.replace('&amp;','&')).status_code not in {404,500},link
    assert 'custom-category-create' not in user.get('/').get_data(as_text=True)
    assert 'Feedback senden' in user.get('/').get_data(as_text=True)
    assert 'Feedback verwalten' in sysadmin.get('/help/navigation').get_data(as_text=True)
    # Invalid fields, too many attachments and account rate limits are rejected.
    assert user.post('/feedback/new',data={**data,'feedback_token':initial,'kind':'invented'}).status_code==400
    assert user.post('/feedback/new',data={**data,'feedback_token':initial,'images':[image() for _ in range(5)]}).status_code==400
    for i in range(9):
        m.db.session.add(m.FeedbackTicket(user_id=viewer.id,title=f'Limit fixture {i}',description='Limit test',kind='bug',area='Allgemein',app_version='5.0.0'))
    m.db.session.commit()
    assert user.post('/feedback/new',data={**data,'feedback_token':initial}).status_code==429
    assert 'no-store' in user.get(url).headers['Cache-Control']
    assert 'feedback-uploads/' not in user.get(url).get_data(as_text=True)
    print('OK: feedback privacy, images, internal notes, rights, CSRF, concurrency, rollback and navigation')
