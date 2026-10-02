#!/usr/bin/env python3
"""Authenticated smoke test for the cumulative release."""
import os
import sys
import tempfile
from pathlib import Path

_sandbox = tempfile.TemporaryDirectory(prefix="bibo-smoke-")
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(_sandbox.name) / "smoke.db")
os.environ["ADMIN_USERNAME"] = "smoke-admin"
os.environ["ADMIN_PASSWORD"] = "smoke-password"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.app import APP_VERSION, app


def main():
    client = app.test_client()
    login = client.post("/login", data={"username": "smoke-admin", "password": "smoke-password"})
    assert login.status_code in {302, 303}, login.status_code
    paths = ["/", "/bewertungen", "/collector/collections", "/price-center", "/quality/errors", "/admin/data-health", "/admin/operations", "/whats-new", "/inbox", "/capture-batches", "/insights", "/library", "/planner", "/locations", "/loans", "/add/media", "/discover"]
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, f"{path}: {response.status_code}"
    health = client.get("/health/deep")
    assert health.status_code == 200 and health.json.get("version") == APP_VERSION, health.get_data(as_text=True)
    print(f"OK: Bibo {APP_VERSION}, Anmeldung und {len(paths)} Kernseiten")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
