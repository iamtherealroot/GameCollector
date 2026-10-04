#!/usr/bin/env python3
"""Regression test: an existing EAN may create another physical copy."""
import importlib
import os
import sys
import tempfile
from pathlib import Path

_sandbox = tempfile.TemporaryDirectory(prefix="bibo-ean-copy-")
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(_sandbox.name) / "ean-copy.db")
os.environ["ADMIN_USERNAME"] = "ean-admin"
os.environ["ADMIN_PASSWORD"] = "ean-password"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

module = importlib.import_module("app.app")

with module.app.app_context():
    owner = module.shared_collection_user()
    original = module.CollectorItem(
        user_id=owner.id,
        category="movies",
        title="EAN Testfilm",
        barcode="4000000000001",
        media_type="Blu-ray",
        edition="Doppelbox",
        purchase_price_eur=49.99,
        estimated_value_eur=70.0,
        storage_location="Altes Regal",
        notes="Darf nicht kopiert werden",
        external_source="TMDB",
        external_id="1234",
        metadata_json='{"tmdb_id":"1234","edition_type":"box","de_physical_release_status":"physical"}',
    )
    module.db.session.add(original)
    module.db.session.flush()
    module.db.session.add(module.ReleaseCoverage(
        owner_id=owner.id,
        source_kind="collector",
        source_id=str(original.id),
        target_kind="movies",
        target_key="movie:tmdb:1234",
        target_title="EAN Testfilm",
        sequence_label="1",
        origin="tmdb",
    ))
    console = module.Console(name="EAN Testkonsole")
    module.db.session.add(console)
    module.db.session.flush()
    game = module.Game(title="EAN Testspiel", console_id=console.id, barcode="4000000000001", edition="Standard")
    accessory = module.AccessoryItem(
        user_id=owner.id, console_id=console.id, name="EAN Testzubehör", barcode="4000000000001",
        purchase_price=29.99, estimated_value=35.0, storage_location="Zubehörregal", notes="Originalnotiz",
    )
    module.db.session.add_all([game, accessory])
    module.db.session.commit()
    original_id = original.id
    accessory_id = accessory.id

    client = module.app.test_client()
    login = client.post("/login", data={"username": "ean-admin", "password": "ean-password"})
    assert login.status_code in {302, 303}

    search = client.get("/find?q=4000000000001")
    assert search.status_code == 200
    assert "Medienart" in search.get_data(as_text=True)
    identify = client.get("/identify/4000000000001")
    page = identify.get_data(as_text=True)
    assert identify.status_code == 200
    assert "Diese EAN ist bereits bekannt" in page
    assert "Vorhandenes Exemplar öffnen" in page
    assert "Weiteres Exemplar erfassen" in page
    assert "EAN Testspiel" in page and "EAN Testzubehör" in page

    handoff = client.get(f"/collector/item/{original_id}/new-copy")
    assert handoff.status_code in {302, 303} and handoff.headers["Location"].endswith("/add/media")
    wizard = client.get(handoff.headers["Location"])
    wizard_page = wizard.get_data(as_text=True)
    assert "Weitere physische Kopie" in wizard_page
    assert 'value="4000000000001"' in wizard_page
    assert "EAN Testfilm" in wizard_page and "Altes Regal" not in wizard_page

    created = client.post("/add/media", data={
        "category": "movies",
        "title": "EAN Testfilm",
        "barcode": "4000000000001",
        "media_type": "Blu-ray",
        "edition": "Doppelbox",
        "ownership_format": "physical",
        "release_kind": "box",
        "de_physical_release_status": "physical",
        "tmdb_id": "1234",
        "source": "TMDB",
        "source_id": "1234",
        "copy_origin_id": str(original_id),
        "included_titles": "EAN Testfilm",
        "condition": "Sehr gut",
        "purchase_price_eur": "19,99",
        "storage_location": "Neues Regal",
    })
    assert created.status_code in {302, 303}
    copies = module.CollectorItem.query.filter_by(user_id=owner.id, barcode="4000000000001").order_by(module.CollectorItem.id).all()
    assert len(copies) == 2
    new_copy = copies[-1]
    assert new_copy.id != original_id and new_copy.purchase_price_eur == 19.99
    assert new_copy.storage_location == "Neues Regal" and new_copy.notes is None
    assert module.collector_metadata(new_copy).get("copy_origin_id") == original_id
    assert module.ReleaseCoverage.query.filter_by(source_id=str(new_copy.id), target_kind="movies").count() == 1

    accessory_copy = client.post(f"/accessories/{accessory_id}/duplicate-copy")
    assert accessory_copy.status_code in {302, 303}
    accessory_rows = module.AccessoryItem.query.filter_by(user_id=owner.id, barcode="4000000000001").order_by(module.AccessoryItem.id).all()
    assert len(accessory_rows) == 2
    assert accessory_rows[-1].purchase_price is None and accessory_rows[-1].estimated_value is None
    assert accessory_rows[-1].storage_location is None and accessory_rows[-1].notes is None
    print("OK: vorhandene EAN öffnet Wahlmöglichkeit und legt ein separates Exemplar über den Fragenkatalog an")
