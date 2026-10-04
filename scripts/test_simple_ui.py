#!/usr/bin/env python3
"""5.1.1: search order, bounded lists, invalidation, isolation and undo."""
import importlib, json, os, sys, tempfile
from datetime import timedelta
from pathlib import Path
from flask import g
from flask.testing import FlaskClient
from sqlalchemy import event
from werkzeug.security import generate_password_hash

sandbox=tempfile.TemporaryDirectory(prefix='bibo-simple-ui-')
os.environ.update(DATABASE_URL='sqlite:///'+str(Path(sandbox.name)/'test.db'),ADMIN_USERNAME='ui-admin',ADMIN_PASSWORD='ui-pass')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
m=importlib.import_module('app.app');m.app.config['TESTING']=True
class Client(FlaskClient):
    def open(self,*a,**kw):g.pop('_login_user',None);return super().open(*a,**kw)
m.app.test_client_class=Client
with m.app.app_context():
    owner=m.shared_collection_user();space=m.CollectionSpace.query.filter_by(owner_user_id=owner.id).one()
    foreign=m.User(username='foreign-ui-owner',password_hash='unused',is_system=True)
    reader=m.User(username='ui-reader',password_hash=generate_password_hash('pass'),role='viewer')
    m.db.session.add_all([foreign,reader]);m.db.session.flush()
    m.db.session.add(m.CollectionPermission(collection_id=space.id,user_id=reader.id,role='viewer'))
    console=m.Console.query.first()
    game=m.Game(title='Search Game',console_id=console.id,barcode='4000000000001',physical_status='physical')
    m.db.session.add(game);m.db.session.flush()
    copy=m.CollectionItem(game_id=game.id,user_id=owner.id,status='owned',estimated_value=12)
    m.db.session.add(copy)
    m.db.session.add_all([m.CollectorItem(user_id=owner.id,category='movies',title=f'Search Film {n:03}',barcode='4000000000001' if n==0 else None,media_type='Blu-ray',estimated_value_eur=10) for n in range(85)])
    m.db.session.add(m.CollectorItem(user_id=foreign.id,category='movies',title='Search PRIVATE FILM',media_type='DVD'))
    m.db.session.commit();client=m.app.test_client();client.post('/login',data={'username':'ui-admin','password':'ui-pass'})
    # Enter query first; neither results nor external calls before category choice.
    old_urlopen=m.urlopen
    def no_network(*a,**kw):raise AssertionError('Network call during local search/list')
    m.urlopen=no_network
    choice=client.get('/find?q=4000000000001').get_data(as_text=True)
    assert 'Medienart' in choice and 'Search Film 000' not in choice and 'Search Game' not in choice
    films=client.get('/find?q=4000000000001&type=movies').get_data(as_text=True)
    assert 'Search Film 000' in films and 'Search Game' not in films and 'Neu anlegen' in films
    games=client.get('/find?q=4000000000001&type=games').get_data(as_text=True)
    assert 'Search Game' in games and 'Search Film 000' not in games
    assert 'PRIVATE FILM' not in client.get('/find?q=Search&type=movies').get_data(as_text=True)
    assert 'Search Game' not in client.get('/find?q=Search&type=all').get_data(as_text=True)
    manual=client.get('/add/media?category=movies&title=Typed%20Title&barcode=4000000000002').get_data(as_text=True)
    assert 'value="Typed Title"' in manual and 'value="4000000000002"' in manual and 'Speichern und öffnen' in manual
    bad=client.post('/add/media',data={'category':'movies','title':'Keep This','purchase_price_eur':'invalid','barcode':'4000000000003'})
    assert bad.status_code==400 and 'value="Keep This"' in bad.get_data(as_text=True) and 'Kaufpreis:' in bad.get_data(as_text=True)
    assert not m.CollectorItem.query.filter_by(title='Keep This').first()
    created=client.post('/add/media',data={'category':'books','title':'Simple Book','media_type':'Hardcover'})
    assert created.status_code==302 and '/collector/item/' in created.location
    assert 'Weiteren hinzufügen' in client.get(created.location).get_data(as_text=True)
    # Rendering is capped, while totals/filter links describe the whole result.
    page=client.get('/collector/movies?q=Search&sort=name_asc').get_data(as_text=True)
    assert page.count('class="panel collector-item-row ')==40 and '1–40 von 85' in page
    next_page=client.get('/collector/movies?q=Search&sort=name_asc&page=2').get_data(as_text=True)
    assert 'Search Film 040' in next_page and 'Search Film 000' not in next_page
    assert 'PRIVATE FILM' not in page and 'page=2' in page and 'q=Search' in page
    # Summaries invalidate transactionally; repeated library reads do not rebuild.
    client.get('/');old_payload=json.loads(m.db.session.get(m.DashboardSummary,owner.id).payload)
    assert old_payload['module_stats']['movies']['count']==85
    film=m.CollectorItem.query.filter_by(title='Search Film 000').one();film.estimated_value_eur=123;m.db.session.commit()
    client.get('/');new_payload=json.loads(m.db.session.get(m.DashboardSummary,owner.id).payload)
    assert new_payload['module_stats']['movies']['value']==963
    m.CollectorItem.query.filter_by(id=film.id).update({'estimated_value_eur':321});m.db.session.commit()
    client.get('/');assert json.loads(m.db.session.get(m.DashboardSummary,owner.id).payload)['module_stats']['movies']['value']==1161
    client.get('/library');statements=[]
    def count(conn,cursor,statement,params,context,many):statements.append(statement)
    event.listen(m.db.engine,'before_cursor_execute',count)
    page=client.get('/library').get_data(as_text=True)
    event.remove(m.db.engine,'before_cursor_execute',count)
    assert not any(stmt.lstrip().upper().startswith(('INSERT ','UPDATE ','DELETE ')) for stmt in statements)
    assert page.count('class="bibo-register-row"')==40 and 'PRIVATE FILM' not in page
    # Capture price history + release coverage before deleting a copy.
    m.db.session.add(m.CollectorPriceHistory(collector_item_id=film.id,value_eur=42,source='fixture'))
    m.db.session.add(m.ReleaseCoverage(owner_id=owner.id,source_kind='collector',source_id=str(film.id),target_kind='movies',target_key='fixture:movie',target_title='Coverage',origin='manual'))
    m.db.session.commit();deleted_id=film.id
    assert client.post(f'/collector/item/{deleted_id}/delete').status_code==302
    token=client.get('/').get_data(as_text=True).split('name="token" value="')[1].split('"')[0]
    assert not m.db.session.get(m.CollectorItem,deleted_id)
    readonly=m.app.test_client();readonly.post('/login',data={'username':'ui-reader','password':'pass'})
    assert readonly.post('/collection/undo-delete',data={'token':token}).status_code==403
    assert client.post('/collection/undo-delete',data={'token':token}).status_code==302
    restored=m.CollectorItem.query.filter_by(title='Search Film 000').one()
    assert restored.estimated_value_eur==321 and len(restored.collector_price_history)==1
    assert m.ReleaseCoverage.query.filter_by(source_kind='collector',source_id=str(restored.id),target_key='fixture:movie').count()==1
    assert client.post('/collection/undo-delete',data={'token':token}).status_code==400
    # Game-copy history and date fields survive restoration as well.
    m.db.session.add(m.PriceHistory(collection_item_id=copy.id,value_eur=12,source='fixture'));m.db.session.commit()
    client.post(f'/collection/items/{copy.id}/delete')
    with client.session_transaction() as session:game_token=session['undo_deletion']
    assert client.post('/collection/undo-delete',data={'token':game_token}).status_code==302
    restored_copy=m.CollectionItem.query.filter_by(game_id=game.id,user_id=owner.id).one()
    assert len(restored_copy.price_history)==1 and restored_copy.estimated_value==12
    client.post(f'/collector/item/{restored.id}/delete')
    with client.session_transaction() as session:expired_token=session['undo_deletion']
    snapshot=m.db.session.get(m.UndoDeletion,expired_token);snapshot.expires_at=m.utc_now()-timedelta(seconds=1);m.db.session.commit()
    client.post('/collection/undo-delete',data={'token':expired_token});assert not m.CollectorItem.query.filter_by(title='Search Film 000').first()
    home=client.get('/').get_data(as_text=True)
    assert len(home)<160000 and 'data-character=' not in home and 'regal-shake-status' not in home
    lookup=[]
    old_resolver=m.collector_media_ean_results
    def resolver(code,limit):
        lookup.append(code)
        return ([dict(section='movies',id=1726,title='Iron Man',year=2008,cover_url='',overview='',original_title='Iron Man')], [], '')
    m.collector_media_ean_results=resolver
    dashboard=client.get('/find?q=4010324037190&type=movies').get_data(as_text=True)
    assert 'data-catalog-url=' in dashboard and 'ean=4010324037190' in dashboard
    assert lookup==[], 'Local search must not block on providers'
    fragment=client.get('/collector/media/search?section=movies&ean=4010324037190&fragment=1').get_data(as_text=True)
    assert lookup==['4010324037190'] and '<h3>Iron Man</h3>' in fragment
    assert '<html' not in fragment and 'name="tmdb_id" value="1726"' in fragment
    assert 'action="/collector/media/search"' in fragment
    m.collector_media_ean_results=old_resolver
    m.urlopen=old_urlopen
print('OK: input/category/results order, no local network calls, prefills/errors, pagination, cache/bulk invalidation, privacy, undo/history/coverage/expiry/rights and deferred supplied figures')
