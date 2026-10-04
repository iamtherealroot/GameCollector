#!/usr/bin/env python3
"""Reproducible offline comparison; fixtures are synthetic and isolated."""
import argparse, importlib, json, os, statistics, sys, tempfile, time
from pathlib import Path
from flask import g
from flask.testing import FlaskClient
from sqlalchemy import event

parser=argparse.ArgumentParser()
parser.add_argument('--source',default=str(Path(__file__).resolve().parents[1]))
args=parser.parse_args()
sandbox=tempfile.TemporaryDirectory(prefix='bibo-speed-')
os.environ.update(DATABASE_URL='sqlite:///'+str(Path(sandbox.name)/'bench.db'),ADMIN_USERNAME='bench-admin',ADMIN_PASSWORD='bench-pass')
sys.path.insert(0,args.source)
m=importlib.import_module('app.app');m.app.config['TESTING']=True
class Client(FlaskClient):
    def open(self,*a,**kw):g.pop('_login_user',None);return super().open(*a,**kw)
m.app.test_client_class=Client
with m.app.app_context():
    owner=m.shared_collection_user();console=m.Console.query.first()
    for n in range(300):
        game=m.Game(title=f'Benchmark Game {n:04}',console_id=console.id,physical_status='physical')
        m.db.session.add(game);m.db.session.flush()
        m.db.session.add(m.CollectionItem(game_id=game.id,user_id=owner.id,status='owned',estimated_value=float(n+1)))
    m.db.session.add_all([m.CollectorItem(user_id=owner.id,category='movies',title=f'Benchmark Film {n:04}',media_type='Blu-ray',estimated_value_eur=10) for n in range(200)])
    m.db.session.commit();m.refresh_bibo_registry()
    client=m.app.test_client();client.post('/login',data={'username':'bench-admin','password':'bench-pass'})
    statements=[]
    def count(conn,cursor,statement,parameters,context,executemany):statements.append(statement)
    event.listen(m.db.engine,'before_cursor_execute',count)
    result={'version':m.APP_VERSION,'fixture':{'games':300,'movies':200},'routes':{}}
    for route in ['/','/library','/collection','/collector/movies']:
        # Home's first visit populates the cache; still record its cold cost.
        samples=[]
        for run in range(4):
            m.db.session.remove();g.pop('_login_user',None);statements.clear()
            started=time.perf_counter();response=client.get(route);duration=time.perf_counter()-started
            assert response.status_code==200,(route,response.status_code)
            samples.append({'ms':round(duration*1000,2),'queries':len(statements),'writes':sum(stmt.lstrip().upper().startswith(('UPDATE ','INSERT ','DELETE ')) for stmt in statements),'html_bytes':len(response.data)})
        result['routes'][route]={'cold':samples[0],'warm_median_ms':round(statistics.median(x['ms'] for x in samples[1:]),2),'warm_queries':samples[-1]['queries'],'warm_writes':samples[-1]['writes'],'html_bytes':samples[-1]['html_bytes']}
    print(json.dumps(result,ensure_ascii=False,indent=2))
