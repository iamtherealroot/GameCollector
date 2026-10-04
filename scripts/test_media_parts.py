#!/usr/bin/env python3
"""Physical parts can be selected before saving, including retry and digital paths."""
import importlib
import os
from html.parser import HTMLParser
from pathlib import Path
import sys
import tempfile

sandbox=tempfile.TemporaryDirectory(prefix='bibo-media-parts-')
os.environ.update(DATABASE_URL='sqlite:///'+str(Path(sandbox.name)/'test.db'),ADMIN_USERNAME='parts-admin',ADMIN_PASSWORD='test-pass')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
m=importlib.import_module('app.app');m.app.config['TESTING']=True
keys=('has_original_packaging','disc_present','booklet_present','slipcover_present','bonus_disc_present','sealed')
class Inputs(HTMLParser):
    def __init__(self,text):
        super().__init__();self.checks={};self.feed(text)
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='input' and attrs.get('type')=='checkbox' and attrs.get('name') in keys:
            self.checks[attrs['name']]='checked' in attrs
with m.app.app_context():
    client=m.app.test_client();assert client.post('/login',data={'username':'parts-admin','password':'test-pass'}).status_code==302
    for category,media in [('movies','Blu-ray'),('tv','DVD'),('music','CD')]:
        for advanced in ('','&advanced=1'):
            response=client.get('/add/media?category='+category+advanced)
            assert response.status_code==200
            page=response.get_data(as_text=True)
            assert ('name="purchase_date"' in page)==bool(advanced)
            assert ('name="purchase_price_eur"' in page)==bool(advanced)
            assert '>Versiegelt</option>' in page
            if advanced:
                assert '>Kauf</button>' not in page and 'data-step="5"' not in page
                assert page.index('name="completeness"') < page.index('data-copy-parts')
                assert '<details class="media-purchase-details"' in page
            assert Inputs(response.get_data(as_text=True)).checks=={key:key!='sealed' for key in keys}
        form=dict(category=category,title='Parts '+category,media_type=media,ownership_format='physical',copy_parts_submitted='1',has_original_packaging='1',disc_present='1',slipcover_present='1')
        bad=client.post('/add/media',data={**form,'purchase_price_eur':'invalid'})
        assert bad.status_code==400
        advanced_bad=client.post('/add/media',data={**form,'media_intake_mode':'advanced','purchase_price_eur':'invalid','purchase_date':'2026-10-04'})
        assert advanced_bad.status_code==400
        advanced_page=advanced_bad.get_data(as_text=True)
        assert 'id="media-wizard"' in advanced_page and 'value="invalid"' in advanced_page and 'value="2026-10-04"' in advanced_page
        assert Inputs(bad.get_data(as_text=True)).checks=={key:key in form for key in keys}
        assert client.post('/add/media',data=form).status_code==302
        row=m.CollectorItem.query.filter_by(title=form['title']).one()
        meta=m.collector_metadata(row)
        assert {key:meta[key] for key in keys}=={key:key in form for key in keys}
        assert client.post('/add/media',data={**form,'title':'Complete '+category,**dict.fromkeys(keys,'1')}).status_code==302
        row=m.CollectorItem.query.filter_by(title='Complete '+category).one()
        assert all(m.collector_metadata(row)[key] is True for key in keys)
        assert client.post('/add/media',data={**form,'title':'Digital '+category,'ownership_format':'digital',**dict.fromkeys(keys,'1')}).status_code==302
        row=m.CollectorItem.query.filter_by(title='Digital '+category).one()
        assert not any(key in m.collector_metadata(row) for key in keys)
print('OK: physical parts defaults, simple/wizard forms, explicit unchecked save, all checked save, validation retry and digital exclusion')
