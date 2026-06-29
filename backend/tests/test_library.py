"""Asset Library endpoint tests."""
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


def test_library_empty_does_not_crash(client):
    resp = client.get("/api/library")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_library_returns_uploads_processed_scenes_copy_and_videos(client):
    project = client.post(
        "/api/projects", json={"name": "Library Project", "description": None}
    ).json()
    asset = client.post(
        "/api/assets/upload",
        data={"project_id": project["id"]},
        files={"file": ("shirt.png", b"fake image bytes", "image/png")},
    ).json()

    client.post(f"/api/assets/{asset['id']}/remove-background")
    processed = _wait(client, f"/api/assets/{asset['id']}", "completed")

    scene = client.post(
        "/api/product-scenes",
        json={
            "project_id": project["id"],
            "asset_id": asset["id"],
            "prompt": "fashion product scene",
            "preset": "studio",
        },
    ).json()
    scene = _wait(client, f"/api/product-scenes/{scene['id']}", "completed")

    copy = client.post(
        "/api/copy",
        json={
            "project_id": project["id"],
            "product_asset_id": asset["id"],
            "product_scene_id": scene["id"],
            "copy_type": "instagram_caption",
            "tone": "luxury",
            "audience": "fashion shoppers",
            "prompt": "write a launch caption",
        },
    ).json()
    copy = _wait(client, f"/api/copy/{copy['id']}", "completed")

    video = client.post(
        "/api/videos",
        json={
            "project_id": project["id"],
            "product_scene_id": scene["id"],
            "prompt": "slow push in",
            "motion_preset": "slow_zoom",
            "duration_seconds": 3,
        },
    ).json()
    video = _wait(client, f"/api/videos/{video['id']}", "completed")

    resp = client.get("/api/library")
    assert resp.status_code == 200
    items = resp.json()
    by_id = {item["id"]: item for item in items}

    upload = by_id[f"upload:{asset['id']}"]
    assert upload["type"] == "upload"
    assert upload["project_name"] == "Library Project"
    assert upload["asset_url"] == asset["original_url"]

    processed_item = by_id[f"processed_asset:{asset['id']}"]
    assert processed_item["type"] == "processed_asset"
    assert processed_item["asset_url"] == processed["processed_url"]

    scene_item = by_id[f"scene:{scene['id']}"]
    assert scene_item["type"] == "scene"
    assert scene_item["download_url"] == f"/api/exports/scene/{scene['id']}"

    copy_item = by_id[f"copy:{copy['id']}"]
    assert copy_item["type"] == "copy"
    assert copy_item["description"] == copy["result_text"]
    assert copy_item["download_url"] == f"/api/exports/copy/{copy['id']}"

    video_item = by_id[f"video:{video['id']}"]
    assert video_item["type"] == "video"
    assert video_item["asset_url"] == video["result_url"]
    assert video_item["download_url"] == f"/api/exports/video/{video['id']}"


def test_library_sorts_newest_first(client):
    project = client.post(
        "/api/projects", json={"name": "Sort Project", "description": None}
    ).json()
    first = client.post(
        "/api/assets/upload",
        data={"project_id": project["id"]},
        files={"file": ("first.png", b"one", "image/png")},
    ).json()
    second = client.post(
        "/api/assets/upload",
        data={"project_id": project["id"]},
        files={"file": ("second.png", b"two", "image/png")},
    ).json()

    items = client.get("/api/library").json()
    ids = [item["id"] for item in items]
    assert ids.index(f"upload:{second['id']}") < ids.index(f"upload:{first['id']}")


def test_library_can_filter_by_project(client):
    first_project = client.post(
        "/api/projects", json={"name": "Library Filter A", "description": None}
    ).json()
    second_project = client.post(
        "/api/projects", json={"name": "Library Filter B", "description": None}
    ).json()
    first_asset = client.post(
        "/api/assets/upload",
        data={"project_id": first_project["id"]},
        files={"file": ("a.png", b"a", "image/png")},
    ).json()
    second_asset = client.post(
        "/api/assets/upload",
        data={"project_id": second_project["id"]},
        files={"file": ("b.png", b"b", "image/png")},
    ).json()

    items = client.get(
        f"/api/library?project_id={first_project['id']}"
    ).json()
    ids = {item["id"] for item in items}

    assert f"upload:{first_asset['id']}" in ids
    assert f"upload:{second_asset['id']}" not in ids
