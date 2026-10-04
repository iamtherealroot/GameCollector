#!/usr/bin/env python3
import importlib,os,sys,tempfile
from pathlib import Path
from datetime import timedelta
from flask import g
from flask.testing import FlaskClient
from werkzeug.security import generate_password_hash
sandbox=tempfile.TemporaryDirectory(prefix='bibo-inventory-crud-')
os.environ.update(DATABASE_URL='sqlite:///'+str(Path(sandbox.name)/'test.db'),ADMIN_USERNAME='crud-admin',ADMIN_PASSWORD='crud-pass')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
m=importlib.import_module('app.app');m.app.config['TESTING']=True
class Client(FlaskClient):
    def open(self,*a,**kw):g.pop('_login_user',None);return super().open(*a,**kw)
m.app.test_client_class=Client
with m.app.app_context():
    client=m.app.test_client();assert client.post('/login',data={'username':'crud-admin','password':'crud-pass'}).status_code==302
    owner=m.shared_collection_user();space=m.CollectionSpace.query.filter_by(owner_user_id=owner.id).one()
    viewer=m.User(username='crud-reader',password_hash=generate_password_hash('pass'),role='viewer')
    foreign=m.User(username='other-collection',password_hash='unused',is_system=True)
    m.db.session.add_all([viewer,foreign]);m.db.session.flush()
    m.db.session.add(m.CollectionPermission(collection_id=space.id,user_id=viewer.id,role='viewer'))
    console=m.Console(name='CRUD Console');m.db.session.add(console);m.db.session.flush()
    game=m.Game(title='CRUD Game',console_id=console.id);model=m.HardwareModel(name='CRUD Model',console_id=console.id)
    m.db.session.add_all([game,model]);m.db.session.commit()
    for value in ['nonsense','-1','inf','NaN']:
        assert client.post('/accessories',data={'name':'Bad','purchase_price':value}).status_code==400
        assert client.post(f'/hardware/{model.id}',data={'estimated_value':value}).status_code==400
        assert client.post(f'/collection/configure/{game.id}?new_copy=1',data={'estimated_value':value}).status_code==400
    assert client.post(f'/hardware/{model.id}',data={'purchase_date':'2026-02-30'}).status_code==400
    assert m.AccessoryItem.query.count()==0 and m.HardwareItem.query.count()==0 and m.CollectionItem.query.count()==0
    assert client.post('/accessories',data={'name':'CRUD Accessory','purchase_price':'12,50','estimated_value':'15,90'}).status_code==302
    accessory=m.AccessoryItem.query.one();assert accessory.purchase_price==12.5
    assert client.post(f'/accessories/{accessory.id}/edit',data={'name':'Renamed','purchase_price':'invalid'}).status_code==400
    m.db.session.refresh(accessory);assert accessory.name=='CRUD Accessory' and accessory.purchase_price==12.5
    assert client.post(f'/accessories/{accessory.id}/edit',data={'name':'Renamed','estimated_value':'20,10'}).status_code==302
    assert client.post(f'/hardware/{model.id}',data={'condition':'9','estimated_value':'45,60','purchase_date':'2026-10-03'}).status_code==302
    hardware=m.HardwareItem.query.one();assert hardware.estimated_value==45.6
    assert client.post(f'/hardware/items/{hardware.id}/edit',data={'estimated_value':'50,10','condition':'8'}).status_code==302
    assert client.post(f'/collection/configure/{game.id}?new_copy=1',data={'media_present':'on','estimated_value':'30,90'}).status_code==302
    copy=m.CollectionItem.query.one();assert copy.estimated_value==30.9
    assert client.post(f'/collection/configure/{game.id}',data={'item_id':str(copy.id),'media_present':'on','estimated_value':'35,50'}).status_code==302
    foreign_item=m.AccessoryItem(user_id=foreign.id,name='Foreign');m.db.session.add(foreign_item);m.db.session.commit()
    assert client.post('/accessories',data={'name':'Invalid parent','parent_accessory_id':str(foreign_item.id)}).status_code==400
    assert client.post(f'/accessories/{foreign_item.id}/delete').status_code==404
    reader=m.app.test_client();assert reader.post('/login',data={'username':'crud-reader','password':'pass'}).status_code==302
    for path in [f'/accessories/{accessory.id}/delete',f'/hardware/items/{hardware.id}/delete',f'/collection/item/{copy.id}/delete']:
        assert reader.post(path).status_code in {403,404}
    copy.auto_value_eur=100;copy.auto_value_source='eBay-Angebote';copy.auto_value_confidence='niedrig';copy.auto_value_updated_at=m.utc_now()-timedelta(days=50)
    m.db.session.commit()
    with m.app.test_request_context('/'):
        row=m._price_center_row(copy,'game')
    assert len(row['warnings'])>=3 and row['state']=='stale'
    for path in [f'/accessories/{accessory.id}/delete',f'/hardware/items/{hardware.id}/delete']:
        assert client.post(path).status_code==302
    delete_path=next(rule.rule for rule in m.app.url_map.iter_rules() if rule.endpoint=='collection_item_delete').replace('<int:item_id>',str(copy.id))
    assert client.post(delete_path).status_code==302
    assert m.db.session.get(m.Game,game.id) is not None and m.db.session.get(m.HardwareModel,model.id) is not None
    assert m.CollectionItem.query.count()==0 and m.HardwareItem.query.count()==0
print('OK: game/hardware/accessory create-edit-delete, money/date validation, no partial writes, isolation, reader rights and price warnings')
