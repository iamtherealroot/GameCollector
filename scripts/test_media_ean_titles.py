#!/usr/bin/env python3
"""Physical film titles resolve through TMDB fallbacks without losing the EAN."""
import importlib
import os
from pathlib import Path
import sys
import tempfile

sandbox = tempfile.TemporaryDirectory(prefix="bibo-media-title-")
os.environ.update(DATABASE_URL="sqlite:///"+str(Path(sandbox.name)/"test.db"), ADMIN_USERNAME="media-admin", ADMIN_PASSWORD="test-pass")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
m = importlib.import_module("app.app")
m.app.config["TESTING"] = True
with m.app.app_context():
    products = [{"name": "Disney Baymax - Riesiges Robowabohu [DVD] | Zustand sehr gut", "source": "Test provider"} for _ in range(8)]
    m._collector_media_ean_terms = lambda code: ([(p["name"],p,None) for p in products], "ok")
    calls=[]
    def tmdb(path,params):
        calls.append((path,params["query"]))
        return {"results": [{"id":177572,"title":"Baymax - Riesiges Robowabohu","release_date":"2014-10-22"}] if path=='search/movie' and params['query']=='Baymax' else []}
    m.tmdb_json=tmdb
    results,_,_=m.collector_media_ean_results('8717418454098')
    assert len(results)==1 and results[0]['id']=='177572'
    assert results[0]['barcode']=='8717418454098' and results[0]['media_type']=='DVD'
    assert len(calls)==len(set(calls)) and len(calls)<=6, calls
    assert m._collector_media_title_queries('Spider-Man: No Way Home [4K UHD Blu-ray]')==['Spider-Man: No Way Home [4K UHD Blu-ray]','Spider-Man: No Way Home','Spider-Man']
    calls.clear()
    def offline(path,params): calls.append(path);return None
    m.tmdb_json=offline
    assert not m.collector_media_ean_results('8717418454098')[0] and len(calls)==2
    client=m.app.test_client()
    assert client.post('/login',data={'username':'media-admin','password':'test-pass'}).status_code==302
    page=client.get('/collector/media/search?section=movies&ean=8717418454098&fragment=1').get_data(as_text=True)
    assert 'Zur EAN gefundene Produkttitel' in page and 'name="ean" value="8717418454098"' in page
    assert 'name="q" value="Disney Baymax' in page and '<html' not in page
    # Search relevance survives pagination, duplicate hits and legacy date-sort links.
    def ranked(path, params):
        page = params.get('page', 1)
        titles = [('101','Relevant older work','1980-01-01'),('102','New less relevant work','2025-01-01')] if page == 1 else [('101','Relevant older work','1980-01-01'),('103','Last provider result','1995-01-01')] if page == 2 else []
        return {'results':[{'id':id,'title':title,'name':title,'release_date':date,'first_air_date':date} for id,title,date in titles]}
    m.tmdb_json=ranked
    for section in ('movies','tv'):
        for sort in ('', '&sort=newest', '&sort=oldest', '&sort=invalid'):
            page=client.get('/collector/media/search?section='+section+'&q=Example'+sort+'&fragment=1').get_data(as_text=True)
            assert page.index('Relevant older work') < page.index('New less relevant work') < page.index('Last provider result')
            assert 'name="sort"' not in page and 'Neueste zuerst' not in page
print('OK: cleaned/short title fallback, retained EAN/DVD, deduplicated provider requests, offline bound and visible product alternatives')
