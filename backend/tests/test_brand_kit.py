"""Project brand kit tests."""
import os
import tempfile

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


def _project(client, name="Brand Project"):
    return client.post(
        "/api/projects", json={"name": name, "description": None}
    ).json()


def _asset(client, project_id):
    return client.post(
        "/api/assets/upload",
        data={"project_id": project_id},
        files={"file": ("brand.png", b"image", "image/png")},
    ).json()


def test_empty_brand_kit_returns_defaults(client):
    project = _project(client, "Empty Brand")

    resp = client.get(f"/api/projects/{project['id']}/brand-kit")

    assert resp.status_code == 200
    assert resp.json() == {
        "brand_name": None,
        "brand_voice": None,
        "target_audience": None,
        "primary_colors": None,
        "style_keywords": None,
        "negative_keywords": None,
        "product_positioning": None,
        "campaign_notes": None,
    }


def test_brand_kit_can_be_updated_and_workspace_includes_it(client):
    project = _project(client, "Brand Workspace")
    payload = {
        "brand_name": "Maison Atlas",
        "brand_voice": "luxury, refined, confident",
        "target_audience": "professionals",
        "primary_colors": "black, gold, ivory",
        "style_keywords": "minimal, architectural",
        "negative_keywords": "cartoon, cheap, cluttered",
        "product_positioning": "premium daily apparel",
        "campaign_notes": "Milan-inspired editorial direction",
    }

    update = client.put(f"/api/projects/{project['id']}/brand-kit", json=payload)
    workspace = client.get(f"/api/projects/{project['id']}/workspace")

    assert update.status_code == 200
    assert update.json() == payload
    assert workspace.status_code == 200
    assert workspace.json()["brand_kit"] == payload


def test_brand_kit_invalid_project_returns_404(client):
    assert client.get("/api/projects/nope/brand-kit").status_code == 404
    assert client.put("/api/projects/nope/brand-kit", json={}).status_code == 404


def test_generation_prompts_include_brand_context(client):
    project = _project(client, "Brand Prompt")
    asset = _asset(client, project["id"])
    client.put(
        f"/api/projects/{project['id']}/brand-kit",
        json={
            "brand_voice": "luxury, refined, confident",
            "target_audience": "professionals",
            "primary_colors": "black, gold, ivory",
            "negative_keywords": "cartoon, cheap, cluttered",
        },
    )

    scene = client.post(
        "/api/product-scenes",
        json={
            "project_id": project["id"],
            "asset_id": asset["id"],
            "prompt": "Create a boutique scene",
            "preset": "luxury",
        },
    ).json()
    copy = client.post(
        "/api/copy",
        json={
            "project_id": project["id"],
            "product_asset_id": asset["id"],
            "copy_type": "instagram_caption",
            "tone": "luxury",
            "audience": "shoppers",
            "prompt": "Launch caption",
        },
    ).json()
    campaign = client.post(
        "/api/campaigns/from-preset",
        json={
            "project_id": project["id"],
            "asset_id": asset["id"],
            "preset_id": "luxury_launch",
            "product_name": "Atlas Jacket",
        },
    ).json()

    for prompt in [
        scene["prompt"],
        copy["prompt"],
        campaign["scene_job"]["prompt"],
        campaign["copy_job"]["prompt"],
    ]:
        assert "Brand guidance:" in prompt
        assert "luxury, refined, confident" in prompt
        assert "black, gold, ivory" in prompt
        assert "cartoon, cheap, cluttered" in prompt
