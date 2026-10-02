#!/usr/bin/env python3
"""Regression checks for the non-destructive Bibo 4 registry."""
import os
import sys
import tempfile
from pathlib import Path

_sandbox = tempfile.TemporaryDirectory(prefix="bibo-registry-")
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(_sandbox.name) / "registry.db")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.app import (  # noqa: E402
    BiboCopy, BiboEdition, BiboSeries, BiboWork, CollectorItem, app, db,
    refresh_bibo_registry, shared_collection_user,
)


with app.app_context():
    owner = shared_collection_user()
    metadata = '{"collection_name":"Navy CIS","collection_order":8,"season_number":8,"de_physical_release_status":"physical"}'
    first = CollectorItem(user_id=owner.id, category="tv", title="Navy CIS Staffel 8.1", quantity=1,
                          media_type="DVD", edition="Teil 1", metadata_json=metadata, purchase_price_eur=10.0)
    second = CollectorItem(user_id=owner.id, category="tv", title="Navy CIS Staffel 8.2", quantity=1,
                           media_type="DVD", edition="Teil 2", metadata_json=metadata, purchase_price_eur=12.0)
    db.session.add_all([first, second]); db.session.commit()
    refresh_bibo_registry()
    works = BiboWork.query.filter_by(media_kind="tv", logical_unit_key="season:8").all()
    assert len(works) == 1, len(works)
    assert works[0].series_name == "Navy CIS"
    assert works[0].availability_de == "physical"
    assert BiboEdition.query.filter_by(work_id=works[0].id, active=True).count() == 2
    assert BiboCopy.query.join(BiboEdition).filter(BiboEdition.work_id == works[0].id, BiboCopy.active.is_(True)).count() == 2
    assert BiboSeries.query.filter_by(title="Navy CIS", active=True).count() == 1
    assert CollectorItem.query.count() == 2, "Originaldaten dürfen beim Registerabgleich nicht verändert werden"
    print("OK: Bibo-4-Register vereinigt Split-Ausgaben ohne Originaldaten zu verändern")
