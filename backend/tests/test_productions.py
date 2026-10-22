"""Production pipeline tests."""
import os
import tempfile
import zipfile
from io import BytesIO

_TMP = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(_TMP, 'test.db')}")
os.environ.setdefault("STORAGE_DIR", os.path.join(_TMP, "storage"))
os.environ.setdefault("VIDEO_BACKEND", "mock")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        response = c.post("/api/admin/family-users", json={
            "display_name": "Production workspace tests", "role": "family_user", "initial_credits": 100,
        })
        assert response.status_code == 201, response.text
        c.headers["X-SCS-Family-User-Id"] = response.json()["id"]
        yield c


def _project(client):
    return client.post(
        "/api/projects", json={"name": "Production Project", "description": None}
    ).json()


def _storyboard_and_shot(client, project_id):
    storyboard = client.post(
        f"/api/projects/{project_id}/storyboards",
        json={"title": "Launch film", "description": "Three-shot sequence"},
    ).json()
    shot = client.post(
        f"/api/storyboards/{storyboard['id']}/shots",
        json={
            "shot_number": 1,
            "duration_seconds": 4,
            "description": "Hero opener",
            "generation_prompt": "Luxury product reveal",
        },
    ).json()
    return storyboard, shot


def _video(client, project_id):
    response = client.post(
        "/api/videos",
        json={
            "project_id": project_id,
            "mode": "text_to_video",
            "provider": "local_ltx",  # these tests are about productions, not which model is the default
            "prompt": "slow luxury product reveal",
            "motion_preset": "slow_zoom",
            "duration_seconds": 5,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _scene(client, project_id):
    asset = client.post(
        "/api/assets/upload",
        data={"project_id": project_id},
        files={"file": ("scene.png", b"bytes", "image/png")},
    ).json()
    return client.post(
        "/api/product-scenes",
        json={
            "project_id": project_id,
            "asset_id": asset["id"],
            "prompt": "Storyboard keyframe",
            "preset": "studio",
            "mode": "film_scene",
        },
    ).json()


def test_production_crud_workspace_and_export(client):
    project = _project(client)
    storyboard, shot = _storyboard_and_shot(client, project["id"])
    video = _video(client, project["id"])
    scene = _scene(client, project["id"])
    shot = client.put(
        f"/api/storyboards/{storyboard['id']}/shots/{shot['id']}",
        json={"product_scene_id": scene["id"], "video_id": video["id"]},
    ).json()

    created = client.post(
        f"/api/projects/{project['id']}/productions",
        json={
            "title": "Launch production",
            "description": "Storyboard to export package",
            "storyboard_ids": [storyboard["id"]],
            "shot_ids": [shot["id"]],
            "video_ids": [],
        },
    )
    assert created.status_code == 201
    production = created.json()
    assert production["storyboard_ids"] == [storyboard["id"]]

    listed = client.get(f"/api/projects/{project['id']}/productions").json()
    assert any(item["id"] == production["id"] for item in listed)

    workspace = client.get(
        f"/api/projects/{project['id']}/productions/{production['id']}"
    ).json()
    assert workspace["counts"]["storyboards"] == 1
    assert workspace["counts"]["shots"] == 1
    assert workspace["counts"]["videos"] == 1
    assert workspace["shots"][0]["generation_prompt"] == "Luxury product reveal"
    assert workspace["shots"][0]["product_scene_id"] == scene["id"]
    assert workspace["shots"][0]["video_id"] == video["id"]

    updated = client.put(
        f"/api/projects/{project['id']}/productions/{production['id']}",
        json={"status": "assembly", "video_ids": [video["id"]]},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "assembly"

    exported = client.post(
        f"/api/projects/{project['id']}/productions/{production['id']}/export"
    )
    assert exported.status_code == 200
    with zipfile.ZipFile(BytesIO(exported.content)) as zf:
        assert {
            "metadata.json",
            "storyboards.json",
            "shots.json",
            "videos.json",
            "sequence.txt",
            "keyframes.json",
        } <= set(zf.namelist())
        assert "Launch production" in zf.read("sequence.txt").decode("utf-8")
        assert "Storyboard keyframe" in zf.read("keyframes.json").decode("utf-8")

    workspace_after_export = client.get(
        f"/api/projects/{project['id']}/productions/{production['id']}"
    ).json()
    assert workspace_after_export["production"]["status"] == "exported"
    assert workspace_after_export["counts"]["exports"] == 1


def test_production_errors_are_clean(client):
    assert client.get("/api/projects/nope/productions").status_code == 404
    project = _project(client)
    bad = client.post(
        f"/api/projects/{project['id']}/productions",
        json={"title": "Bad refs", "storyboard_ids": ["missing"]},
    )
    assert bad.status_code == 404

    empty = client.post(
        f"/api/projects/{project['id']}/productions",
        json={"title": "Empty production"},
    ).json()
    assert (
        client.get(f"/api/projects/{project['id']}/productions/{empty['id']}")
        .json()["counts"]["videos"]
        == 0
    )
    assert client.delete(f"/api/projects/{project['id']}/productions/{empty['id']}").status_code == 204
