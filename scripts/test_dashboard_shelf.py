#!/usr/bin/env python3
import importlib,os,sys,tempfile
from pathlib import Path
from flask import g
from flask.testing import FlaskClient
from werkzeug.security import generate_password_hash
temp=tempfile.TemporaryDirectory(prefix='bibo-shelf-')
os.environ.update(DATABASE_URL='sqlite:///'+str(Path(temp.name)/'test.db'),ADMIN_USERNAME='shelf-admin',ADMIN_PASSWORD='shelf-pass')
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
m=importlib.import_module('app.app');m.app.config['TESTING']=True
class Client(FlaskClient):
    def open(self,*args,**kwargs):g.pop('_login_user',None);return super().open(*args,**kwargs)
m.app.test_client_class=Client
def route_url(endpoint,**values):
    with m.app.test_request_context():return m.url_for(endpoint,**values)
with m.app.app_context():
    owner=m.shared_collection_user();space=m.CollectionSpace.query.filter_by(owner_user_id=owner.id).one()
    reader=m.User(username='shelf-reader',password_hash=generate_password_hash('pass'),role='viewer')
    m.db.session.add(reader);m.db.session.flush();m.db.session.add(m.CollectionPermission(collection_id=space.id,user_id=reader.id,role='viewer'));m.db.session.commit()
    client=m.app.test_client();assert client.post('/login',data={'username':'shelf-admin','password':'shelf-pass'}).status_code==302
    home=client.get('/');assert home.status_code==200
    page=home.get_data(as_text=True)
    assert 'collection-shelf.css' in page and 'collection-shelf.js' in page and 'collection-regal' in page
    for title in ['Games','Filme','Serien','Bücher','Musik','Sammelkarten']:assert f'title="{title}">{title}</strong>' in page and f'<h2>{title}</h2>' not in page
    assert 'Weitere Sammlungen öffnen' not in page
    assert 'regal-empty-space' in page and 'href="#custom-category-create"' in page
    assert 'aria-label="Games öffnen' in page and '0 Objekte' in page
    # Actual titles and formats come only from the active collection.
    m.db.session.add_all([
        m.CollectorItem(user_id=owner.id,category='movies',title='Blue Film',media_type='Blu-ray'),
        m.CollectorItem(user_id=owner.id,category='movies',title='Black Film',media_type='DVD'),
        m.CollectorItem(user_id=reader.id,category='movies',title='PRIVATE OTHER TITLE',media_type='DVD'),
        m.CollectorItem(user_id=owner.id,category='custom',title='Own Figurine',media_type='Figur'),
    ]);m.db.session.commit()
    filled=client.get('/').get_data(as_text=True)
    assert 'Blue Film' in filled and 'Black Film' in filled and 'PRIVATE OTHER TITLE' not in filled
    assert 'case-bluray' in filled and 'case-dvd' in filled
    assert 'Weitere Sammlungen öffnen' in filled and 'Own Figurine' in filled
    from html.parser import HTMLParser
    class Links(HTMLParser):
        def __init__(self):super().__init__();self.active=False;self.links=[]
        def handle_starttag(self,tag,attrs):
            if tag=='a':
                assert not self.active, 'Nested anchors break direct medium links'
                self.active=True;self.links.append(dict(attrs))
        def handle_endtag(self,tag):
            if tag=='a':self.active=False
    parsed=Links();parsed.feed(filled)
    film=m.CollectorItem.query.filter_by(title='Blue Film',user_id=owner.id).one()
    link=next(link for link in parsed.links if link.get('aria-label')=='Blue Film öffnen')
    assert link['href']==route_url('collector_item_detail',item_id=film.id)
    assert client.get(link['href']).status_code==200
    category_links=[link for link in parsed.links if 'regal-category-spine' in link.get('class','')]
    assert category_links and all('title' in link and ' öffnen' in link['aria-label'] for link in category_links)
    assert all('regal-spine-title' not in link.get('class','') for link in category_links)
    console=m.Console.query.first()
    game=m.Game(title='FIFA 98',console_id=console.id)
    m.db.session.add(game);m.db.session.flush()
    m.db.session.add(m.CollectionItem(game_id=game.id,user_id=owner.id,status='owned'));m.db.session.commit()
    parsed=Links();parsed.feed(client.get('/').get_data(as_text=True))
    game_link=next(link for link in parsed.links if link.get('aria-label')=='FIFA 98 öffnen')
    assert game_link['href'].startswith(route_url('game_detail',game_id=game.id))
    assert client.get(game_link['href']).status_code==200
    # Resolve the real route rather than invent an endpoint path.
    create=next(rule.rule for rule in m.app.url_map.iter_rules() if rule.endpoint=='custom_collection_category_create')
    assert client.post(create,data={'title':'Shelf Test','icon':'🎲'}).status_code==302
    page=client.get('/').get_data(as_text=True)
    assert 'title="Shelf Test">Shelf Test</strong>' in page and 'custom_category=' in page
    other=m.app.test_client();assert other.post('/login',data={'username':'shelf-reader','password':'pass'}).status_code==302
    readonly=other.get('/').get_data(as_text=True)
    assert 'collection-regal' in readonly and 'regal-empty-space' not in readonly
    assert other.post(create,data={'title':'Forbidden','icon':'📦'}).status_code==403
    tour=client.get('/api/tutorial').get_json();assert any(step['title']=='Dein Sammlungsregal' for step in tour['steps'])
    import re
    def style_token(browser):
        form=browser.get('/account').get_data(as_text=True).split('<form class="dashboard-style-switch"')[1].split('</form>')[0]
        return re.search(r'name="token" value="([^"]+)"',form).group(1)
    token=style_token(client)
    assert client.post('/dashboard/style',data={'style':'cards'}).status_code==400
    assert client.post('/dashboard/style',data={'token':token,'style':'invalid'}).status_code==400
    foreign=other.post('/dashboard/style',data={'token':token,'style':'cards'});assert foreign.status_code==400,(foreign.status_code,foreign.get_data(as_text=True)[:200])
    assert client.post('/dashboard/style',data={'token':token,'style':'cards','user_id':reader.id}).status_code==302
    cards=client.get('/').get_data(as_text=True)
    assert '<h2>Games</h2>' in cards and 'collection-cards.js' in cards and 'data-shelf-cases' not in cards
    assert 'regal-shake-trigger' not in cards
    assert 'data-shelf-cases' in other.get('/').get_data(as_text=True)
    assert any(step['title']=='Deine Sammlungskacheln' for step in client.get('/api/tutorial').get_json()['steps'])
    renewed=m.app.test_client();renewed.post('/login',data={'username':'shelf-admin','password':'shelf-pass'})
    assert 'collection-cards.js' in renewed.get('/').get_data(as_text=True)
    reader_token=style_token(other)
    assert other.post('/dashboard/style',data={'token':reader_token,'style':'cards'}).status_code==302
    assert 'collection-cards.js' in other.get('/').get_data(as_text=True)
    assert client.post('/dashboard/style',data={'token':token,'style':'shelf'}).status_code==302
    assert 'data-shelf-cases' in client.get('/').get_data(as_text=True)
    assert client.post('/dashboard/style',data={'token':token,'style':'glass'}).status_code==302
    glass=client.get('/').get_data(as_text=True);assert 'regal-skin-glass' in glass
    assert 'dashboard-style-switch' not in glass
    assert 'regal-helper-door' in glass and 'regal-doorman' in glass
    assert 'dashboard-appearance' in client.get('/account').get_data(as_text=True)
    saved=client.post('/dashboard/style',data={'token':token,'style':'glass','return_to':'account'})
    assert saved.status_code==302 and saved.headers['Location'].endswith('/account')
    payload=client.get('/dashboard/easter-helpers').get_json()
    figures=''.join(payload['helpers'].values())+payload['guard']
    for character in ['sport-blue','pirate-captain','detective-blue','rapper-tracksuit','profession-baker','profession-diver','class-miner','falconer-ranger']:
        assert f'data-character="{character}"' in figures
    for character in ['mario','luigi','hitman','walter','ash','actor','wizard','adventurer']:
        assert f'data-character="{character}"' not in figures
    assert figures.count('class="regal-security-template"')==4
    assert 'href="/static/shelf-security.png"' in figures
    assert 'regal-shake-status' not in glass
    assert glass.count('class="regal-helper-door"')==1
    assert glass.count('class="regal-shelf-board"')==glass.count('class="regal-spine-wrap"')+1
    card_tile=glass.split('collector-module-cards shelf-compartment')[1].split('</article>')[0]
    assert 'href="/collector/cards"' in card_tile and 'regal-door-panel' in card_tile
    # Named music fields must become literal clauses; edition barcode/count survive.
    mb_calls=[]
    old_mb=m.musicbrainz_json
    def mb_stub(path, params=None):
        mb_calls.append((path,params))
        return {"releases":[{"id":"11111111-2222-3333-4444-555555555555","title":"Test Album","artist-credit":[{"name":"Test Artist"}],"barcode":"1234567890123","country":"DE","date":"2020-01-01","media":[{"format":"CD","track-count":10},{"format":"CD","track-count":8}]}]}
    m.musicbrainz_json=mb_stub
    try:
        response=client.get('/collector/music/search',query_string={'mode':'fields','artist':'Band" OR release:*','album':'Test Album'})
        assert response.status_code==200
        assert mb_calls[-1][1]['query']=='artist:"Band\\" OR release:*" AND release:"Test Album"'
        music_page=response.get_data(as_text=True)
        assert 'Musik bestimmen' in music_page and '2 Tonträger' in music_page
        assert 'name="barcode" value="1234567890123"' in music_page
        assert 'name="disc_count" value="2"' in music_page
        before=len(mb_calls);client.get('/collector/music/search?mode=fields');assert len(mb_calls)==before
        assert 'Musik bestimmen' in client.get('/collector/music').get_data(as_text=True)
        imported=client.post('/collector/music/import',data={'title':'Test Album','artist':'Test Artist','barcode':'1234567890123','disc_count':'2','track_count':'18','media_type':'CD'})
        assert imported.status_code==302
        intake=client.get(imported.headers['Location']).get_data(as_text=True)
        assert 'name="disc_count" type="number" min="1" max="99" value="2"' in intake
        saved=client.post(route_url('collector_media_questionnaire'),data={'category':'music','title':'Test Album','artist':'Test Artist','barcode':'1234567890123','media_type':'CD','disc_count':'2','track_count':'18'})
        assert saved.status_code==302,(saved.status_code,saved.get_data(as_text=True)[:300])
        added=m.CollectorItem.query.filter_by(user_id=owner.id,category='music',title='Test Album').one()
        assert m.collector_metadata(added)['disc_count']==2 and m.collector_metadata(added)['track_count']==18

    finally:
        m.musicbrainz_json=old_mb
css=(ROOT/'app/static/collection-shelf.css').read_text()
assert 'writing-mode:vertical-rl' in css and '@media(max-width:720px)' in css
assert '@media(prefers-reduced-motion:reduce)' in css and '.shelf-compartment:focus-visible' in css
assert 'translate3d(0,-14px,95px)' in css and '@media(hover:hover)' in css
print('OK: shelf routes, named spines, category creation, read-only rights, tutorial, keyboard/reduced-motion/responsive contracts')
from app.shelf import case_style,shelf_cases
for media,style in [('Nintendo Switch','switch'),('Xbox 360','xbox360'),('PlayStation 2','dvd-game'),('PlayStation 1','ps1'),('PlayStation 3','ps3')]:
    assert case_style('games',media)==style
assert case_style('movies','4K UHD')=='uhd' and case_style('music','Vinyl')=='vinyl'
cases=shelf_cases('movies',[('Only real title','Blu-ray')]);assert len(cases)==7
assert sum(bool(case['title']) for case in cases)==1
mixed=shelf_cases('games',[('Small','PlayStation'),('Medium','PlayStation 3'),('Large','Xbox 360')])
assert [case['height'] for case in mixed]==sorted(case['height'] for case in mixed)

assert case_style('games','Game Boy',False)=='gb-cartridge'
assert case_style('games','Game Boy',True)=='retro-box'
assert case_style('games','Nintendo 64',False)=='n64-cartridge'
assert case_style('games','Super Nintendo',False)=='snes-cartridge'
