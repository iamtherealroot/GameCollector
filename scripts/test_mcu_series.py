#!/usr/bin/env python3
"""MCU is visible as its own film series, with scoped ownership and viewing order."""
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
from flask import g, template_rendered
from flask.testing import FlaskClient

sandbox=tempfile.TemporaryDirectory(prefix='bibo-mcu-series-')
os.environ.update(DATABASE_URL='sqlite:///'+str(Path(sandbox.name)/'test.db'),ADMIN_USERNAME='mcu-admin',ADMIN_PASSWORD='test-pass')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
m=importlib.import_module('app.app');m.app.config['TESTING']=True
class Client(FlaskClient):
    def open(self,*args,**kwargs):
        g.pop('_login_user',None)
        return super().open(*args,**kwargs)
m.app.test_client_class=Client
captured=[]
def capture(sender,template,context,**extra):captured.append(context)
template_rendered.connect(capture,m.app)
with m.app.app_context():
    client=m.app.test_client()
    assert client.post('/login',data={'username':'mcu-admin','password':'test-pass'}).status_code==302
    owner=m.shared_collection_user()
    client.get('/collector/collections?type=movies')
    group=next(x for x in captured[-1]['groups'] if x.get('catalog_umbrella'))
    assert group['name']=='Marvel Cinematic Universe (MCU)' and group['owned']==0 and group['total']==38
    foreign=m.User(username='foreign-mcu',password_hash='unused',is_system=True)
    m.db.session.add(foreign);m.db.session.flush()
    for title,year,user,value in [('Iron Man 2',2010,owner,4.72),('Guardians of the Galaxy',2014,owner,6.0),('X-Men',2000,owner,7.0),('Iron Man',2008,foreign,999.0)]:
        m.db.session.add(m.CollectorItem(user_id=user.id,category='movies',title=title,release_year=year,media_type='Blu-ray',estimated_value_eur=value,metadata_json=json.dumps({'ownership_format':'physical','status':'owned'})))
    m.db.session.commit()
    client.get('/collector/collections?type=movies')
    overview=captured[-1]
    group=next(x for x in overview['groups'] if x.get('catalog_umbrella'))
    assert group['owned']==2 and abs(group['value']-10.72)<.001
    assert overview['overview']['owned']==sum(x['owned'] for x in overview['groups'] if not x.get('catalog_umbrella'))
    assert abs(overview['overview']['value']-sum(x['value'] for x in overview['groups'] if not x.get('catalog_umbrella')))<.001
    assert '/collector/movies/marvel?' in group['detail_url'] and 'branch=MCU' in group['detail_url']
    client.get(group['detail_url']+'&order=release')
    page=captured[-1]
    assert page['pagination']['total']==38 and page['total_owned']==2
    assert page['rows'][0]['entry']['title']=='Iron Man'
    assert all(x['entry']['branch']=='MCU' for x in page['rows'])
    assert next(x for x in page['rows'] if x['entry']['title']=='Iron Man 2')['owned']
    assert not next(x for x in page['rows'] if x['entry']['title']=='Iron Man')['owned']
    owned_row=next(x for x in page['rows'] if x['entry']['title']=='Iron Man 2')
    response=client.get(owned_row['detail_url'])
    assert response.status_code==200 and 'Exemplar bearbeiten' in response.get_data(as_text=True)
    assert '/library/copy/' in response.get_data(as_text=True)
    assert '4,72' in response.get_data(as_text=True) or '4.72' in response.get_data(as_text=True)
    response=client.get(group['detail_url']+'&order=release')
    assert 'collection-compact-head' in response.get_data(as_text=True) and 'collection-compact-price' in response.get_data(as_text=True)
    client.get(group['detail_url']+'&order=timeline')
    assert captured[-1]['rows'][0]['entry']['title']=='Captain America: The First Avenger'
    client.get('/collector/movies/marvel')
    assert captured[-1]['selected_order']=='timeline' and captured[-1]['selected_series']=='Marvel Cinematic Universe'
    client.get('/collector/movies/marvel?branch=Angek%C3%BCndigt')
    assert {x['entry']['title'] for x in captured[-1]['rows']} == {'Avengers: Doomsday','Avengers: Secret Wars'}
print('OK: always-visible MCU series, 38 films, scoped ownership, no double totals, release/timeline order and remembered choice')

with m.app.app_context():
    m.tmdb_json = lambda *args, **kwargs: None
    m.db.session.add(m.CollectorItem(
        user_id=m.shared_collection_user().id, category='movies', title='Testfilm',
        media_type='Blu-ray', metadata_json=json.dumps({
            'tmdb_collection': {'id': 987654, 'name': 'Testfilm-Reihe'},
        }),
    ))
    m.db.session.commit()
    response = client.get('/collector/movies/collection/987654')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '<h1>Testfilm-Reihe</h1>' in html
    assert 'Testfilm</a>' in html
    assert 'Die vollständige Filmliste ist derzeit nicht verfügbar.' in html
    assert '0 / ?' not in html
print('Filmreihendetail ohne TMDB-Daten geprüft.')

with m.app.app_context():
    movie = m.CollectorItem.query.filter_by(title='Testfilm').one()
    movie.metadata_json = json.dumps({
        'tmdb_id': 987651, 'physical_country': 'DE',
        'tmdb_collection': {'id': 987654, 'name': 'Testfilm-Reihe'},
    })
    m.db.session.commit()
    catalog = {'id': 987654, 'name': 'Testfilm-Reihe', 'parts': [
        {'id': 987651, 'title': 'Testfilm', 'poster_path': '/testfilm.jpg'},
        {'id': 987652, 'title': 'Testfilm 2', 'poster_path': '/testfilm2.jpg'},
    ]}
    def provider(path, params=None):
        if path == 'collection/987654':
            return catalog
        if path.endswith('/release_dates'):
            return {'results': [{'iso_3166_1': 'DE', 'release_dates': [{'type': 5}]}]}
        return {}
    m.tmdb_json = provider
    response = client.get('/collector/movies/collection/987654')
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert '1/2 vorhanden' in html and 'collector-cover-grid' in html
    assert 'testfilm2.jpg' in html and '✗ Fehlt' in html
print('Coveransicht mit vorhandenem und fehlendem Film geprüft.')
