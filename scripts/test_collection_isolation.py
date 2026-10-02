#!/usr/bin/env python3
"""Regression tests for collection-scoped game series and custom categories."""
import importlib
import os
import sys
import tempfile
from pathlib import Path

from werkzeug.security import generate_password_hash

_sandbox = tempfile.TemporaryDirectory(prefix="bibo-collection-scope-")
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(_sandbox.name) / "scope.db")
os.environ["ADMIN_USERNAME"] = "scope-admin"
os.environ["ADMIN_PASSWORD"] = "scope-password"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

module = importlib.import_module("app.app")

with module.app.app_context():
    first_owner = module.shared_collection_user()
    second_owner = module.User(
        username="__scope_second__", display_name="Zweite Sammlung",
        password_hash=generate_password_hash("unused-password"), is_system=True, role="viewer",
    )
    empty_owner = module.User(
        username="__scope_empty__", display_name="Leere Sammlung",
        password_hash=generate_password_hash("unused-password"), is_system=True, role="viewer",
    )
    console = module.Console(name="Scope Console")
    module.db.session.add_all([second_owner, empty_owner, console])
    module.db.session.flush()
    first_game = module.Game(title="Erstes Reihenspiel", console_id=console.id, franchise="Erste Reihe", series_status="series")
    second_game = module.Game(title="Zweites Reihenspiel", console_id=console.id, franchise="Zweite Reihe", series_status="series")
    module.db.session.add_all([first_game, second_game])
    module.db.session.flush()
    module.db.session.add_all([
        module.CollectionItem(user_id=first_owner.id, game_id=first_game.id, status="owned", ownership_format="physical"),
        module.CollectionItem(user_id=second_owner.id, game_id=second_game.id, status="owned", ownership_format="physical"),
    ])
    module.db.session.commit()

    first_rows = module._game_franchise_overview_rows(first_owner.id)
    second_rows = module._game_franchise_overview_rows(second_owner.id)
    empty_rows = module._game_franchise_overview_rows(empty_owner.id)
    assert [row["name"] for row in first_rows] == ["Erste Reihe"]
    assert [row["name"] for row in second_rows] == ["Zweite Reihe"]
    assert empty_rows == [], "Eine leere Sammlung darf keine globalen 0/x-Spielreihen sehen"

    client = module.app.test_client()
    login = client.post("/login", data={"username": "scope-admin", "password": "scope-password"})
    assert login.status_code in {302, 303}
    created = client.post("/collector/custom-categories", data={
        "title": "Figuren", "icon": "🗿", "description": "Meine Sammlerfiguren",
    })
    assert created.status_code in {302, 303}
    categories = module.custom_collection_categories(first_owner.id)
    assert len(categories) == 1 and categories[0]["title"] == "Figuren"
    category_id = categories[0]["id"]
    home = client.get("/").get_data(as_text=True)
    assert "Figuren" in home and "Sammlungskategorie hinzufügen" in home

    item = client.post("/add/media", data={
        "category": "custom", "custom_category": category_id, "title": "Testfigur",
        "media_type": "Figur", "ownership_format": "physical", "release_kind": "single",
        "de_physical_release_status": "physical", "quantity": "1",
    })
    assert item.status_code in {302, 303}
    saved = module.CollectorItem.query.filter_by(user_id=first_owner.id, category="custom", title="Testfigur").one()
    assert module.collector_metadata(saved).get("custom_category") == category_id
    filtered = client.get(f"/collector/custom?custom_category={category_id}").get_data(as_text=True)
    assert "Testfigur" in filtered and "Meine Sammlerfiguren" in filtered
    valuation_dashboard = client.get("/bewertungen").get_data(as_text=True)
    assert "Figuren" in valuation_dashboard
    print("OK: Spielreihen und eigene Dashboard-Kategorien sind sauber je Sammlung getrennt")
