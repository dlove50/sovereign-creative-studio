"""Project workspace endpoint tests."""
import os
import tempfile
import time

_TMP = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(_TMP, 'test.db')}")
os.environ.setdefault("STORAGE_DIR", os.path.join(_TMP, "storage"))
os.environ.setdefault("GENERATOR_BACKEND", "mock")
os.environ.setdefault("PRODUCT_SCENE_BACKEND", "mock")
os.environ.setdefault("COPY_BACKEND", "mock")
os.environ.setdefault("VIDEO_BACKEND", "mock")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _wait(client, path, status, timeout=5.0):
    deadline = time.time() + timeout
    latest = None
    while time.time() < deadline:
        latest = client.get(path).json()
        if latest["status"] == status:
            return latest
        time.sleep(0.05)
    raise AssertionError(f"{path} did not reach {status}: {latest}")


def test_empty_project_workspace_does_not_crash(client):
    project = client.post(
        "/api/projects", json={"name": "Empty Workspace", "description": None}
    ).json()

    resp = client.get(f"/api/projects/{project['id']}/workspace")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == project["id"]
    assert body["counts_by_type"] == {
        "upload": 0,
        "processed_asset": 0,
        "scene": 0,
        "copy": 0,
        "video": 0,
        "campaign": 0,
    }
    assert body["uploaded_assets"] == []
    assert body["latest_activity_at"]


def test_project_workspace_invalid_project_returns_404(client):
    resp = client.get("/api/projects/nope/workspace")
    assert resp.status_code == 404


def test_project_workspace_returns_project_media_and_counts(client):
    project = client.post(
        "/api/projects", json={"name": "Workspace", "description": "Launch"}
    ).json()
    asset = client.post(
        "/api/assets/upload",
        data={"project_id": project["id"]},
        files={"file": ("workspace.png", b"asset", "image/png")},
    ).json()
    client.post(f"/api/assets/{asset['id']}/remove-background")
    processed = _wait(client, f"/api/assets/{asset['id']}", "completed")

    scene = client.post(
        "/api/product-scenes",
        json={
            "project_id": project["id"],
            "asset_id": asset["id"],
            "prompt": "workspace scene",
            "preset": "luxury",
        },
    ).json()
    scene = _wait(client, f"/api/product-scenes/{scene['id']}", "completed")

    copy = client.post(
        "/api/copy",
        json={
            "project_id": project["id"],
            "product_asset_id": asset["id"],
            "product_scene_id": scene["id"],
            "copy_type": "facebook_ad",
            "tone": "bold",
            "audience": "buyers",
            "prompt": "write copy",
        },
    ).json()
    copy = _wait(client, f"/api/copy/{copy['id']}", "completed")

    video = client.post(
        "/api/videos",
        json={
            "project_id": project["id"],
            "product_scene_id": scene["id"],
            "prompt": "motion",
            "motion_preset": "product_reveal",
            "duration_seconds": 3,
        },
    ).json()
    video = _wait(client, f"/api/videos/{video['id']}", "completed")

    resp = client.get(f"/api/projects/{project['id']}/workspace")

    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Workspace"
    assert body["description"] == "Launch"
    assert body["counts_by_type"]["upload"] == 1
    assert body["counts_by_type"]["processed_asset"] == 1
    assert body["counts_by_type"]["scene"] == 1
    assert body["counts_by_type"]["copy"] == 1
    assert body["counts_by_type"]["video"] == 1
    assert body["uploaded_assets"][0]["source_entity_id"] == asset["id"]
    assert body["processed_assets"][0]["asset_url"] == processed["processed_url"]
    assert body["product_scenes"][0]["download_url"] == f"/api/exports/scene/{scene['id']}"
    assert body["copy_generations"][0]["download_url"] == f"/api/exports/copy/{copy['id']}"
    assert body["video_generations"][0]["download_url"] == f"/api/exports/video/{video['id']}"
