"""Phase: video credit charging (10 credits per real video generation).

Mock video backend (test default) completes jobs quickly; the charge happens on
completion, exactly like the image path. Failed jobs are never charged.
"""
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

import app.services.video_jobs as video_jobs
from app.main import app

HEADER = "X-SCS-Family-User-Id"
SOURCE = "/storage/videos/seed.mp4"  # mock backend does not read the file


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _user(client, name, credits=100):
    return client.post(
        "/api/admin/family-users",
        json={"display_name": name, "role": "family_user", "initial_credits": credits},
    ).json()


def _balance(client, user_id):
    for u in client.get("/api/admin/family-users").json():
        if u["id"] == user_id:
            return u["credit_balance"]
    raise AssertionError("user not found")


def _hdr(uid):
    return {HEADER: uid}


def _make_video(client, uid, mode, *, duration=3):
    pid = client.post(
        "/api/projects", json={"name": f"{mode}-proj", "description": None}, headers=_hdr(uid)
    ).json()["id"]
    body = {
        "project_id": pid,
        "prompt": "tiny test clip",
        "motion_preset": "slow_zoom",
        "duration_seconds": duration,
        "mode": mode,
    }
    if mode != "text_to_video":
        body["source_image_url"] = SOURCE
    return client.post("/api/videos", json=body, headers=_hdr(uid))


def _wait(client, uid, video_id, target, tries=60):
    for _ in range(tries):
        v = client.get(f"/api/videos/{video_id}", headers=_hdr(uid)).json()
        if v["status"] == target:
            return v
        time.sleep(0.25)
    raise AssertionError(f"video did not reach {target}: {v['status']}")


def _charge_tx(client, uid, video_id):
    txns = client.get(
        "/api/admin/credits/transactions", params={"user_id": uid}
    ).json()
    return [
        t
        for t in txns
        if t["related_id"] == video_id and t["transaction_type"] == "generation_charge"
    ]


@pytest.mark.parametrize(
    "mode",
    ["image_to_video", "text_to_video", "video_to_video", "video_upscale", "video_extension"],
)
def test_each_video_mode_charges_10(client, mode):
    u = _user(client, f"VidCharge {mode}")
    start = _balance(client, u["id"])
    resp = _make_video(client, u["id"], mode)
    assert resp.status_code == 201, resp.text
    video_id = resp.json()["id"]
    _wait(client, u["id"], video_id, "completed")

    assert _balance(client, u["id"]) == start - 10
    charges = _charge_tx(client, u["id"], video_id)
    assert len(charges) == 1
    tx = charges[0]
    assert tx["amount"] == -10
    assert tx["related_feature"] == "video"
    assert tx["status"] == "completed"
    assert mode in tx["note"]


def test_charge_attributed_to_active_family_user(client):
    owner = next(
        u for u in client.get("/api/admin/family-users").json() if u["role"] == "owner_admin"
    )
    owner_start = owner["credit_balance"]
    u = _user(client, "Attributed Member")
    resp = _make_video(client, u["id"], "image_to_video")
    video_id = resp.json()["id"]
    _wait(client, u["id"], video_id, "completed")

    assert _balance(client, u["id"]) == 100 - 10
    # Owner was not charged for the family member's video.
    assert _balance(client, owner["id"]) == owner_start
    # The charge ledger row belongs to the active family user.
    assert _charge_tx(client, u["id"], video_id)


def test_insufficient_credits_blocks_before_generation(client):
    u = _user(client, "Broke Member", credits=5)
    resp = _make_video(client, u["id"], "image_to_video")
    assert resp.status_code == 402
    assert "credits" in resp.json()["detail"].lower()
    # No video, no charge, balance untouched.
    assert _balance(client, u["id"]) == 5


def test_failed_video_is_not_charged(client, monkeypatch):
    class _Boom:
        async def generate(self, **kwargs):
            raise RuntimeError("simulated backend failure")

    monkeypatch.setattr(video_jobs, "get_video_generator", lambda provider="local_ltx": _Boom())
    u = _user(client, "Unlucky Member")
    resp = _make_video(client, u["id"], "image_to_video")
    video_id = resp.json()["id"]
    _wait(client, u["id"], video_id, "failed")

    # Charge-on-completion means a failed job costs nothing.
    assert _balance(client, u["id"]) == 100
    assert _charge_tx(client, u["id"], video_id) == []


def test_admin_can_add_credits_after_video_charge(client):
    u = _user(client, "Topped Up Member")
    resp = _make_video(client, u["id"], "image_to_video")
    _wait(client, u["id"], resp.json()["id"], "completed")
    assert _balance(client, u["id"]) == 90

    client.post(
        "/api/admin/credits/add",
        json={"user_id": u["id"], "amount": 50, "note": "family top-up by admin"},
    )
    assert _balance(client, u["id"]) == 140


def test_admin_can_remove_credits_still_works(client):
    u = _user(client, "Trim Member")
    client.post(
        "/api/admin/credits/remove",
        json={"user_id": u["id"], "amount": 25, "note": "admin correction"},
    )
    assert _balance(client, u["id"]) == 75
