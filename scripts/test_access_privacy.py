#!/usr/bin/env python3
"""Regression: collection managers must not receive the global user directory."""
import importlib
import os
import sys
import tempfile
from pathlib import Path
from werkzeug.security import generate_password_hash

_sandbox = tempfile.TemporaryDirectory(prefix="bibo-access-privacy-")
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(_sandbox.name) / "access.db")
os.environ["ADMIN_USERNAME"] = "root-admin"
os.environ["ADMIN_PASSWORD"] = "root-password"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
module = importlib.import_module("app.app")

with module.app.app_context():
    owner = module.shared_collection_user()
    admin = module.User.query.filter_by(username="root-admin").one()
    manager = module.User(username="manager", password_hash=generate_password_hash("manager-pass"), role="editor", is_admin=False, is_system=False)
    outsider = module.User(username="outsider", password_hash=generate_password_hash("outsider-pass"), role="viewer", is_admin=False, is_system=False)
    module.db.session.add_all([manager, outsider]); module.db.session.flush()
    space = module.CollectionSpace.query.filter_by(owner_user_id=owner.id).one()
    module.db.session.add(module.CollectionPermission(collection_id=space.id, user_id=manager.id, role="manager", can_manage_users=True))
    module.db.session.commit()

    manager_client = module.app.test_client()
    assert manager_client.post("/login", data={"username":"manager","password":"manager-pass"}).status_code in {302,303}
    page = manager_client.get("/collection/access").get_data(as_text=True)
    assert "manager" in page
    assert "outsider" not in page, "Unbeteiligte Systemnutzer dürfen für Sammlungsverwalter nicht sichtbar sein"

    outsider_client = module.app.test_client()
    assert outsider_client.post("/login", data={"username":"outsider","password":"outsider-pass"}).status_code in {302,303}
    requested = outsider_client.post("/collections/request-access", data={"collection_id":str(space.id),"requested_role":"editor","message":"Bitte freigeben"})
    assert requested.status_code in {302,303}

    page = manager_client.get("/collection/access").get_data(as_text=True)
    assert "outsider" in page and "Bitte freigeben" in page
    request_row = module.CollectionAccessRequest.query.filter_by(collection_id=space.id, user_id=outsider.id, status="pending").one()
    approved = manager_client.post(f"/collection/access/requests/{request_row.id}/approve")
    assert approved.status_code in {302,303}
    permission = module.CollectionPermission.query.filter_by(collection_id=space.id, user_id=outsider.id).one()
    assert permission.role == "editor"
    print("OK: Sammlungsverwalter sehen nur Mitglieder und konkrete Zugriffsanfragen")
