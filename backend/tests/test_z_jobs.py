"""Phase 7: admin job monitor (read-only normalized job list + counts)."""
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

from app.database import SessionLocal
from app.main import app
from app.models import AvatarJob, User


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _finished_generation(client):
    proj = client.post("/api/projects", json={"name": "JobProj", "description": None}).json()
    gen = client.post(
        "/api/generations",
        json={"prompt": "job monitor test", "media_type": "image", "project_id": proj["id"]},
    ).json()
    for _ in range(40):
        g = client.get(f"/api/generations/{gen['id']}").json()
        if g["status"] in ("completed", "failed"):
            break
        time.sleep(0.25)
    return proj, gen


def test_counts_and_attribution(client):
    proj, gen = _finished_generation(client)
    data = client.get("/api/admin/jobs").json()
    assert {"queued", "running", "completed", "failed", "total"} <= set(data["counts"])
    assert data["counts"]["total"] >= 1
    job = next(j for j in data["jobs"] if j["id"] == gen["id"])
    assert job["feature"] == "base_generation"
    assert job["user_id"]
    assert job["project_id"] == proj["id"]
    assert job["project_name"] == "JobProj"
    assert job["status"] in ("queued", "running", "completed", "failed")


def test_filter_by_feature(client):
    data = client.get("/api/admin/jobs", params={"feature": "base_generation"}).json()
    assert all(j["feature"] == "base_generation" for j in data["jobs"])


def test_filter_by_status(client):
    data = client.get("/api/admin/jobs", params={"status": "completed"}).json()
    assert all(j["status"] == "completed" for j in data["jobs"])


def test_avatar_video_jobs_are_in_monitor(client):
    with SessionLocal() as db:
        user = db.query(User).first()
        job = AvatarJob(
            user_id=user.id,
            job_type="avatar_talking",
            status="completed",
            provider="comfyui_wan_infinite_talk",
            script_text="avatar monitor",
            avatar_preset="tiny_test",
            output_video_path="/storage/avatar_videos/example.mp4",
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id
    data = client.get("/api/admin/jobs", params={"feature": "avatar_video"}).json()
    match = next(j for j in data["jobs"] if j["id"] == job_id)
    assert match["feature"] == "avatar_video"
    assert match["mode"] == "tiny_test"
    assert match["result_url"] == "/storage/avatar_videos/example.mp4"
