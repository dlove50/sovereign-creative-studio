"""Stale job recovery: detect and clear queued/running jobs stuck past a threshold."""
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")
    os.environ["DEFAULT_CREDITS"] = "100"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.main import app
from app.models import CreditTransaction, Generation, Project, User, VideoGeneration


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _owner_id():
    with SessionLocal() as db:
        return db.scalars(select(User).order_by(User.created_at)).first().id


def _project(uid):
    with SessionLocal() as db:
        p = Project(user_id=uid, name="stale-proj", description=None)
        db.add(p)
        db.commit()
        return p.id


def _insert_video(uid, pid, *, status, age_minutes):
    with SessionLocal() as db:
        v = VideoGeneration(
            user_id=uid, project_id=pid, source_image_url="", mode="text_to_video",
            prompt="stale clip", motion_preset="slow_zoom", duration_seconds=3, status=status,
        )
        db.add(v)
        db.commit()
        v.created_at = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
        db.commit()
        return v.id


def _insert_generation(uid, pid, *, status, age_minutes):
    with SessionLocal() as db:
        g = Generation(user_id=uid, project_id=pid, prompt="stale gen", media_type="image", status=status)
        db.add(g)
        db.commit()
        g.created_at = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
        db.commit()
        return g.id


def _stale_ids(client, threshold=60):
    return {(j["feature"], j["id"]) for j in client.get("/api/admin/jobs/stale", params={"threshold_minutes": threshold}).json()}


def test_stale_queued_job_detected(client):
    uid = _owner_id(); pid = _project(uid)
    vid = _insert_video(uid, pid, status="queued", age_minutes=120)
    rows = client.get("/api/admin/jobs/stale", params={"threshold_minutes": 60}).json()
    match = next(j for j in rows if j["id"] == vid)
    assert match["status"] == "queued" and match["elapsed_minutes"] >= 120


def test_stale_running_job_detected(client):
    uid = _owner_id(); pid = _project(uid)
    gid = _insert_generation(uid, pid, status="running", age_minutes=200)
    assert ("base_generation", gid) in _stale_ids(client, 60)


def test_recent_running_job_not_stale(client):
    uid = _owner_id(); pid = _project(uid)
    vid = _insert_video(uid, pid, status="running", age_minutes=5)
    assert ("video", vid) not in _stale_ids(client, 60)


def test_mark_stale_failed(client):
    uid = _owner_id(); pid = _project(uid)
    vid = _insert_video(uid, pid, status="running", age_minutes=300)
    resp = client.post(
        "/api/admin/jobs/mark-stale",
        json={"action": "failed", "threshold_minutes": 60, "ids": [{"feature": "video", "id": vid}]},
    ).json()
    assert resp["marked"] == 1 and resp["action"] == "failed"
    v = client.get(f"/api/videos/{vid}").json()
    assert v["status"] == "failed"
    assert "stale" in (v["error"] or "").lower()
    assert ("video", vid) not in _stale_ids(client, 60)


def test_mark_stale_cancelled(client):
    uid = _owner_id(); pid = _project(uid)
    gid = _insert_generation(uid, pid, status="queued", age_minutes=300)
    resp = client.post(
        "/api/admin/jobs/mark-stale",
        json={"action": "cancelled", "threshold_minutes": 60, "ids": [{"feature": "base_generation", "id": gid}]},
    ).json()
    assert resp["marked"] == 1
    g = client.get(f"/api/generations/{gid}").json()
    assert g["status"] == "cancelled"


def test_legacy_create_video_relabelled_and_dismissable(client):
    uid = _owner_id(); pid = _project(uid)
    with SessionLocal() as db:
        g = Generation(
            user_id=uid, project_id=pid, prompt="old create-page video attempt",
            media_type="video", status="failed",
            error="ComfyUI adapter currently supports image generation only",
        )
        db.add(g)
        db.commit()
        gid = g.id
    # Relabelled in the monitor so it is not mistaken for a real /videos failure.
    item = next(j for j in client.get("/api/admin/jobs").json()["jobs"] if j["id"] == gid)
    assert item["feature"] == "base_generation"
    assert "Legacy Create-page video attempt" in (item["title"] or "")
    # Dismiss removes it from the monitor without deleting files.
    resp = client.post("/api/admin/jobs/dismiss", json={"feature": "base_generation", "id": gid})
    assert resp.status_code == 200 and resp.json()["dismissed"] is True
    assert all(j["id"] != gid for j in client.get("/api/admin/jobs").json()["jobs"])
    # Copy jobs have no archive column -> rejected clearly.
    assert client.post("/api/admin/jobs/dismiss", json={"feature": "copy", "id": "x"}).status_code == 400


def test_no_unfair_charge_after_marking_stale(client):
    uid = _owner_id(); pid = _project(uid)
    before = next(u for u in client.get("/api/admin/family-users").json() if u["id"] == uid)["credit_balance"]
    vid = _insert_video(uid, pid, status="running", age_minutes=400)
    resp = client.post(
        "/api/admin/jobs/mark-stale",
        json={"action": "failed", "threshold_minutes": 60, "ids": [{"feature": "video", "id": vid}]},
    ).json()
    after = next(u for u in client.get("/api/admin/family-users").json() if u["id"] == uid)["credit_balance"]
    # Never-completed job was never charged: balance unchanged, no refund needed.
    assert after == before
    assert resp["refunds"] == 0
    with SessionLocal() as db:
        charge = db.scalar(
            select(CreditTransaction).where(
                CreditTransaction.related_id == vid,
                CreditTransaction.transaction_type == "generation_charge",
            )
        )
    assert charge is None
