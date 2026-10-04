#!/usr/bin/env python3
"""Automatic enrichment is asynchronous, one-shot, scoped and additive."""
import importlib, json, os, sys, tempfile
from pathlib import Path
from flask import g, request, redirect
from flask.testing import FlaskClient
from flask_login import login_required
from werkzeug.security import generate_password_hash

sandbox = tempfile.TemporaryDirectory(prefix="bibo-auto-metadata-")
os.environ.update(DATABASE_URL="sqlite:///" + str(Path(sandbox.name)/"test.db"), ADMIN_USERNAME="auto-admin", ADMIN_PASSWORD="pass")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
m = importlib.import_module("app.app")
m.app.config["TESTING"] = True
class Client(FlaskClient):
    def open(self, *a, **kw):
        g.pop("_login_user", None)
        return super().open(*a, **kw)
m.app.test_client_class = Client

@m.app.post("/_test/new/<kind>")
@login_required
def fixture(kind):
    owner = m.active_collection_user_id()
    console = m.Console.query.first()
    if kind == "game":
        game = m.Game(title="Fixture Game", console_id=console.id)
        m.db.session.add(game);m.db.session.flush()
        row = m.CollectionItem(user_id=owner, game_id=game.id)
    elif kind == "hardware":
        model = m.HardwareModel(name="Fixture Hardware", console_id=console.id)
        m.db.session.add(model);m.db.session.flush()
        row = m.HardwareItem(user_id=owner, hardware_model_id=model.id)
    else:
        row = m.AccessoryItem(user_id=owner, name="Fixture Accessory", barcode="4000000000004")
    m.db.session.add(row);m.db.session.commit()
    return redirect("/")

with m.app.app_context():
    client=m.app.test_client();client.post("/login",data={"username":"auto-admin","password":"pass"})
    calls=[]
    def tmdb(path, params=None):
        calls.append(path)
        if path.startswith("search/"):
            return {"results":[{"id":42,"title":"Fixture Series" if path.endswith("tv") else "Fixture Film","name":"Fixture Series","release_date":"2020-01-01"}]}
        return {"id":42,"original_title":"Original","overview":"Story","release_date":"2020-01-01","genres":[{"name":"Drama"}],"credits":{"crew":[{"job":"Director","name":"Director"}]}}
    m.tmdb_json=tmdb
    m.openlibrary_search_books=lambda **kw:[{"id":"/works/book","title":"Fixture Book","isbn":"9780000000001","year":2021,"author":"Author","page_count":123,"cover_url":"book-cover"}]
    m.musicbrainz_search_releases=lambda *a,**kw:[{"id":"album","title":"Fixture Music","year":2022,"artist":"Artist","track_count":12,"cover_url":"album-cover"}]
    m.tcgdex_search=lambda title:[{"id":"set-1","name":"Fixture Card","set_name":"Fixture Set","number":"1","rarity":"Rare","image":"card-cover","tcg":"Pokémon","language":"de","provider":"tcgdex"}]
    m.scryfall_search=lambda *a,**kw:[];m.ygopro_search=lambda *a,**kw:[]
    m.lookup_barcode_external=lambda code:[{"name":"Product","barcode":code,"publisher":"Brand","cover_url":"product-cover","source":"Barcode","source_id":code}]
    m.upcitemdb_title_search=lambda title,**kw:[{"name":title,"publisher":"Brand","cover_url":"product-cover","source":"UPCitemdb","source_id":"product"}]
    m._metadata_candidates=lambda title, platform, **kw:([{"name":title,"platform":platform,"platform_match":True,"publisher":"Publisher","cover_url":"game-cover","year":2023,"source":"Fixture"}],"ok")
    def no_network(*a,**kw):raise AssertionError("Unexpected real provider request")
    m.urlopen=no_network

    for category,title in [("movies","Fixture Film"),("tv","Fixture Series"),("books","Fixture Book"),("music","Fixture Music"),("cards","Fixture Card"),("custom","Fixture Custom")]:
        data={"category":category,"title":title,"notes":"My notes","condition":"Good","purchase_price_eur":"9.99"}
        if category=="cards":data.update(tcg_game="Pokémon",card_set="Fixture Set",card_number="1")
        before=len(calls)
        response=client.post("/add/media",data=data)
        assert response.status_code==302,(category,response.status_code,response.get_data(as_text=True)[:500])
        row=m.CollectorItem.query.filter_by(title=title).one()
        assert m.collector_metadata(row)["de_physical_release_status"]=="physical"
        assert len(calls)==before,"Saving must not wait for TMDB"
        page=client.get(response.location).get_data(as_text=True)
        assert "data-auto-metadata-jobs" in page
        url=f"/metadata/auto/media/{row.id}"
        result=client.post(url).get_json()
        assert result["status"]=="enriched",(category,result)
        m.db.session.expire_all();row=m.CollectorItem.query.filter_by(title=title).one()
        assert row.title==title and row.notes=="My notes" and row.purchase_price_eur==9.99
        assert m.collector_metadata(row)["de_physical_release_status"]=="physical"
        assert client.post(url).get_json()["status"]=="skipped"
        if category in {"movies","tv"}:
            assert m.collector_metadata(row)["overview"]=="Story"
            assert "TMDB-Metadaten aktualisieren" in client.get(response.location).get_data(as_text=True)
        elif category=="books":assert m.collector_metadata(row)["author"]=="Author"
        elif category=="music":assert m.collector_metadata(row)["artist"]=="Artist"
        elif category=="cards":assert row.card_rarity=="Rare"
        else:assert row.cover_url=="product-cover"

    for kind,model in [("game",m.CollectionItem),("hardware",m.HardwareItem),("accessory",m.AccessoryItem)]:
        assert client.post("/_test/new/"+kind).status_code==302
        row=model.query.order_by(model.id.desc()).first()
        result=client.post(f"/metadata/auto/{kind}/{row.id}").get_json()
        assert result["status"]=="enriched",(kind,result)
        m.db.session.expire_all();row=m.db.session.get(model,row.id)
        if kind=="game":assert row.game.publisher=="Publisher"
        elif kind=="hardware":assert row.model.reference_image=="product-cover"
        else:assert row.manufacturer=="Brand"

    # Existing values and copy details are never overwritten, including metadata.
    client.post("/add/media",data={"category":"movies","title":"Fixture Film","cover_url":"manual-cover","release_year":"2020","notes":"Keep"})
    row=m.CollectorItem.query.order_by(m.CollectorItem.id.desc()).first()
    meta=m.collector_metadata(row);meta["overview"]="Manual description";row.metadata_json=json.dumps(meta);m.db.session.commit()
    client.post(f"/metadata/auto/media/{row.id}")
    m.db.session.refresh(row)
    assert row.cover_url=="manual-cover" and m.collector_metadata(row)["overview"]=="Manual description"
    # Failure leaves the newly saved row and does not repeat on subsequent pages.
    m.tmdb_json=lambda *a,**kw:(_ for _ in ()).throw(TimeoutError("provider offline"))
    client.post("/add/media",data={"category":"movies","title":"Offline Film"})
    row=m.CollectorItem.query.filter_by(title="Offline Film").one();url=f"/metadata/auto/media/{row.id}"
    assert client.post(url).get_json()["status"]=="unavailable"
    assert m.db.session.get(m.CollectorItem,row.id) is not None
    assert client.post(url).get_json()["status"]=="skipped"
    # No queued job can mutate an old or foreign entry.
    assert client.post("/metadata/auto/media/999999").get_json()["status"]=="skipped"
    # Digital and explicit unknown remain valid overrides of the default.
    for status,ownership in [("unknown","physical"),("physical","digital")]:
        title="Status "+ownership
        client.post("/add/media",data={"category":"books","title":title,"de_physical_release_status":status,"ownership_format":ownership})
        row=m.CollectorItem.query.filter_by(title=title).one()
        assert m.collector_metadata(row)["de_physical_release_status"]==("digital" if ownership=="digital" else "unknown")
    assert "option value=\"physical\" selected" in client.get("/add/media?category=books").get_data(as_text=True)
    # A forged queue still cannot enrich another owner's row.
    foreign=m.User(username="foreign-auto",password_hash="unused",is_system=True)
    reader=m.User(username="reader-auto",password_hash=generate_password_hash("pass"),role="viewer")
    m.db.session.add_all([foreign,reader]);m.db.session.flush()
    private=m.CollectorItem(user_id=foreign.id,category="books",title="Private Book")
    m.db.session.add(private);m.db.session.commit()
    with client.session_transaction() as sess:
        sess["auto_metadata_pending"]=[{"kind":"media","id":private.id,"owner":m.shared_collection_user().id,"actor":m.User.query.filter_by(username="auto-admin").one().id}]
    assert client.post(f"/metadata/auto/media/{private.id}").get_json()["status"]=="skipped"
    viewer=m.app.test_client();viewer.post("/login",data={"username":"reader-auto","password":"pass"})
    assert viewer.post(f"/metadata/auto/media/{private.id}").status_code==403
print("OK: all media adapters, additive metadata, async save, queue ownership, one-shot, failures, manual TMDB button and physical defaults")
