"""Campaign preset + from-preset tests."""
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

EXPECTED_PRESET_IDS = {
    "luxury_launch",
    "instagram_product_ad",
    "black_friday",
    "minimalist_studio",
    "outdoor_lifestyle",
}
PRESET_FIELDS = {
    "id",
    "name",
    "description",
    "scene_preset",
    "scene_mode",
    "scene_prompt_template",
    "copy_type",
    "tone",
    "audience_hint",
}


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


def _project_and_asset(client):
    project_id = client.post(
        "/api/projects", json={"name": "Campaign", "description": None}
    ).json()["id"]
    asset = client.post(
        "/api/assets/upload",
        data={"project_id": project_id},
        files={"file": ("item.png", b"bytes", "image/png")},
    ).json()
    return project_id, asset["id"]


def _brief(client, project_id, **overrides):
    payload = {"title": "Campaign brief", "campaign_goal": "Sell the spring bundle"}
    payload.update(overrides)
    return client.post(f"/api/projects/{project_id}/briefs", json=payload).json()


def test_campaign_with_brief_appends_context(client):
    project_id, asset_id = _project_and_asset(client)
    brief = _brief(client, project_id, campaign_goal="Promote the limited drop")
    resp = client.post(
        "/api/campaigns/from-preset",
        json={
            "project_id": project_id,
            "asset_id": asset_id,
            "preset_id": "instagram_product_ad",
            "product_name": "glow serum",
            "brief_id": brief["id"],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    # Brief context lands in both the scene and copy prompts.
    assert "Creative brief:" in body["scene_job"]["prompt"]
    assert "Promote the limited drop" in body["scene_job"]["prompt"]
    assert "Creative brief:" in body["copy_job"]["prompt"]


def test_campaign_with_invalid_brief_is_404(client):
    project_id, asset_id = _project_and_asset(client)
    resp = client.post(
        "/api/campaigns/from-preset",
        json={
            "project_id": project_id,
            "asset_id": asset_id,
            "preset_id": "black_friday",
            "brief_id": "does-not-exist",
        },
    )
    assert resp.status_code == 404


def test_list_presets(client):
    resp = client.get("/api/presets")
    assert resp.status_code == 200
    presets = resp.json()
    assert {p["id"] for p in presets} == EXPECTED_PRESET_IDS
    for preset in presets:
        assert PRESET_FIELDS <= set(preset)


def test_get_preset(client):
    resp = client.get("/api/presets/luxury_launch")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scene_preset"] == "luxury"
    assert body["copy_type"] == "product_description"


def test_get_unknown_preset_is_404(client):
    assert client.get("/api/presets/nope").status_code == 404


def test_from_preset_creates_linked_scene_and_copy(client):
    project_id, asset_id = _project_and_asset(client)
    resp = client.post(
        "/api/campaigns/from-preset",
        json={
            "project_id": project_id,
            "asset_id": asset_id,
            "preset_id": "instagram_product_ad",
            "product_name": "glow serum",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["preset_id"] == "instagram_product_ad"

    scene = body["scene_job"]
    copy = body["copy_job"]
    # Scene reflects the preset and the product name is injected into the prompt.
    assert scene["preset"] == "social ad"
    assert scene["mode"] == "img2img"
    assert "glow serum" in scene["prompt"]
    # Copy reflects the preset and is linked to the scene + asset.
    assert copy["copy_type"] == "instagram_caption"
    assert copy["tone"] == "playful"
    assert copy["product_scene_id"] == scene["id"]
    assert copy["product_asset_id"] == asset_id

    # Both jobs run to completion on the mock backends.
    _wait(client, f"/api/product-scenes/{scene['id']}", "completed")
    done_copy = _wait(client, f"/api/copy/{copy['id']}", "completed")
    assert done_copy["result_text"]


def test_from_preset_without_product_name_uses_default(client):
    project_id, asset_id = _project_and_asset(client)
    body = client.post(
        "/api/campaigns/from-preset",
        json={
            "project_id": project_id,
            "asset_id": asset_id,
            "preset_id": "minimalist_studio",
        },
    ).json()
    assert "your product" in body["scene_job"]["prompt"]


def test_from_preset_unknown_preset_is_404(client):
    project_id, asset_id = _project_and_asset(client)
    resp = client.post(
        "/api/campaigns/from-preset",
        json={"project_id": project_id, "asset_id": asset_id, "preset_id": "nope"},
    )
    assert resp.status_code == 404


def test_from_preset_unknown_asset_is_404(client):
    project_id = client.post(
        "/api/projects", json={"name": "C2", "description": None}
    ).json()["id"]
    resp = client.post(
        "/api/campaigns/from-preset",
        json={
            "project_id": project_id,
            "asset_id": "does-not-exist",
            "preset_id": "black_friday",
        },
    )
    assert resp.status_code == 404
