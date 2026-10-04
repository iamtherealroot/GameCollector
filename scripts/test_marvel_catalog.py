#!/usr/bin/env python3
"""Marvel catalogues works, not inventory, and preserves multiple series."""
import importlib, json, os, sys, tempfile
from pathlib import Path
from flask import g
from flask.testing import FlaskClient
from werkzeug.security import generate_password_hash
from sqlalchemy import event

sandbox=tempfile.TemporaryDirectory(prefix="bibo-marvel-")
os.environ.update(DATABASE_URL="sqlite:///"+str(Path(sandbox.name)/"test.db"),ADMIN_USERNAME="marvel-admin",ADMIN_PASSWORD="pass")
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
m=importlib.import_module("app.app");m.app.config["TESTING"]=True
from app.marvel_catalog import CATALOG, match_movie
from app.mcu_order import entry_order, RELEASE_TITLES, STORY_TITLES
class Client(FlaskClient):
    def open(self,*a,**kw):g.pop("_login_user",None);return super().open(*a,**kw)
m.app.test_client_class=Client
with m.app.app_context():
    owner=m.shared_collection_user()
    mcu=[e for e in CATALOG if e['branch']=='MCU']
    assert [e['title'] for e in sorted(mcu,key=lambda e:entry_order(e,'release')[0])]==RELEASE_TITLES
    chronology=sorted(mcu,key=lambda e:entry_order(e,'timeline')[0])
    assert [e['title'] for e in chronology[:36]]==STORY_TITLES
    assert all(entry_order(e,'timeline')[0][0]==1 for e in chronology[36:])
    assert len(CATALOG)==170 and len({e["key"] for e in CATALOG})==170
    assert sum(e["branch"]=="MCU" for e in CATALOG)==38
    assert m.BiboWork.query.filter_by(media_kind="movies").count()==170
    assert m.BiboCopy.query.count()==0 and m.CollectorItem.query.count()==0
    ids=[]
    for title,year,series,mid in [("Iron Man",2008,"Iron Man","1726"),("Spider-Man",2002,"Spider-Man","557"),("Guardians of the Galaxy",2014,"Guardians of the Galaxy","118340")]:
        row=m.CollectorItem(user_id=owner.id,category="movies",title=title,release_year=year,media_type="Blu-ray",estimated_value_eur=10,
                            metadata_json=json.dumps({"collection_name":series,"tmdb_id":mid,"de_physical_release_status":"physical"}))
        m.db.session.add(row);m.db.session.flush();ids.append(row.id)
    foreign=m.User(username="foreign-marvel",password_hash=generate_password_hash("pass"),is_system=True)
    m.db.session.add(foreign);m.db.session.flush()
    m.db.session.add(m.CollectorItem(user_id=foreign.id,category="movies",title="Iron Man 2",release_year=2010,notes="PRIVATE",metadata_json='{"collection_name":"Iron Man"}'))
    m.db.session.commit();m.refresh_bibo_registry()
    assert m.CollectorItem.query.count()==4
    assert m.BiboWork.query.filter_by(media_kind="movies").count()==170,"No duplicate catalog work for owned films"
    for item_id in ids:
        edition=m.BiboEdition.query.filter_by(source_kind="collector",source_id=str(item_id)).one()
        memberships={r.series.title for r in edition.work.series_memberships if r.active and r.series.active}
        title=m.db.session.get(m.CollectorItem,item_id).title
        assert "Marvel" in memberships and title in memberships,(title,memberships)
        if title!="Spider-Man":assert "Marvel Cinematic Universe" in memberships
    counts=(m.BiboWork.query.count(),m.BiboSeries.query.count(),m.BiboSeriesMembership.query.count(),m.BiboCopy.query.count())
    m.refresh_bibo_registry()
    assert counts==(m.BiboWork.query.count(),m.BiboSeries.query.count(),m.BiboSeriesMembership.query.count(),m.BiboCopy.query.count())
    assert match_movie(m.CollectorItem(title="Fantastic Four",category="movies"),{},m._match_key) is None
    assert match_movie(m.CollectorItem(title="Fantastic Four",category="movies",release_year=2015),{},m._match_key)["year"]==2015
    assert match_movie(m.CollectorItem(title="My renamed film",category="movies",release_year=2014),{"original_title":"Guardians of the Galaxy"},m._match_key)["series"]=="Guardians of the Galaxy"
    client=m.app.test_client();client.post("/login",data={"username":"marvel-admin","password":"pass"})
    def no_network(*a,**kw):raise AssertionError("Catalogue must use local data")
    m.urlopen=no_network;m.tmdb_json=lambda *a,**kw:{}
    page=client.get("/collector/movies/marvel?series=Iron+Man&branch=MCU").get_data(as_text=True)
    assert "3 Katalogtitel · 1 physisch vorhanden" in page
    assert "PRIVATE" not in page and "Meine Exemplare öffnen" in page and "Exemplar anlegen" in page
    assert 'release_year=2010' in page
    timeline=client.get('/collector/movies/marvel?branch=MCU&order=timeline').get_data(as_text=True)
    assert timeline.index('<h2>Captain America: The First Avenger')<timeline.index('<h2>Iron Man ')
    assert 'Weitere MCU-Universen' in timeline
    remembered=client.get('/collector/movies/marvel?branch=MCU').get_data(as_text=True)
    assert 'value="timeline" selected' in remembered
    release=client.get('/collector/movies/marvel?branch=MCU&order=release').get_data(as_text=True)
    assert release.index('<h2>Iron Man ')<release.index('<h2>Captain America: The First Avenger')
    marvel=client.get("/collector/movies/marvel").get_data(as_text=True)
    assert "134 Katalogtitel · 3 physisch vorhanden" not in marvel # default excludes 36 shorts AND one serial
    assert "133 Katalogtitel · 3 physisch vorhanden" in marvel
    upcoming=client.get("/collector/movies/marvel?branch=Angek%C3%BCndigt").get_data(as_text=True)
    assert "3 Katalogtitel · 0 physisch vorhanden" in upcoming and "Exemplar anlegen" not in upcoming
    all_titles=client.get("/collector/movies/marvel?branch=all&page=5").get_data(as_text=True)
    assert "161–170 von 170" in all_titles
    overview=client.get("/collector/collections?type=movies").get_data(as_text=True)
    assert "Marvel" in overview and "Guardians of the Galaxy" in overview
    client.get("/library")
    assert sum(copy.effective_value_eur or 0 for copy in m.BiboCopy.query.filter_by(owner_id=owner.id,active=True).all())==30
    # Cheap repeated catalogue reads: no writes and no provider calls.
    writes=[]
    def count(conn,cursor,statement,params,context,many):
        if statement.lstrip().split()[0].upper() in {"INSERT","UPDATE","DELETE"}:writes.append(statement)
    event.listen(m.db.engine,"before_cursor_execute",count)
    client.get("/collector/movies/marvel")
    event.remove(m.db.engine,"before_cursor_execute",count)
    assert not writes,writes
print("OK: 170 local catalog works, 38 MCU films, own+Marvel+MCU membership, no fake inventory, deduplication, aliases/year ambiguity, privacy and read caching")
