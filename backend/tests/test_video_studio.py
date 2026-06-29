"""Phase C11: video modes (incl. text->video), storyboards, shots."""
import os
import tempfile
import time

_TMP = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(_TMP, 'test.db')}")
os.environ.setdefault("STORAGE_DIR", os.path.join(_TMP, "storage"))
os.environ.setdefault("GENERATOR_BACKEND", "mock")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _fund_users():
    # Video generations now cost credits; keep the shared test user funded so
    # these functional mode/storyboard tests are not starved by the charge.
    from app.database import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        for user in db.query(User).all():
            user.credits = 100000
        db.commit()


def _project(client) -> str:
    return client.post(
        "/api/projects", json={"name": "Studio", "description": None}
    ).json()["id"]


def _wait(client, path, status, timeout=5.0):
    deadline = time.time() + timeout
    latest = None
    while time.time() < deadline:
        latest = client.get(path).json()
        if latest["status"] == status:
            return latest
        time.sleep(0.05)
    raise AssertionError(f"{path} did not reach {status}: {latest}")


# --- video modes -------------------------------------------------------------
def test_video_modes_registry(client):
    modes = client.get("/api/videos/modes").json()
    ids = {m["id"] for m in modes}
    assert {
        "image_to_video",
        "text_to_video",
        "video_to_video",
        "video_extension",
        "video_upscale",
    } <= ids
    text_mode = next(m for m in modes if m["id"] == "text_to_video")
    assert text_mode["source_required"] is False
    # Mock backend (test default) makes every mode available.
    assert all(m["available"] for m in modes)


def test_text_to_video_needs_no_source(client):
    project_id = _project(client)
    resp = client.post(
        "/api/videos",
        json={
            "project_id": project_id,
            "prompt": "a neon city skyline at night",
            "motion_preset": "slow_zoom",
            "duration_seconds": 4,
            "mode": "text_to_video",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["mode"] == "text_to_video"
    done = _wait(client, f"/api/videos/{body['id']}", "completed")
    assert done["result_url"].endswith(".html")


def test_non_text_mode_requires_source(client):
    project_id = _project(client)
    resp = client.post(
        "/api/videos",
        json={
            "project_id": project_id,
            "prompt": "restyle this",
            "motion_preset": "orbit",
            "duration_seconds": 4,
            "mode": "video_to_video",
        },
    )
    assert resp.status_code == 400


def test_invalid_video_mode_rejected(client):
    project_id = _project(client)
    resp = client.post(
        "/api/videos",
        json={
            "project_id": project_id,
            "source_image_url": "/storage/x.png",
            "prompt": "x",
            "motion_preset": "orbit",
            "duration_seconds": 4,
            "mode": "teleport",
        },
    )
    assert resp.status_code == 422


def test_image_to_video_default_mode_still_works(client):
    project_id = _project(client)
    resp = client.post(
        "/api/videos",
        json={
            "project_id": project_id,
            "source_image_url": "/storage/product-scenes/x.svg",
            "prompt": "slow push",
            "motion_preset": "slow_zoom",
            "duration_seconds": 5,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["mode"] == "image_to_video"


# --- storyboards + shots -----------------------------------------------------
def test_storyboard_crud_and_shots(client):
    project_id = _project(client)
    board = client.post(
        f"/api/projects/{project_id}/storyboards",
        json={"title": "Launch film", "description": "30s teaser"},
    ).json()
    assert board["title"] == "Launch film"

    listed = client.get(f"/api/projects/{project_id}/storyboards").json()
    assert any(b["id"] == board["id"] for b in listed)

    updated = client.put(
        f"/api/projects/{project_id}/storyboards/{board['id']}",
        json={"status": "approved"},
    ).json()
    assert updated["status"] == "approved"

    # Shots
    shot = client.post(
        f"/api/storyboards/{board['id']}/shots",
        json={
            "shot_number": 1,
            "duration_seconds": 4,
            "description": "Opening hero shot",
            "camera_notes": "slow dolly in",
            "generation_prompt": "product on marble, dramatic light",
        },
    ).json()
    assert shot["shot_number"] == 1

    shots = client.get(f"/api/storyboards/{board['id']}/shots").json()
    assert len(shots) == 1

    client.put(
        f"/api/storyboards/{board['id']}/shots/{shot['id']}",
        json={"duration_seconds": 6},
    )
    assert client.get(
        f"/api/storyboards/{board['id']}/shots"
    ).json()[0]["duration_seconds"] == 6

    assert (
        client.delete(f"/api/storyboards/{board['id']}/shots/{shot['id']}").status_code
        == 204
    )
    assert client.get(f"/api/storyboards/{board['id']}/shots").json() == []


def test_shot_can_store_scene_and_video_links(client):
    project_id = _project(client)
    board = client.post(
        f"/api/projects/{project_id}/storyboards",
        json={"title": "Linked board"},
    ).json()
    asset = client.post(
        "/api/assets/upload",
        data={"project_id": project_id},
        files={"file": ("hero.png", b"bytes", "image/png")},
    ).json()
    scene = client.post(
        "/api/product-scenes",
        json={
            "project_id": project_id,
            "asset_id": asset["id"],
            "prompt": "cinematic keyframe",
            "preset": "studio",
            "mode": "film_scene",
        },
    ).json()
    video = client.post(
        "/api/videos",
        json={
            "project_id": project_id,
            "source_image_url": "/storage/product-scenes/keyframe.png",
            "prompt": "cinematic push",
            "motion_preset": "cinematic_push",
            "duration_seconds": 3,
        },
    ).json()

    shot = client.post(
        f"/api/storyboards/{board['id']}/shots",
        json={
            "shot_number": 1,
            "description": "Linked shot",
            "product_scene_id": scene["id"],
            "video_id": video["id"],
        },
    ).json()
    assert shot["product_scene_id"] == scene["id"]
    assert shot["video_id"] == video["id"]

    updated = client.put(
        f"/api/storyboards/{board['id']}/shots/{shot['id']}",
        json={"video_id": None},
    ).json()
    assert updated["product_scene_id"] == scene["id"]
    assert updated["video_id"] is None


def test_storyboard_invalid_project_404(client):
    assert client.get("/api/projects/nope/storyboards").status_code == 404


def test_shots_invalid_storyboard_404(client):
    assert client.get("/api/storyboards/nope/shots").status_code == 404


def test_delete_storyboard_removes_it(client):
    project_id = _project(client)
    board = client.post(
        f"/api/projects/{project_id}/storyboards", json={"title": "Temp"}
    ).json()
    assert (
        client.delete(
            f"/api/projects/{project_id}/storyboards/{board['id']}"
        ).status_code
        == 204
    )
    assert (
        client.get(
            f"/api/projects/{project_id}/storyboards/{board['id']}"
        ).status_code
        == 404
    )


def test_storyboard_export_includes_ordered_shots(client):
    project_id = _project(client)
    board = client.post(
        f"/api/projects/{project_id}/storyboards",
        json={"title": "Editorial Sequence", "description": "Three-shot plan"},
    ).json()
    client.post(
        f"/api/storyboards/{board['id']}/shots",
        json={
            "shot_number": 2,
            "duration_seconds": 5,
            "description": "Boutique entrance",
            "camera_notes": "tracking move",
            "generation_prompt": "model walking into Milan boutique",
        },
    )
    client.post(
        f"/api/storyboards/{board['id']}/shots",
        json={
            "shot_number": 1,
            "duration_seconds": 3,
            "description": "Hero closeup",
            "camera_notes": "dolly in",
            "generation_prompt": "preserve same person and outfit",
        },
    )

    resp = client.get(f"/api/projects/{project_id}/storyboards/{board['id']}/export")
    assert resp.status_code == 200
    assert "attachment" in resp.headers.get("content-disposition", "")
    text = resp.text
    assert "Editorial Sequence" in text
    assert text.index("1. Hero closeup") < text.index("2. Boutique entrance")
    assert "preserve same person and outfit" in text
