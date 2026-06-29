"""Phase 5: local active family user switcher (X-SCS-Family-User-Id header)."""
import os
import sys
import tempfile

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")
    os.environ["DEFAULT_CREDITS"] = "100"

import pytest
from fastapi.testclient import TestClient

from app.main import app

HEADER = "X-SCS-Family-User-Id"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _owner(client):
    users = client.get("/api/admin/family-users").json()
    return next(u for u in users if u["role"] == "owner_admin")


def _new_family_user(client, name="Switcher Kid"):
    return client.post(
        "/api/admin/family-users",
        json={"display_name": name, "role": "family_user", "initial_credits": 10},
    ).json()


def test_no_header_uses_seeded_owner(client):
    # A project created with no header belongs to the seeded owner.
    proj = client.post("/api/projects", json={"name": "OwnerProj", "description": None}).json()
    listed = client.get("/api/projects").json()
    assert any(p["id"] == proj["id"] for p in listed)


def test_valid_active_user_header_attributes_to_that_user(client):
    u2 = _new_family_user(client, "Active Member")
    proj = client.post(
        "/api/projects",
        json={"name": "MemberProj", "description": None},
        headers={HEADER: u2["id"]},
    ).json()
    # Visible when acting as u2...
    as_u2 = client.get("/api/projects", headers={HEADER: u2["id"]}).json()
    assert any(p["id"] == proj["id"] for p in as_u2)
    # ...and NOT visible to the owner (so it was attributed to u2, not the owner).
    as_owner = client.get("/api/projects").json()
    assert not any(p["id"] == proj["id"] for p in as_owner)


def test_disabled_user_header_is_rejected(client):
    u = _new_family_user(client, "Disabled Member")
    client.post(f"/api/admin/family-users/{u['id']}/disable")
    resp = client.get("/api/projects", headers={HEADER: u["id"]})
    assert resp.status_code == 403
    assert "disabled" in resp.json()["detail"].lower()


def test_unknown_user_header_is_rejected(client):
    resp = client.get("/api/projects", headers={HEADER: "does-not-exist"})
    assert resp.status_code == 404
    # And it did not silently create a user.
    users = client.get("/api/admin/family-users").json()
    assert not any(u["id"] == "does-not-exist" for u in users)


def test_owner_behaviour_intact_after_switching(client):
    u2 = _new_family_user(client, "Temp Member")
    # Act as u2, then back to owner (no header) — owner still works normally.
    client.get("/api/projects", headers={HEADER: u2["id"]})
    assert client.get("/api/projects").status_code == 200
    assert client.get("/api/admin/dashboard").status_code == 200
