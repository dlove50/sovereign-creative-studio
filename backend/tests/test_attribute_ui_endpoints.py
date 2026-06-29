"""Attribute Editor UI endpoints: mask preview + save-result-to-asset-library."""
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


def _project_asset(client):
    pid = client.post("/api/projects", json={"name": "AttrUI", "description": None}).json()["id"]
    asset = client.post(
        "/api/assets/upload",
        data={"project_id": pid},
        files={"file": ("m.png", b"bytes", "image/png")},
    ).json()
    return pid, asset["id"]


def test_mask_preview_humanparse_route(client):
    _, asset_id = _project_asset(client)
    r = client.post(
        "/api/product-scenes/mask-preview",
        json={"asset_id": asset_id, "target_attribute": "pants"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["route"] == "human-parse"
    # mock backend returns a placeholder mask image url.
    assert body["mask_url"] and body["mask_url"].startswith("/storage/mask-previews/")


def test_mask_preview_shirt_is_manual(client):
    _, asset_id = _project_asset(client)
    r = client.post(
        "/api/product-scenes/mask-preview",
        json={"asset_id": asset_id, "target_attribute": "shirt"},
    ).json()
    assert r["route"] == "manual-mask"
    assert r["mask_url"] is None  # ambiguous -> client previews the manual mask


def test_mask_preview_open_vocab_route(client):
    _, asset_id = _project_asset(client)
    r = client.post(
        "/api/product-scenes/mask-preview",
        json={"asset_id": asset_id, "target_attribute": "tie"},
    ).json()
    assert r["route"] == "groundingdino-sam"


def test_save_scene_as_asset(client):
    pid, asset_id = _project_asset(client)
    scene = client.post(
        "/api/product-scenes",
        json={
            "project_id": pid,
            "asset_id": asset_id,
            "prompt": "change pants to black",
            "preset": "studio",
            "mode": "attribute_edit",
            "target_attribute": "pants",
        },
    ).json()
    sid = scene["id"]
    for _ in range(60):
        s = client.get(f"/api/product-scenes/{sid}").json()
        if s["status"] in ("completed", "failed"):
            break
        time.sleep(0.05)
    assert s["status"] == "completed"
    saved = client.post(f"/api/assets/from-scene/{sid}")
    assert saved.status_code == 201
    body = saved.json()
    assert body["status"] == "completed"
    assert body["original_url"] == s["result_url"]


def test_save_scene_unknown_404(client):
    assert client.post("/api/assets/from-scene/nope").status_code == 404
