#!/usr/bin/env python3
"""Offline regression fixtures for mixed offers and price jumps.

Load the actual pricing functions without starting Flask or making network calls.
"""
import ast
import json
import re
import statistics
import unicodedata
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS
from urllib.parse import urlencode

source = Path(__file__).resolve().parents[1] / 'app/app.py'
names = {'_match_key', 'value_kind_for_item', 'condition_factor',
         'game_offer_matches_completeness', 'game_offer_matches_variant', 'game_price_jump_pending',
         'store_auto_valuation', 'ebay_offer_valuation', 'auto_value_item'}
tree = ast.parse(source.read_text())
env = dict(json=json, re=re, statistics=statistics, unicodedata=unicodedata,
           datetime=datetime, timedelta=timedelta, timezone=timezone, urlencode=urlencode)
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef)
                            and n.name in names], type_ignores=[]), str(source), 'exec'), env)
env['derive_completeness'] = lambda media, box, manual, sealed: 'Sealed' if sealed else ('CIB' if box and manual else 'Loose' if not box and not manual else 'Incomplete')
env['canonical_franchise_name'] = lambda _: ''
env['infer_franchise_name'] = lambda _: ''
env['normalize_series_title'] = lambda s: s
env['_search_text'] = env['_match_key']
env['CURATED_SERIES'] = {}
env['ebay_credentials'] = lambda: {'client_id':'fixture', 'client_secret':'fixture'}
env['ebay_enrich_candidates'] = lambda rows, limit: rows


def copy(box=False, manual=False, sealed=False, previous=50):
    return NS(id=None, game_id=1, game=NS(title='Pokémon Gelb', console=NS(name='Game Boy'),
              barcode=None, product_code=None, edition='Standard', franchise='', region='PAL'),
              ownership_format='physical', media_present=True, box_present=box, manual_present=manual,
              sealed=sealed, media_condition=8, box_condition=8,
              auto_value_eur=previous, auto_value_condition='CIB' if box and manual else 'Loose',
              auto_value_pending_json=None, auto_value_updated_at=datetime(2026, 10, 1, tzinfo=timezone.utc))


class PricingTests(unittest.TestCase):
    def test_regions_and_editions(self):
        item=copy();match=env['game_offer_matches_variant']
        self.assertTrue(match(item,'Pokémon Gelb PAL nur Modul'))
        for title in ['Pokémon Gelb USA NTSC-U nur Modul','Pokémon Gelb JPN nur Modul','Pokémon Gelb Collector Edition nur Modul']:
            self.assertFalse(match(item,title))
        item.game.edition='Steelbook'
        self.assertFalse(match(item,'Pokémon Gelb PAL nur Modul'))
        self.assertTrue(match(item,'Pokémon Gelb Steelbook PAL nur Modul'))
    def setUp(self):
        env["utc_now"] = lambda: datetime(2026,10,2,tzinfo=timezone.utc)
        env["db"] = NS(session=NS(add=lambda value: None))

    def test_completeness_groups(self):
        match = env['game_offer_matches_completeness']
        for item, accepted in [(copy(), 'nur Modul'), (copy(True,True),'OVP mit Anleitung komplett'),
                               (copy(sealed=True),'sealed'), (copy(True,False),'OVP ohne Anleitung')]:
            self.assertTrue(match(item, 'Pokémon Gelb '+accepted))
        for suffix in ['OVP komplett', 'sealed', 'graded WATA', 'nur OVP', 'Repro loose', '', 'OVP ohne Anleitung']:
            self.assertFalse(match(copy(), 'Pokémon Gelb '+suffix), suffix)
        self.assertFalse(match(copy(True,True), 'Pokémon Gelb nur Modul'))
        self.assertFalse(match(copy(True,True), 'Pokémon Gelb OVP ohne Anleitung'))
        self.assertFalse(match(copy(sealed=True), 'Pokémon Gelb OVP komplett'))

    def test_mixed_market_is_not_multiplied(self):
        rows = []
        for label, prices in [('nur Modul',[45,48,50,52,55]), ('OVP komplett',[180,200,220,240,260]),
                              ('sealed',[400,500,600,700,800]), ('Rot nur Modul',[999]*5)]:
            for p in prices:
                rows.append(dict(id=str(len(rows)),name='Pokémon '+('' if label.startswith('Rot') else 'Gelb ')+label,
                                 price=p,shipping=0,currency='EUR'))
        env['ebay_search_items'] = lambda query, limit: (rows,'ok')
        for item, expected in [(copy(),50),(copy(True,True),220),(copy(sealed=True),600)]:
            value, prices, status = env['ebay_offer_valuation'](item)
            self.assertEqual(value['value'],expected)
            self.assertEqual(prices['offer_count'],5)
        env['ebay_search_items'] = lambda query, limit: (rows[:2],'ok')
        self.assertEqual(env['ebay_offer_valuation'](copy())[2],'ebay_too_few_results')

    def test_jump_requires_later_confirmation(self):
        item = copy(); now=datetime(2026,10,2,tzinfo=timezone.utc)
        guard=env['game_price_jump_pending']; price={'source':'eBay-Angebote'}
        v=lambda value: {'value':value,'condition':'Loose'}
        self.assertTrue(guard(item,v(150),price,now))
        pending=item.auto_value_pending_json
        self.assertTrue(guard(item,v(150),price,now+timedelta(hours=1)))
        self.assertEqual(pending,item.auto_value_pending_json)
        self.assertFalse(guard(item,v(151),price,now+timedelta(hours=24)))
        self.assertEqual(item.auto_value_eur,50)
        self.assertIsNone(item.auto_value_pending_json)
        self.assertTrue(guard(item,v(150),price,now))
        self.assertFalse(guard(item,v(51),price,now+timedelta(days=1)))
        self.assertIsNone(item.auto_value_pending_json)

    def test_sources_cannot_confirm_each_other_and_pending_expires(self):
        item=copy(); now=datetime(2026,10,2,tzinfo=timezone.utc)
        guard=env['game_price_jump_pending']; v={'value':150,'condition':'Loose'}
        self.assertTrue(guard(item,v,{'source':'eBay'},now))
        self.assertTrue(guard(item,v,{'source':'PrixRetro'},now+timedelta(days=1)))
        self.assertTrue(guard(item,v,{'source':'PrixRetro'},now+timedelta(days=10)))
        for bad in [0,-1,float('nan'),float('inf')]:
            self.assertTrue(guard(item,dict(v,value=bad),{'source':'eBay'},now))

    def test_pending_writes_no_price_history_or_activity(self):
        records=[]; env['db']=NS(session=NS(add=records.append))
        now=datetime(2026,10,2,tzinfo=timezone.utc);env['utc_now']=lambda: now
        item=copy(); updated=item.auto_value_updated_at
        self.assertFalse(env['store_auto_valuation'](item,{'value':150,'condition':'Loose'},{'source':'eBay'}))
        self.assertEqual(records,[])
        self.assertEqual(item.auto_value_eur,50)
        self.assertEqual(item.auto_value_updated_at,updated)

    def test_pending_does_not_fall_through_to_another_source(self):
        item=copy();env['game_is_physical_candidate']=lambda game:True
        env['ebay_offer_valuation']=lambda item: ({'value':150,'condition':'Loose'}, {'source':'eBay'}, 'ok')
        env['prixretro_lookup']=lambda game: self.fail('Pending eBay jump must not trigger fallback')
        self.assertEqual(env['auto_value_item'](item),(False,'price_jump_pending'))

    def test_schema_and_price_center_include_pending(self):
        text=source.read_text()
        self.assertIn('auto_value_pending_json = db.Column(db.Text)',text)
        self.assertIn('"auto_value_pending_json": "TEXT"',text)
        self.assertIn('message if status_raw == "price_jump_pending"',text)

if __name__ == '__main__':
    unittest.main()
