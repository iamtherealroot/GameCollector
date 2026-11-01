#!/usr/bin/env python3
"""Decks must never set individual card values, including old stored quotes."""
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

sandbox=tempfile.TemporaryDirectory(prefix='bibo-card-prices-')
os.environ.update(DATABASE_URL='sqlite:///'+str(Path(sandbox.name)/'test.db'),ADMIN_USERNAME='card-admin',ADMIN_PASSWORD='pass')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
m=importlib.import_module('app.app');m.app.config['TESTING']=True
with m.app.app_context():
    owner=m.shared_collection_user()
    card=m.CollectorItem(user_id=owner.id,category='cards',title='Roter Apparat',tcg_game='Yu-Gi-Oh!',card_set="Yugi's Legendary Decks",card_number='YGLD-DEB18',card_language='Deutsch',card_variant='Normal',card_rarity='Common',condition='Near Mint',barcode='4012927000000',estimated_value_eur=2.98,auto_value_eur=66.27,auto_value_low_eur=59,auto_value_high_eur=70,auto_value_source='eBay-Angebote')
    m.db.session.add(card);m.db.session.commit()
    def hit(name,price=2,id='one'):
        return {'name':name,'price':price,'currency':'EUR','shipping':0,'id':id}
    valid='Roter Apparat YGLD-DEB18 Common NM Deutsch Einzelkarte'
    assert m.card_offer_matches(card,hit(valid))
    assert m.card_offer_matches(card,hit(valid+" Yugi's Legendary Decks"))
    for title in ["Yu-Gi-Oh Yugi's Legendary Decks komplett 66,27 Euro",'Gelber Apparat YGLD-DEB19 Common NM Deutsch',valid+' Deck komplett',valid+' Booster',valid+' Playset 3x',valid+' PSA 10',valid.replace('DEB18','ENB18'),valid.replace('DEB18','DEB19'),valid+' English',valid+' damaged',valid+' YGLD-DEB19',valid+' Proxy',valid+' 10x',valid+' 100 Karten',valid+' Auswahl',valid.replace('Common','Ultra Rare')]:
        assert not m.card_offer_matches(card,hit(title)),title
    queries=[]
    offers=[hit("Yu-Gi-Oh Yugi's Legendary Decks komplett",66.27,'deck'),hit(valid,1.5,'a'),hit(valid,2.5,'b'),hit(valid,100,'a')]
    m.ebay_search_items=lambda q,limit:(queries.append(q) or offers,'ok')
    value,low,high,status=m.collector_ebay_valuation(card)
    assert (value,low,high,status)==(2.0,1.5,2.5,'ok')
    assert queries and all(card.card_number in q and card.barcode not in q for q in queries)
    assert len(m.collector_metadata(card)['card_ebay_evidence'])==2
    # Same listing twice is insufficient evidence, even if the prices differ.
    m.ebay_search_items=lambda *a,**kw:([hit(valid,1.5,'a'),hit(valid,2.5,'a')],'ok')
    assert m.collector_ebay_valuation(card)[0] is None
    m.ebay_search_items=lambda *a,**kw:([hit("Yugi's Legendary Decks komplett",66.27,'x'),hit("Yugi's Legendary Decks komplett",66.27,'y')],'ok')
    assert m.collector_ebay_valuation(card)[0] is None
    original=card.card_number;card.card_number='12345678'
    assert m.collector_ebay_valuation(card)[3]=='card_identity_missing'
    card.card_number=original;card.card_grade='PSA 10'
    assert m.collector_ebay_valuation(card)[3]=='card_grade_unsupported'
    card.card_grade='raw'
    # Old quotes do not affect current totals, but manual estimates/fixes survive.
    assert m.collector_effective_value(card)==2.98
    card.fixed_value_eur=7.0;assert m.collector_effective_value(card)==7.0
    assert m.repair_card_ebay_valuations()==1
    assert card.auto_value_eur is None and card.fixed_value_eur==7.0 and card.estimated_value_eur==2.98
    assert m.collector_metadata(card)['unverified_card_ebay_values'][-1]['value']==66.27
    assert m.repair_card_ebay_valuations()==0
    m.record_collector_price(card,2.98,66.27,59,70,'eBay-Angebote');m.db.session.commit()
    with m.app.test_request_context('/bewertungen'):
        assert not m.collection_market_movement('latest',[],[],[],[card])['winners']
    # A fresh exact result gets provenance; changing printing invalidates it.
    card.fixed_value_eur=None
    m.ebay_search_items=lambda *a,**kw:([hit(valid,1.5,'a'),hit(valid,2.5,'b')],'ok')
    client=m.app.test_client();client.post('/login',data={'username':'card-admin','password':'pass'})
    assert client.post(f'/collector/item/{card.id}/value').status_code==302
    assert card.auto_value_eur==2.0 and card.auto_value_source==m.CARD_EBAY_SOURCE
    assert m.collector_effective_value(card)==2.0
    card.card_number='YGLD-DEB19'
    assert m.collector_effective_value(card)==2.98
    assert m.invalidate_unverified_card_ebay_value(card)
    # Other media and provider-native Pokémon/MTG values keep their own paths.
    book=m.CollectorItem(category='books',title='Book',auto_value_eur=12,auto_value_source='eBay-Angebote')
    assert m.collector_effective_value(book)==12
    pokemon=m.CollectorItem(category='cards',title='Pikachu',tcg_game='Pokémon')
    assert m.collector_ebay_valuation(pokemon)[3]=='pokecollector_only'
print('OK: exact printing/name/language, no decks/bundles/grades/wrong rarity, distinct listings, legacy quote quarantine and guarded new valuations')
