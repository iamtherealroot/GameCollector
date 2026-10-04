#!/usr/bin/env python3
import importlib, os, re, sys, tempfile
from pathlib import Path
sandbox=tempfile.TemporaryDirectory(prefix='bibo-copy-condition-')
os.environ.update(DATABASE_URL='sqlite:///'+str(Path(sandbox.name)/'test.db'),ADMIN_USERNAME='copy-admin',ADMIN_PASSWORD='copy-pass')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
m=importlib.import_module('app.app')
with m.app.app_context():
    owner=m.shared_collection_user()
    console=m.Console(name='Condition Console');m.db.session.add(console);m.db.session.flush()
    game=m.Game(title='Condition Game',console_id=console.id);m.db.session.add(game);m.db.session.flush()
    item=m.CollectionItem(user_id=owner.id,game_id=game.id,box_condition=7)
    with m.app.test_request_context(method='POST',data={'media_present':'on','box_condition':'1'}):
        assert not m.update_collection_item_from_form(item)
    assert not item.box_present and item.box_condition==7 and item.completeness=='Loose'
    with m.app.test_request_context(method='POST',data={'media_present':'on','box_present':'on','box_condition':'5'}):
        m.update_collection_item_from_form(item)
    assert item.box_present and item.box_condition==5
    with m.app.test_request_context(method='POST',data={'sealed':'on','box_condition':'9'}):
        m.update_collection_item_from_form(item)
    assert item.sealed and item.box_present and item.box_condition==9
    with m.app.test_request_context(method='POST',data={'ownership_format':'digital','box_condition':'2'}):
        m.update_collection_item_from_form(item)
    assert not item.box_present and item.box_condition==9
    m.db.session.commit()
    client=m.app.test_client();assert client.post('/login',data={'username':'copy-admin','password':'copy-pass'}).status_code==302
    response=client.get(f'/collection/configure/{game.id}?new_copy=1')
    assert response.status_code==200
    page=response.get_data(as_text=True)
    assert 'disabled' in re.search(r'<input[^>]*name="box_condition"[^>]*>',page).group()
    assert 'copy-condition.js' in page
    settings=client.get('/help/tutorial-settings').get_data(as_text=True)
    assert 'tutorial-save-button' in settings and 'Tutorial-Einstellung speichern' in settings
print('OK: OVP absent/boxed/sealed/digital persistence, initial disabled form and prominent tutorial action')
