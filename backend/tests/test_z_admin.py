"""Private/local admin dashboard tests."""
import os
import sys
import tempfile
import time

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")
    os.environ["DEFAULT_CREDITS"] = "100"

import pytest
from fastapi.testclient import TestClient

import app.services.admin as admin_service
from app.main import app
from app.schemas import WorkflowManagerStatusOut


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_admin_dashboard_reports_private_studio_summary(client):
    resp = client.get("/api/admin/dashboard")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "local/private family studio"
    assert body["service_health"]["status"] == "ok"
    assert "product_scene_model" in body["service_health"]
    assert "workflow_config" in body
    assert body["family_users"]
    assert body["family_users"][0]["role"] == "owner_admin"
    assert body["family_users"][0]["status"] == "active"
    assert "updated_at" in body["family_users"][0]
    assert "recent_jobs" in body
    assert "failed_jobs" in body
    assert "recent_credit_transactions" in body


def test_admin_safe_reset_delegates_to_workflow_manager(client, monkeypatch):
    def _fake_update_config(changes):
        assert changes == admin_service.SAFE_WORKFLOW_CONFIG
        return {
            "applied": changes,
            "warnings": [],
            "status": WorkflowManagerStatusOut(
                active_image_model="flux-kontext",
                active_scene_workflow="workflows/product_scene_flux_kontext.json",
                active_scene_mode="segmented_composite_polished",
                active_video_backend="mock",
                active_copy_backend="mock",
                active_copy_model="template",
                generator_backend="mock",
                product_scene_backend="mock",
                comfyui_base_url="http://127.0.0.1:8001",
                comfyui_reachable=False,
            ),
        }

    monkeypatch.setattr(admin_service.workflow_manager, "update_config", _fake_update_config)

    resp = client.post("/api/admin/workflow/reset-safe-defaults")
    assert resp.status_code == 200
    body = resp.json()
    assert body["applied"]["image_model"] == "flux-kontext"
    assert body["applied"]["video_backend"] == "mock"
    assert body["warnings"] == []


def test_admin_family_user_lifecycle(client):
    create_resp = client.post(
        "/api/admin/family-users",
        json={
            "display_name": "Family Tester",
            "role": "family_user",
            "status": "active",
            "initial_credits": 25,
            "notes": "Can test local creative flows.",
        },
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["display_name"] == "Family Tester"
    assert created["role"] == "family_user"
    assert created["status"] == "active"
    assert created["credit_balance"] == 25
    assert created["notes"] == "Can test local creative flows."
    assert created["created_at"]
    assert created["updated_at"]

    list_resp = client.get("/api/admin/family-users")
    assert list_resp.status_code == 200
    assert any(user["id"] == created["id"] for user in list_resp.json())

    update_resp = client.put(
        f"/api/admin/family-users/{created['id']}",
        json={
            "display_name": "Updated Family Tester",
            "role": "guest",
            "notes": "Guest access for testing.",
        },
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["display_name"] == "Updated Family Tester"
    assert updated["role"] == "guest"
    assert updated["status"] == "active"
    assert updated["credit_balance"] == 25
    assert updated["notes"] == "Guest access for testing."

    disabled = client.post(f"/api/admin/family-users/{created['id']}/disable").json()
    assert disabled["status"] == "disabled"

    reactivated = client.post(
        f"/api/admin/family-users/{created['id']}/reactivate"
    ).json()
    assert reactivated["status"] == "active"


def test_admin_family_user_duplicate_email_is_rejected(client):
    payload = {
        "display_name": "Duplicate Email",
        "role": "family_user",
        "email": "duplicate@family.local",
    }
    first = client.post("/api/admin/family-users", json=payload)
    assert first.status_code == 201
    second = client.post("/api/admin/family-users", json=payload)
    assert second.status_code == 409


def test_admin_manual_credit_adjustments_create_ledger_entries(client):
    created = client.post(
        "/api/admin/family-users",
        json={"display_name": "Credit Tester", "initial_credits": 10},
    ).json()

    added = client.post(
        "/api/admin/credits/add",
        json={
            "user_id": created["id"],
            "amount": 15,
            "note": "Allowance top-up for local testing.",
        },
    )
    assert added.status_code == 200
    assert added.json()["credit_balance"] == 25

    removed = client.post(
        "/api/admin/credits/remove",
        json={
            "user_id": created["id"],
            "amount": 5,
            "note": "Correcting local test balance.",
        },
    )
    assert removed.status_code == 200
    assert removed.json()["credit_balance"] == 20

    txs = client.get(
        f"/api/admin/credits/transactions?user_id={created['id']}&status=manual"
    )
    assert txs.status_code == 200
    body = txs.json()
    assert [tx["transaction_type"] for tx in body[:2]] == [
        "manual_remove",
        "manual_add",
    ]
    assert body[0]["related_feature"] == "admin_adjustment"
    assert body[0]["note"] == "Correcting local test balance."


def test_admin_refunds_generation_charge(client):
    me = client.get("/api/me").json()
    user_id = me["id"]
    before = me["credits"]
    gen = client.post(
        "/api/generations",
        json={"prompt": "admin ledger refund smoke", "media_type": "image"},
    ).json()
    deadline = time.time() + 5
    current = gen
    while time.time() < deadline:
        current = client.get(f"/api/generations/{gen['id']}").json()
        if current["status"] == "completed":
            break
        time.sleep(0.05)
    assert current["status"] == "completed"
    assert client.get("/api/me").json()["credits"] < before

    txs = client.get(
        f"/api/admin/credits/transactions?user_id={user_id}&transaction_type=generation_charge"
    ).json()
    charge = next(tx for tx in txs if tx["generation_id"] == current["id"])
    assert charge["amount"] < 0
    assert charge["related_feature"] == "base_generation"
    assert charge["status"] == "completed"

    refund = client.post(
        f"/api/admin/credits/transactions/{charge['id']}/refund",
        json={"note": "Refund local QA generation."},
    )
    assert refund.status_code == 200
    refunded = refund.json()
    assert refunded["transaction_type"] == "refund"
    assert refunded["amount"] == abs(charge["amount"])
    assert refunded["status"] == "refunded"
    assert refunded["note"] == "Refund local QA generation."
    assert client.get("/api/me").json()["credits"] == before

    repeat = client.post(f"/api/admin/credits/transactions/{charge['id']}/refund")
    assert repeat.status_code == 400
