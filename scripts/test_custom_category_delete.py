#!/usr/bin/env python3
"""Deletion must preserve copies and isolate categories between collections."""
import importlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from werkzeug.security import generate_password_hash
from flask import g
from flask.testing import FlaskClient

sandbox=tempfile.TemporaryDirectory(prefix='bibo-category-delete-')
os.environ['DATABASE_URL']='sqlite:///'+str(Path(sandbox.name)/'test.db')
os.environ['ADMIN_USERNAME']='category-admin'
os.environ['ADMIN_PASSWORD']='category-password'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
m=importlib.import_module('app.app')
m.app.config.update(TESTING=True)
class IsolatedLoginClient(FlaskClient):
    def open(self, *args, **kwargs):
        # The fixture keeps one app context for DB assertions; reset its cached
        # login user to match the separate request contexts used in production.
        g.pop("_login_user", None)
        return super().open(*args, **kwargs)
m.app.test_client_class = IsolatedLoginClient

with m.app.app_context():
    owner=m.shared_collection_user()
    space=m.CollectionSpace.query.filter_by(owner_user_id=owner.id).one()
    foreign=m.User(username='foreign-owner',password_hash=generate_password_hash('random'),is_system=True)
    viewer=m.User(username='category-viewer',password_hash=generate_password_hash('viewer-pass'),is_system=False)
    editor=m.User(username='category-editor',password_hash=generate_password_hash('editor-pass'),is_system=False)
    m.db.session.add_all([foreign,viewer,editor]);m.db.session.flush()
    other=m.CollectionSpace(name='Andere Sammlung',slug='other-fixture',owner_user_id=foreign.id)
    m.db.session.add(other);m.db.session.flush()
    m.db.session.add_all([m.CollectionPermission(collection_id=space.id,user_id=viewer.id,role='viewer'),
                          m.CollectionPermission(collection_id=space.id,user_id=editor.id,role='editor')])
    categories=[dict(id='figuren',title='Figuren',icon='📦'),dict(id='leer',title='Leer',icon='📦')]
    m.app_setting_set(f'custom_collection_categories_{owner.id}',json.dumps(categories))
    m.app_setting_set(f'custom_collection_categories_{foreign.id}',json.dumps([dict(id='figuren',title='Fremde Figuren',icon='📦')]))
    own=m.CollectorItem(user_id=owner.id,category='custom',title='Figur',notes='Behalten',estimated_value_eur=42,
                        metadata_json=json.dumps({'custom_category':'figuren','extra':'keep'}))
    other_item=m.CollectorItem(user_id=foreign.id,category='custom',title='Fremde Figur',metadata_json=json.dumps({'custom_category':'figuren'}))
    m.db.session.add_all([own,other_item]);m.db.session.commit()
    own_id,other_id=own.id,other_item.id

    def client(username,password):
        c=m.app.test_client();assert c.post('/login',data={'username':username,'password':password}).status_code==302
        return c
    edit=client('category-editor','editor-pass')
    read=client('category-viewer','viewer-pass')
    # Editing keeps stable category IDs and all copy metadata.
    edit_url='/collector/custom-categories/figuren/edit'
    assert read.get(edit_url).status_code==403
    page=edit.get(edit_url).get_data(as_text=True)
    edit_token=re.search(r'name="category_token" value="([^"]+)"',page).group(1)
    assert edit.post(edit_url,data={'title':'Neu'}).status_code==400
    assert edit.post(edit_url,data={'category_token':edit_token,'title':'X'}).status_code==400
    assert edit.post(edit_url,data={'category_token':edit_token,'title':'Meine Figuren','icon':'🧸','description':'Neue Beschreibung'}).status_code==302
    config=m._custom_collection_category(owner.id,'figuren')
    assert config['title']=='Meine Figuren' and config['icon']=='🧸' and config['description']=='Neue Beschreibung'
    assert m.collector_metadata(own)['custom_category']=='figuren'
    assert m._custom_collection_category(foreign.id,'figuren')['title']=='Fremde Figuren'
    assert edit.get('/collector/custom-categories/movies/edit').status_code==404

    # Bulk move is atomic, custom-only and scoped to the active collection.
    extra=m.CollectorItem(user_id=owner.id,category='custom',title='Zweite Figur',metadata_json=json.dumps({'custom_category':'figuren','note':'preserve'}))
    movie=m.CollectorItem(user_id=owner.id,category='movies',title='Film')
    m.db.session.add_all([extra,movie]);m.db.session.commit()
    section=edit.get('/collector/custom?custom_category=figuren').get_data(as_text=True)
    move_token=re.search(r'name="category_token" value="([^"]+)"',section).group(1)
    move_url='/collector/custom-categories/move-items'
    data={'category_token':move_token,'target_category':'leer','item_ids':[str(own_id),str(extra.id)]}
    assert read.post(move_url,data=data).status_code==403
    assert edit.post(move_url,data={'target_category':'leer','item_ids':[str(own_id)]}).status_code==400
    assert edit.post(move_url,data={**data,'target_category':'unknown'}).status_code==404
    assert edit.post(move_url,data={**data,'item_ids':[str(own_id),str(other_id)]}).status_code==404
    assert m.collector_metadata(own)['custom_category']=='figuren'
    assert edit.post(move_url,data={**data,'item_ids':[str(own_id),str(movie.id)]}).status_code==404
    assert edit.post(move_url,data={**data,'item_ids':['²']}).status_code==400
    assert edit.post(move_url,data={**data,'item_ids':[]}).status_code==302
    assert edit.post(move_url,data=data).status_code==302
    assert m.collector_metadata(own)=={'custom_category':'leer','extra':'keep'}
    assert m.collector_metadata(extra)=={'custom_category':'leer','note':'preserve'}
    assert edit.post(move_url,data={**data,'target_category':''}).status_code==302
    assert 'custom_category' not in m.collector_metadata(own)
    assert edit.post(move_url,data={**data,'target_category':'figuren'}).status_code==302

    url='/collector/custom-categories/figuren/delete'
    assert read.get(url).status_code==403
    assert read.post(url,data={'confirm_delete':'1'}).status_code==403
    assert 'Diese Kategorie löschen' not in read.get('/collector/custom?custom_category=figuren').get_data(as_text=True)
    page=edit.get(url)
    assert page.status_code==200
    if os.environ.get('BIBO_UI_SNAPSHOTS'):
        snapshots=Path(os.environ['BIBO_UI_SNAPSHOTS']);snapshots.mkdir(parents=True,exist_ok=True)
        (snapshots/'delete.html').write_text(page.get_data(as_text=True))
    assert '2 Objekte bleiben erhalten' in page.get_data(as_text=True)
    assert len(m.custom_collection_categories(owner.id))==2, 'GET cannot mutate categories'
    token=re.search(r'name="delete_token" value="([^"]+)"',page.get_data(as_text=True)).group(1)
    assert edit.post(url,data={'confirm_delete':'1'}).status_code==400
    assert edit.post(url,data={'delete_token':token}).status_code==302
    assert len(m.custom_collection_categories(owner.id))==2
    assert edit.post(url,data={'delete_token':token,'confirm_delete':'1'}).status_code==302
    assert m._custom_collection_category(owner.id,'figuren') is None
    assert m._custom_collection_category(foreign.id,'figuren') is not None
    own=m.db.session.get(m.CollectorItem,own_id);other_item=m.db.session.get(m.CollectorItem,other_id)
    assert m.collector_metadata(own)=={'extra':'keep'}
    assert own.notes=='Behalten' and own.estimated_value_eur==42
    assert m.collector_metadata(other_item)['custom_category']=='figuren'
    assert edit.get(url).status_code==404
    assert edit.post(url,data={'delete_token':token,'confirm_delete':'1'}).status_code==404
    assert edit.get('/collector/custom-categories/movies/delete').status_code==404
    assert edit.get('/collector/custom').status_code==200
    home=edit.get('/').get_data(as_text=True)
    assert 'id="custom-figuren"' not in home and 'id="custom-leer"' in home
    empty_url='/collector/custom-categories/leer/delete'
    empty_page=edit.get(empty_url).get_data(as_text=True)
    assert 'keine Objekte' in empty_page
    token=re.search(r'name="delete_token" value="([^"]+)"',empty_page).group(1)
    assert edit.post(empty_url,data={'delete_token':token,'confirm_delete':'1'}).status_code==302
    assert m.custom_collection_categories(owner.id)==[]
    assert m.db.session.get(m.CollectorItem,own_id) is not None
    # Preset and custom icons survive creation, edits and validation errors.
    assert 'data-category-icon-select' in home
    assert edit.post('/collector/custom-categories',data={'title':'Brettspiele','icon':'🎲'}).status_code==302
    icon_category=m.custom_collection_categories(owner.id)[0]
    assert icon_category['icon']=='🎲'
    icon_url=f"/collector/custom-categories/{icon_category['id']}/edit"
    icon_page=edit.get(icon_url).get_data(as_text=True)
    assert 'value="🎲" selected' in icon_page
    icon_token=re.search(r'name="category_token" value="([^"]+)"',icon_page).group(1)
    assert edit.post(icon_url,data={'category_token':icon_token,'title':'Drachen','icon':'__custom__','custom_icon':'🐉'}).status_code==302
    assert m._custom_collection_category(owner.id,icon_category['id'])['icon']=='🐉'
    icon_page=edit.get(icon_url).get_data(as_text=True)
    assert 'value="__custom__" selected' in icon_page and 'value="🐉"' in icon_page
    invalid=edit.post(icon_url,data={'category_token':icon_token,'title':'X','icon':'__custom__','custom_icon':'🐲'})
    assert invalid.status_code==400 and 'value="🐲"' in invalid.get_data(as_text=True)
    if os.environ.get('BIBO_UI_SNAPSHOTS'):
        (snapshots/'edit.html').write_text(icon_page)
    print('OK: category editing, atomic bulk move, deletion, copy preservation, permissions, confirmation, isolation and dashboard')
