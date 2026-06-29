"""Export endpoint tests: scene image, copy text, campaign bundle zip."""
import io
import json
import os
import tempfile
import time
import zipfile

_TMP = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(_TMP, 'test.db')}")
os.environ.setdefault("STORAGE_DIR", os.path.join(_TMP, "storage"))
os.environ.setdefault("GENERATOR_BACKEND", "mock")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ProductSceneGeneration  # noqa: E402


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


def _completed_scene_and_copy(client):
    project_id = client.post(
        "/api/projects", json={"name": "Export", "description": None}
    ).json()["id"]
    asset = client.post(
        "/api/assets/upload",
        data={"project_id": project_id},
        files={"file": ("thing.png", b"bytes", "image/png")},
    ).json()
    scene = client.post(
        "/api/product-scenes",
        json={
            "project_id": project_id,
            "asset_id": asset["id"],
            "prompt": "thing on marble",
            "preset": "studio",
        },
    ).json()
    _wait(client, f"/api/product-scenes/{scene['id']}", "completed")
    copy = client.post(
        "/api/copy",
        json={
            "project_id": project_id,
            "copy_type": "seo_title",
            "tone": "professional",
            "prompt": "thing",
        },
    ).json()
    _wait(client, f"/api/copy/{copy['id']}", "completed")
    return project_id, asset, scene, copy


def test_export_scene_returns_image_attachment(client):
    _, _, scene, _ = _completed_scene_and_copy(client)
    resp = client.get(f"/api/exports/scene/{scene['id']}")
    assert resp.status_code == 200
    assert "attachment" in resp.headers.get("content-disposition", "")
    assert resp.content  # non-empty image bytes


def test_export_copy_returns_text_attachment(client):
    _, _, _, copy = _completed_scene_and_copy(client)
    resp = client.get(f"/api/exports/copy/{copy['id']}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "attachment" in resp.headers.get("content-disposition", "")
    # Body matches the generated copy.
    current = client.get(f"/api/copy/{copy['id']}").json()
    assert resp.text == current["result_text"]


def test_campaign_bundle_contains_image_copy_and_metadata(client):
    project_id, asset, scene, copy = _completed_scene_and_copy(client)
    resp = client.post(
        "/api/exports/campaign-bundle",
        json={"scene_id": scene["id"], "copy_id": copy["id"]},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = zf.namelist()
        assert "metadata.json" in names
        assert "copy.txt" in names
        assert any(n.startswith("scene") for n in names)

        meta = json.loads(zf.read("metadata.json"))
        assert meta["project"]["id"] == project_id
        assert meta["asset"]["id"] == asset["id"]
        assert meta["scene"]["id"] == scene["id"]
        assert meta["copy"]["id"] == copy["id"]


def test_campaign_bundle_requires_at_least_one_id(client):
    resp = client.post("/api/exports/campaign-bundle", json={})
    assert resp.status_code == 400


def test_export_unknown_scene_is_404(client):
    assert client.get("/api/exports/scene/nope").status_code == 404


def test_export_not_completed_scene_is_409(client):
    project_id = client.post(
        "/api/projects", json={"name": "Pending", "description": None}
    ).json()["id"]
    asset = client.post(
        "/api/assets/upload",
        data={"project_id": project_id},
        files={"file": ("p.png", b"bytes", "image/png")},
    ).json()
    user_id = client.get("/api/me").json()["id"]

    # Insert a queued (never-run) scene directly so the state is deterministic.
    with SessionLocal() as db:
        scene = ProductSceneGeneration(
            user_id=user_id,
            project_id=project_id,
            asset_id=asset["id"],
            prompt="pending",
            preset="studio",
            status="queued",
        )
        db.add(scene)
        db.commit()
        scene_id = scene.id

    resp = client.get(f"/api/exports/scene/{scene_id}")
    assert resp.status_code == 409


def test_export_scene_with_missing_file_is_404(client):
    _, _, scene, _ = _completed_scene_and_copy(client)
    # Delete the underlying file, leaving the DB row "completed".
    current = client.get(f"/api/product-scenes/{scene['id']}").json()
    rel = current["result_url"].removeprefix("/storage/")
    os.remove(os.path.join(os.environ["STORAGE_DIR"], rel))

    resp = client.get(f"/api/exports/scene/{scene['id']}")
    assert resp.status_code == 404
