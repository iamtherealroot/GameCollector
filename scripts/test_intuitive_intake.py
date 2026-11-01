#!/usr/bin/env python3
"""A recognized PS5 barcode reaches the copy form and can be saved."""
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile

sandbox = tempfile.TemporaryDirectory(prefix="bibo-intake-")
os.environ.update(DATABASE_URL="sqlite:///" + str(Path(sandbox.name) / "test.db"),
                  ADMIN_USERNAME="intake-admin", ADMIN_PASSWORD="test-pass")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
m = importlib.import_module("app.app")
m.app.config["TESTING"] = True

with m.app.app_context():
    title = "Tiny Tinas Wonderlands Next Level Edition Sony Playstation 5 PS5 Spiel"
    code = "4000000000087"
    m.lookup_barcode_external = lambda code: []
    m.ebay_search_gtin = lambda code, limit: ([{"name": title, "source_id": "fixture-ps5"}], "ok")
    m.tmdb_json = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Games must not query TMDB"))
    m.archived_or_original_image = lambda value: value or None
    results, terms, _ = m.collector_media_ean_results(code)
    assert not results and terms
    assert terms[0][1]["platform"] == "PlayStation 5"
    assert m.classify_collector_candidate({"name": title, "category": "DVD / Blu-ray"}) == "games"
    assert m.classify_collector_candidate({"name": "Family Guy Season 16 DVD"}) == "movies"
    client = m.app.test_client()
    assert client.post("/login", data={"username": "intake-admin", "password": "test-pass"}).status_code == 302
    page = client.get("/identify/" + code)
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "Als Game übernehmen" in html and 'value="PlayStation 5"' in html
    assert "DVD / Blu-ray" not in html and "Als Film hinzufügen" not in html
    response = client.post("/external/import/barcode", data={
        "title": title, "platform": "PlayStation 5", "barcode": code,
        "source": "eBay GTIN", "source_id": "fixture-ps5"})
    assert response.status_code == 302 and "/collection/configure/" in response.location
    game = m.Game.query.filter_by(barcode=code).one()
    assert game.title == title and game.console.name == "PlayStation 5"
    assert m.CollectionItem.query.filter_by(game_id=game.id).count() == 0
    form = client.get(response.location)
    assert form.status_code == 200 and title in form.get_data(as_text=True)
    saved = client.post(f"/collection/configure/{game.id}?new_copy=1", data={
        "status": "owned", "ownership_format": "physical", "media_present": "on",
        "box_present": "on", "media_condition": "8", "box_condition": "8", "rarity": "1"})
    assert saved.status_code == 302
    assert m.CollectionItem.query.filter_by(game_id=game.id, user_id=m.shared_collection_user().id).count() == 1
    for category in ("movies", "tv", "books", "music", "cards", "custom"):
        wizard = client.get("/add/media?category=" + category).get_data(as_text=True)
        assert "Fragenkatalog für ein neues Medium" in wizard
        assert f'value="{category}" checked' in wizard
    library = client.get("/library?kind=game&q=Tiny&status=owned")
    assert library.status_code == 200
    assert 'aria-label="Sammlungsbereiche"' in library.get_data(as_text=True)
    owner = m.shared_collection_user()
    m.app_setting_set(f"custom_collection_categories_{owner.id}", json.dumps([
        {"id": "figures", "title": "Figuren", "icon": "📦"},
        {"id": "models", "title": "Modelle", "icon": "📦"}]))
    m.db.session.add_all([
        m.CollectorItem(user_id=owner.id, category="custom", title="Fixture Figure", metadata_json='{"custom_category":"figures"}'),
        m.CollectorItem(user_id=owner.id, category="custom", title="Fixture Model", metadata_json='{"custom_category":"models"}')])
    m.db.session.commit()
    filtered = client.get("/library?kind=custom&custom_category=figures").get_data(as_text=True)
    assert "Fixture Figure" in filtered and "Fixture Model" not in filtered
    assert "Figuren" in filtered and "Modelle" in filtered
    with m.app.test_request_context("/library"):
        from flask_login import login_user
        login_user(m.User.query.filter_by(username="intake-admin").one())
        groups = m.app.config["NAVIGATION_GROUPS"]()
        assert not any(item["category"] for item in groups[0]["items"])
print("OK: PS5 EAN → catalog → saved copy; category templates and collection navigation")
