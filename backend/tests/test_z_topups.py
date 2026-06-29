"""Phase 4: local sandbox / test top-up sandbox (no real payments)."""
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


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _a_user(client):
    users = client.get("/api/admin/family-users").json()
    return users[0]


def _balance(client, user_id):
    for u in client.get("/api/admin/family-users").json():
        if u["id"] == user_id:
            return u["credit_balance"]
    raise AssertionError("user not found")


def test_packages_are_fixed_sandbox_set(client):
    pkgs = client.get("/api/admin/topups/packages").json()
    by_id = {p["id"]: p for p in pkgs}
    assert {"starter", "creative", "video_test"} <= set(by_id)
    assert by_id["starter"]["credits"] == 50
    assert by_id["creative"]["credits"] == 200
    assert by_id["video_test"]["credits"] == 500
    assert by_id["starter"]["currency"] == "CAD"


def test_complete_topup_adds_credits_and_ledger_entry(client):
    user = _a_user(client)
    start = _balance(client, user["id"])
    created = client.post(
        "/api/admin/topups/create",
        json={"user_id": user["id"], "package_id": "starter", "note": "test"},
    )
    assert created.status_code == 201
    topup = created.json()
    assert topup["status"] == "pending"
    assert topup["credits"] == 50
    assert topup["amount_display"].endswith("CAD")

    done = client.post(f"/api/admin/topups/{topup['id']}/complete").json()
    assert done["status"] == "completed"
    assert done["completed_at"] is not None
    assert done["credit_transaction_id"]

    # Credits increased once.
    assert _balance(client, user["id"]) == start + 50

    # A single source of truth: a sandbox_topup ledger entry referencing the topup.
    txns = client.get(
        "/api/admin/credits/transactions",
        params={"transaction_type": "sandbox_topup"},
    ).json()
    match = [t for t in txns if t["related_id"] == topup["id"]]
    assert len(match) == 1
    assert match[0]["amount"] == 50
    assert match[0]["status"] == "completed"
    assert "SANDBOX" in (match[0]["note"] or "").upper()


def test_double_completion_does_not_double_credit(client):
    user = _a_user(client)
    topup = client.post(
        "/api/admin/topups/create",
        json={"user_id": user["id"], "package_id": "creative"},
    ).json()
    client.post(f"/api/admin/topups/{topup['id']}/complete")
    after_first = _balance(client, user["id"])
    again = client.post(f"/api/admin/topups/{topup['id']}/complete")
    assert again.status_code == 400
    assert _balance(client, user["id"]) == after_first


def test_cancelled_topup_adds_no_credits(client):
    user = _a_user(client)
    start = _balance(client, user["id"])
    topup = client.post(
        "/api/admin/topups/create",
        json={"user_id": user["id"], "package_id": "video_test"},
    ).json()
    cancelled = client.post(f"/api/admin/topups/{topup['id']}/cancel").json()
    assert cancelled["status"] == "cancelled"
    assert _balance(client, user["id"]) == start
    # Cancelled cannot then be completed.
    assert client.post(f"/api/admin/topups/{topup['id']}/complete").status_code == 400
    assert _balance(client, user["id"]) == start


def test_unknown_package_and_user_rejected(client):
    user = _a_user(client)
    assert client.post(
        "/api/admin/topups/create",
        json={"user_id": user["id"], "package_id": "nope"},
    ).status_code == 400
    assert client.post(
        "/api/admin/topups/create",
        json={"user_id": "missing", "package_id": "starter"},
    ).status_code == 404
