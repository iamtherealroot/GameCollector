#!/usr/bin/env python3
"""Bibo 6 collection preferences, copy selection and ownership boundaries."""
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
from flask import g
from flask.testing import FlaskClient
from werkzeug.security import generate_password_hash

sandbox = tempfile.TemporaryDirectory(prefix='bibo-v6-')
os.environ.update(DATABASE_URL='sqlite:///' + str(Path(sandbox.name)/'test.db'), ADMIN_USERNAME='v6-admin', ADMIN_PASSWORD='test-pass')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
m = importlib.import_module('app.app')
m.app.config['TESTING'] = True
class IsolatedClient(FlaskClient):
    def open(self, *args, **kwargs):
        g.pop('_login_user', None)
        return super().open(*args, **kwargs)
m.app.test_client_class = IsolatedClient
with m.app.app_context():
    owner = m.shared_collection_user()
    admin = m.User.query.filter_by(username='v6-admin').one()
    reader = m.User(username='reader6', password_hash=generate_password_hash('reader-pass'), role='viewer', is_admin=False, is_system=False)
    other = m.User(username='other6', password_hash=generate_password_hash('other-pass'), role='editor', is_admin=False, is_system=False)
    m.db.session.add_all([reader,other]); m.db.session.flush()
    space = m.CollectionSpace.query.filter_by(owner_user_id=owner.id).one()
    m.db.session.add(m.CollectionPermission(collection_id=space.id, user_id=reader.id, role='viewer'))
    first = m.CollectorItem(user_id=owner.id,category='books',title='Alpha Buch',condition=None,barcode='9780000000002')
    second = m.CollectorItem(user_id=owner.id,category='books',title='Beta Buch',condition='Gut',storage_location='Regal 1',cover_url='/static/favicon-64-bibo.png')
    foreign = m.CollectorItem(user_id=other.id,category='books',title='Privates Buch')
    console = m.Console.query.first()
    game = m.Game(title='Fixture Spiel',console_id=console.id)
    m.db.session.add_all([first,second,foreign,game]);m.db.session.flush()
    a=m.CollectionItem(user_id=owner.id,game_id=game.id,status='owned',ownership_format='physical',media_present=True)
    b=m.CollectionItem(user_id=owner.id,game_id=game.id,status='owned',ownership_format='physical',media_present=True)
    m.db.session.add_all([a,b]);m.db.session.commit()
    m.refresh_bibo_registry()
    client=m.app.test_client();client.post('/login',data={'username':'v6-admin','password':'test-pass'})
    html=client.get('/library?kind=books').get_data(as_text=True)
    assert 'Alpha Buch' in html and 'Privates Buch' not in html
    assert 'Anwenden & merken' in html and 'library-select-copy' in html
    with client.session_transaction() as sess: token=sess['library_preferences_token']
    assert client.post('/library/preferences',data={'view':'grid','token':'bad'}).status_code==400
    saved=client.post('/library/preferences',data={'token':token,'kind':'books','view':'grid','sort':'title_desc','q':'Beta'})
    assert saved.status_code==302
    assert 'Beta Buch' in client.get(saved.location).get_data(as_text=True)
    remembered=client.get('/library',follow_redirects=True).get_data(as_text=True)
    assert 'library-view-grid' in remembered and remembered.index('Beta Buch') < remembered.index('Alpha Buch')
    # Preferences survive a new login and do not retain the search query.
    again=m.app.test_client();again.post('/login',data={'username':'v6-admin','password':'test-pass'})
    remembered=again.get('/library',follow_redirects=True).get_data(as_text=True)
    assert 'library-view-grid' in remembered and 'Alpha Buch' in remembered
    missing=client.get('/library?kind=books&quality=cover').get_data(as_text=True)
    assert 'Alpha Buch' in missing and 'Beta Buch' not in missing
    duplicate=client.get('/library?quality=duplicate').get_data(as_text=True)
    assert 'Fixture Spiel' in duplicate and 'Alpha Buch' not in duplicate
    copy=m.BiboCopy.query.filter_by(source_kind='collector',source_id=str(first.id)).one()
    foreign_copy=m.BiboCopy.query.filter_by(source_kind='collector',source_id=str(foreign.id)).one()
    assert client.get(f'/library/copy/{foreign_copy.id}/edit').status_code==404
    game_copies=m.BiboCopy.query.filter_by(source_kind='game',source_id=str(b.id)).one()
    edit=client.get(f'/library/copy/{game_copies.id}/edit')
    assert f'item_id={b.id}' in edit.location
    detail=client.get(f'/library/work/{copy.edition.work_id}').get_data(as_text=True)
    assert 'Exemplar bearbeiten' in detail and 'Weiteres Exemplar' in detail and 'Nächstes Medium scannen' in detail
    # GET only preselects; POST changes exactly the selected, filtered, owned rows.
    bulk=client.get(f'/collection/bulk?item_keys=collector:{first.id}').get_data(as_text=True)
    assert f'value="collector:{first.id}" checked' in bulk
    client.post('/collection/bulk',data={'type':'books','q':'Alpha','item_keys':[f'collector:{first.id}',f'collector:{second.id}',f'collector:{foreign.id}'],'storage_mode':'set','storage_location':'Neues Regal'})
    assert m.db.session.get(m.CollectorItem,first.id).storage_location=='Neues Regal'
    assert m.db.session.get(m.CollectorItem,second.id).storage_location=='Regal 1'
    assert m.db.session.get(m.CollectorItem,foreign.id).storage_location is None
    m.refresh_bibo_registry(only_if_changed=True)
    assert m.db.session.get(m.BiboCopy,copy.id).storage_location=='Neues Regal'
    reader_client=m.app.test_client();reader_client.post('/login',data={'username':'reader6','password':'reader-pass'})
    assert reader_client.get(f'/library/copy/{copy.id}/edit').status_code==403
    read_html=reader_client.get('/library').get_data(as_text=True)
    assert 'id="library-selection"' not in read_html
    with reader_client.session_transaction() as sess: reader_token=sess['library_preferences_token']
    assert reader_client.post('/library/preferences',data={'token':reader_token,'view':'grid'}).status_code==302
    assert reader_client.post('/collection/bulk',data={'item_keys':f'collector:{first.id}','storage_mode':'clear'}).status_code==403
    assert m.app_setting_get(f'library_preferences_{admin.id}_{owner.id}').find('title_desc')!=-1
    assert 'Was möchtest du hinzufügen?' in client.get('/add').get_data(as_text=True)
    scan=client.post('/add/media',data={'category':'books','title':'Scan Folge','save_action':'scan_next'})
    assert scan.status_code==302 and scan.location.endswith('/scanner')
    assert m.CollectorItem.query.filter_by(title='Scan Folge',user_id=owner.id).count()==1
    if os.environ.get('BIBO_UI_OUTPUT'):
        out=Path(os.environ['BIBO_UI_OUTPUT']);out.mkdir(parents=True,exist_ok=True)
        for name,url in [('library','/library?view=grid'),('list','/library?view=list'),('detail',f'/library/work/{copy.edition.work_id}'),('add','/add')]:
            (out/f'{name}.html').write_text(client.get(url).get_data(as_text=True))
print('OK: remembered per-user views, quality filters, exact-copy editing, bulk selection/isolation, reader permissions and next scan')
