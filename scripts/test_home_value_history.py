#!/usr/bin/env python3
"""Real owner-scoped value history, daily signs and selectable portfolio chart."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
from datetime import datetime,timedelta
sandbox=tempfile.TemporaryDirectory(prefix='bibo-home-value-')
os.environ.update(DATABASE_URL='sqlite:///'+str(Path(sandbox.name)/'test.db'),ADMIN_USERNAME='history-admin',ADMIN_PASSWORD='pass')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
m=importlib.import_module('app.app');m.app.config['TESTING']=True
with m.app.app_context():
    owner=m.shared_collection_user();now=datetime(2026,11,1,12)
    empty=m.home_value_history(owner.id,100,'24h',now)
    assert not empty['has_history'] and empty['day_delta'] is None
    def add(value,hours,uid=owner.id):
        m.db.session.add(m.CollectorValueSnapshot(collection_user_id=uid,total_value_eur=value,recorded_at=now-timedelta(hours=hours)))
    foreign=m.User(username='history-foreign',password_hash='unused',is_system=True)
    m.db.session.add(foreign);m.db.session.flush()
    add(100,25);add(120,12);add(999999,24,foreign.id);m.db.session.commit()
    up=m.home_value_history(owner.id,130,'24h',now)
    assert up['day_delta']==30 and up['day_percent']==30 and up['delta']==30
    assert up['low']==100 and up['high']==130 and ' V ' in up['path']
    down=m.home_value_history(owner.id,80,'7d',now)
    assert down['day_delta']==-20 and down['day_percent']==-20
    flat=m.home_value_history(owner.id,100,'1m',now);assert flat['day_delta']==0
    assert m.home_value_history(owner.id,100,'bad',now)['period']=='7d'
    assert m.home_value_history(owner.id,100,'all',now)['delta']==0
    # No percentage is invented when the reference value is zero.
    m.CollectorValueSnapshot.query.filter_by(collection_user_id=owner.id).delete()
    add(0,24);m.db.session.commit()
    assert m.home_value_history(owner.id,50,'24h',now)['day_percent'] is None
    m.CollectorValueSnapshot.query.filter_by(collection_user_id=owner.id).delete()
    add(100,100);m.db.session.commit()
    assert m.home_value_history(owner.id,120,'24h',now)['day_delta'] is None
    # Start page stores measured points without making one for each refresh.
    m.CollectorValueSnapshot.query.delete();m.db.session.commit()
    row=m.CollectorItem(user_id=owner.id,category='books',title='Owned book',estimated_value_eur=10)
    wanted=m.CollectorItem(user_id=owner.id,category='books',title='Wanted book',estimated_value_eur=900,metadata_json='{"status":"wishlist"}')
    m.db.session.add_all([row,wanted]);m.db.session.commit()
    client=m.app.test_client();client.post('/login',data={'username':'history-admin','password':'pass'})
    page=client.get('/?value_period=1y');assert page.status_code==200
    html=page.get_data(as_text=True)
    assert 'Aktueller Gesamtwert' in html and 'Tagesvergleich noch nicht verfügbar' in html
    assert 'aria-label="Zeitraum der Wertentwicklung"' in html
    count=m.CollectorValueSnapshot.query.filter_by(collection_user_id=owner.id).count()
    client.get('/');assert m.CollectorValueSnapshot.query.filter_by(collection_user_id=owner.id).count()==count
    admin=m.User.query.filter_by(username='history-admin').one()
    assert m.app_setting_get(f'home_value_period_{admin.id}_{owner.id}')=='1y'
    data=m.dashboard_collection_data(owner.id);snap=m.collector_total_value_snapshot(owner.id)
    assert data['collector_value']==snap.total_value_eur==10
    assert data['collector_count']==snap.owned_count==1
    assert data['collector_valued_count']==snap.valued_count==1
    # Enough measurements for a year's small graph remain bounded in HTML size.
    m.db.session.rollback()
    for i in range(1000): add(100+(i%30),1000-i)
    m.db.session.commit()
    assert len(m.home_value_history(owner.id,110,'all',now)['points'])<=365
print('OK: owner-isolated history, 24h rise/fall/flat, zero/stale/missing baselines, remembered periods, bounded snapshots/graph and consistent owned totals')
