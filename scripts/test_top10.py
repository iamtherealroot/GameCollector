#!/usr/bin/env python3
import importlib, json, os, re, sys, tempfile
from pathlib import Path
from flask import g
from flask.testing import FlaskClient
from werkzeug.security import generate_password_hash

sandbox=tempfile.TemporaryDirectory(prefix='bibo-top10-')
os.environ.update(DATABASE_URL='sqlite:///'+str(Path(sandbox.name)/'test.db'),ADMIN_USERNAME='ranking-admin',ADMIN_PASSWORD='ranking-pass')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
m=importlib.import_module('app.app');m.app.config['TESTING']=True
class IsolatedClient(FlaskClient):
    def open(self,*args,**kwargs):g.pop('_login_user',None);return super().open(*args,**kwargs)
m.app.test_client_class=IsolatedClient
with m.app.app_context():
    owner=m.shared_collection_user();space=m.CollectionSpace.query.filter_by(owner_user_id=owner.id).one()
    viewer=m.User(username='ranking-viewer',password_hash=generate_password_hash('pass'),role='viewer')
    manager=m.User(username='ranking-manager',password_hash=generate_password_hash('pass'),role='editor')
    private=m.User(username='PRIVATE-OWNER-SECRET',password_hash=generate_password_hash('pass'),is_system=True)
    m.db.session.add_all([viewer,manager,private]);m.db.session.flush()
    m.db.session.add(m.CollectionSpace(name='PRIVATE-SPACE-SECRET',slug='private-rank',owner_user_id=private.id))
    m.db.session.add(m.CollectionPermission(collection_id=space.id,user_id=manager.id,role='manager',can_edit_items=False))
    console=m.Console(name='Rank Console');m.db.session.add(console);m.db.session.flush()
    game=m.Game(title='Rank Game',console_id=console.id);m.db.session.add(game);m.db.session.flush()
    for i in range(15):m.db.session.add(m.CollectionItem(user_id=owner.id,game_id=game.id,status='owned',auto_value_eur=100+i,estimated_value=999))
    m.db.session.add_all([m.CollectionItem(user_id=private.id,game_id=game.id,auto_value_eur=9999),
        m.CollectionItem(user_id=owner.id,game_id=game.id,status='wishlist',auto_value_eur=9998),
        m.CollectionItem(user_id=owner.id,game_id=game.id,status='owned',ownership_format='digital',auto_value_eur=9997)])
    for category in ['movies','tv','books','music','cards','custom']:
        m.db.session.add_all([m.CollectorItem(user_id=owner.id,category=category,title='Visible '+category,auto_value_eur=55,estimated_value_eur=900,quantity=20),
            m.CollectorItem(user_id=private.id,category=category,title='PRIVATE-PRODUCT-SECRET',auto_value_eur=5000),
            m.CollectorItem(user_id=owner.id,category=category,title='WISHLIST-PRODUCT',auto_value_eur=9999,metadata_json=json.dumps({'status':'wishlist'}))])
    model=m.HardwareModel(console_id=console.id,name='Rank Hardware');m.db.session.add(model);m.db.session.flush()
    m.db.session.add_all([m.HardwareItem(user_id=owner.id,hardware_model_id=model.id,auto_value_eur=70),
        m.AccessoryItem(user_id=owner.id,name='Rank Accessory',auto_value_eur=80),
        m.AccessoryItem(user_id=owner.id,name='Component excluded',auto_value_eur=9000,included_in_parent_value=True)])
    m.db.session.commit()
    def login(name,password='pass'):
        c=m.app.test_client();assert c.post('/login',data={'username':name,'password':password}).status_code==302;return c
    user=login(viewer.username);mgr=login(manager.username)
    assert m.app.test_client().get('/top10').status_code==302
    assert user.get('/top10/settings').status_code==403
    assert 'Rank Game' not in user.get('/top10').get_data(as_text=True)
    prefpage=user.get('/top10/preferences').get_data(as_text=True)
    preftoken=re.search(r'name="top10_token" value="([^"]+)"',prefpage).group(1)
    assert user.post('/top10/preferences',data={'enabled':'1'}).status_code==400
    assert user.post('/top10/preferences',data={'top10_token':preftoken,'enabled':'1'}).status_code==302
    page=mgr.get('/top10/settings').get_data(as_text=True)
    token=re.search(r'name="top10_token" value="([^"]+)"',page).group(1)
    assert mgr.post('/top10/settings',data={'enabled':'1'}).status_code==400
    assert mgr.post('/top10/settings',data={'top10_token':token,'enabled':'1','collection_alias':'Public Collection','collector_alias':'Public Collector'}).status_code==302
    page=user.get('/top10').get_data(as_text=True)
    assert page.count('class="top10-row"')==10
    assert 'Public Collection' in page and 'Public Collector' in page
    assert 'PRIVATE-OWNER-SECRET' not in page and 'PRIVATE-SPACE-SECRET' not in page and '9.999' not in page
    assert '114,00' in page and '999,00' not in page
    for category in ['movies','tv','books','music','cards','custom']:
        page=user.get('/top10?category='+category).get_data(as_text=True)
        assert 'Visible '+category in page and '55,00' in page
        assert 'PRIVATE-PRODUCT-SECRET' not in page and 'WISHLIST-PRODUCT' not in page
    assert 'Rank Hardware' in user.get('/top10?category=hardware').get_data(as_text=True)
    page=user.get('/top10?category=accessories').get_data(as_text=True)
    assert 'Rank Accessory' in page and 'Component excluded' not in page
    assert user.post('/top10/settings',data={'top10_token':token,'enabled':'1'}).status_code==403
    assert mgr.post('/top10/settings',data={'top10_token':token}).status_code==302
    assert 'Public Collection' not in user.get('/top10').get_data(as_text=True)
    assert user.get('/top10?category=invalid').status_code==404
    assert user.post('/top10/preferences',data={'top10_token':preftoken}).status_code==302
    assert m.db.session.get(m.Top10UserPreference,viewer.id).enabled is False
    assert 'class="top10-row"' not in user.get('/top10').get_data(as_text=True)
    other_space=m.CollectionSpace.query.filter_by(owner_user_id=private.id).one()
    m.db.session.delete(other_space);m.db.session.commit()
    assert m.CollectionSpace.query.count()==1
    assert user.post('/top10/preferences',data={'top10_token':preftoken,'enabled':'1'}).status_code==400
    assert mgr.post('/top10/settings',data={'top10_token':token,'enabled':'1','collection_alias':'Public Collection','collector_alias':'Public Collector'}).status_code==400
    assert 'mindestens zwei' in user.get('/top10').get_data(as_text=True)
    print('OK: opt-in Top 10, all categories, source precedence, rank limits, privacy, rights and withdrawal')
