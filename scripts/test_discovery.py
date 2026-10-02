#!/usr/bin/env python3
"""Regression test for Bibo 4.6 discovery and questionnaire hand-off."""
import html
import importlib
import os
import re
import sys
import tempfile
from pathlib import Path

_sandbox = tempfile.TemporaryDirectory(prefix="bibo-discovery-")
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(_sandbox.name) / "discovery.db")
os.environ["ADMIN_USERNAME"] = "discovery-admin"
os.environ["ADMIN_PASSWORD"] = "discovery-password"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

module = importlib.import_module("app.app")


with module.app.app_context():
    owner = module.shared_collection_user()
    seed = module.CollectorItem(
        user_id=owner.id, category="movies", title="Ausgangsfilm", media_type="Blu-ray",
        external_source="TMDB", external_id="100",
        metadata_json='{"tmdb_id":"100","de_physical_release_status":"physical"}',
    )
    owned = module.CollectorItem(
        user_id=owner.id, category="movies", title="Schon vorhanden", media_type="DVD",
        external_source="TMDB", external_id="200", metadata_json='{"tmdb_id":"200"}',
    )
    module.db.session.add_all([seed, owned])
    module.db.session.commit()
    seed_id = seed.id

    def fake_tmdb(path, params=None):
        if path == "movie/333":
            return {"id": 333, "title": "Boxfilm Drei", "release_date": "2023-03-03"}
        return {"results": [
            {"id": 200, "title": "Schon vorhanden", "release_date": "2020-01-01", "poster_path": "/old.jpg"},
            {"id": 201, "title": "Neue Empfehlung", "release_date": "2024-02-03", "poster_path": "/new.jpg"},
        ]}
    module.tmdb_json = fake_tmdb

    client = module.app.test_client()
    login = client.post("/login", data={"username": "discovery-admin", "password": "discovery-password"})
    assert login.status_code in {302, 303}
    response = client.get(f"/discover?type=movies&seed={seed_id}")
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Neue Empfehlung" in page
    assert page.count("Schon vorhanden") == 1, "Vorhandener Titel darf nur als Ausgangstitel, nicht als Empfehlung erscheinen"
    assert "image.tmdb.org" in page and "DE-Status ungeklärt" in page
    match = re.search(r'href="(/discover/preview/[^"]+)"', page)
    assert match, page[:1000]
    preview_path = html.unescape(match.group(1))
    token = preview_path.rsplit("/", 1)[-1]
    preview = client.get(preview_path)
    assert preview.status_code == 200 and "Neue Empfehlung" in preview.get_data(as_text=True)

    wishlist = client.post("/discover/action", data={"token": token, "action": "wishlist"})
    assert wishlist.status_code in {302, 303}
    copy = module.BiboCopy.query.filter_by(source_kind="discovery", status="wishlist", active=True).first()
    assert copy and copy.edition.work.title == "Neue Empfehlung"
    module.refresh_bibo_registry()
    module.db.session.expire_all()
    assert module.BiboCopy.query.filter_by(id=copy.id, active=True).first(), "Entdeckungs-Wunschliste ging beim Registerabgleich verloren"
    assert client.get("/library").status_code == 200

    add = client.post("/discover/action", data={"token": token, "action": "add"})
    assert add.status_code in {302, 303} and add.headers["Location"].endswith("/add/media")
    wizard = client.get(add.headers["Location"]).get_data(as_text=True)
    assert "Neue Empfehlung" in wizard and 'id="media-type-select"' in wizard
    assert '<input name="media_type"' not in wizard

    strip = client.get(f"/discover/strip/movies/{seed_id}")
    strip_page = strip.get_data(as_text=True)
    assert strip.status_code == 200 and "Neue Empfehlung" in strip_page
    assert "Schon vorhanden" in strip_page and "Im Besitz" in strip_page
    coverage = client.post(f"/collector/item/{seed_id}/coverage", data={
        "action": "tmdb_add", "tmdb_links": "https://www.themoviedb.org/movie/333-boxfilm-drei",
    })
    assert coverage.status_code in {302, 303}
    linked = module.ReleaseCoverage.query.filter_by(source_id=str(seed_id), target_key="movie:tmdb:333").first()
    assert linked and linked.target_title == "Boxfilm Drei" and linked.origin == "tmdb"
    assert "333" in module.collector_metadata(module.db.session.get(module.CollectorItem, seed_id)).get("included_tmdb_ids", [])
    removed = client.post(f"/collector/item/{seed_id}/coverage", data={"coverage_lines": ""})
    assert removed.status_code in {302, 303}
    refreshed_seed = module.db.session.get(module.CollectorItem, seed_id)
    assert "included_tmdb_ids" not in module.collector_metadata(refreshed_seed)
    module.sync_inferred_release_coverages(refreshed_seed)
    assert not module.ReleaseCoverage.query.filter_by(source_id=str(seed_id), target_key="movie:tmdb:333").first()
    review_response = client.post(f"/review/collector/{seed_id}", data={
        "overall_rating": "9", "dimension_1": "8", "dimension_2": "9", "dimension_3": "10",
        "dimension_4": "8", "dimension_5": "7", "review_title": "Sehr sehenswert",
        "review_text": "Meine ausführliche Bewertung.", "pros": "Starke Figuren", "cons": "Kleine Längen",
        "recommendation": "yes", "favorite": "1", "spoiler": "1", "consumed_at": "2026-09-28",
    })
    assert review_response.status_code in {302, 303}
    personal = module.PersonalReview.query.filter_by(source_kind="collector", source_id=str(seed_id)).first()
    assert personal and personal.overall_rating == 9 and personal.dimension_3 == 10 and personal.favorite
    detail_page = client.get(f"/collector/item/{seed_id}").get_data(as_text=True)
    assert "Sehr sehenswert" in detail_page and "9<small>/10</small>" in detail_page
    print("OK: Empfehlungen sind klickbar, dedupliziert, dauerhaft und führen vorausgefüllt in den Fragenkatalog")
