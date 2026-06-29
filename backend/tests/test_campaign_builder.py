"""One-click Campaign Builder tests (mock backends; no live ComfyUI)."""
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


def _project(client) -> str:
    return client.post(
        "/api/projects", json={"name": "Builder", "description": None}
    ).json()["id"]


def _brief(client, project_id, title="Spring Launch") -> str:
    return client.post(
        f"/api/projects/{project_id}/briefs",
        json={"title": title, "campaign_goal": "Sell the spring drop"},
    ).json()["id"]


def _asset(client, project_id) -> str:
    return client.post(
        "/api/assets/upload",
        data={"project_id": project_id},
        files={"file": ("item.png", b"bytes", "image/png")},
    ).json()["id"]


def _setup(client):
    project_id = _project(client)
    return project_id, _brief(client, project_id), _asset(client, project_id)


def test_product_launch_builds_full_bundle(client):
    project_id, brief_id, asset_id = _setup(client)
    resp = client.post(
        f"/api/projects/{project_id}/campaign-builder",
        json={
            "brief_id": brief_id,
            "asset_id": asset_id,
            "campaign_type": "product_launch",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["scene_count"] == 3
    assert body["copy_count"] == 3
    assert body["video_prompt_count"] == 1
    bundle = body["bundle"]
    assert bundle["campaign_type"] == "product_launch"
    assert "Spring Launch" in bundle["title"]
    assert len(bundle["scene_ids"]) == 3

    # The orchestrated jobs exist and reference the project.
    scenes = client.get(f"/api/product-scenes?project_id={project_id}").json()
    assert len(scenes) >= 3
    # Brief context flowed into a scene prompt.
    assert any("Creative brief:" in s["prompt"] for s in scenes)


@pytest.mark.parametrize(
    "campaign_type,scenes,copies",
    [
        ("ecommerce", 2, 2),
        ("social_media", 2, 2),
        ("fashion_editorial", 3, 1),
        ("luxury_brand", 2, 1),
        ("custom", 1, 1),
    ],
)
def test_each_template_counts(client, campaign_type, scenes, copies):
    project_id, brief_id, asset_id = _setup(client)
    body = client.post(
        f"/api/projects/{project_id}/campaign-builder",
        json={"brief_id": brief_id, "asset_id": asset_id, "campaign_type": campaign_type},
    ).json()
    assert body["scene_count"] == scenes
    assert body["copy_count"] == copies


def test_invalid_project_is_404(client):
    resp = client.post(
        "/api/projects/nope/campaign-builder",
        json={"brief_id": "x", "asset_id": "y", "campaign_type": "custom"},
    )
    assert resp.status_code == 404


def test_invalid_brief_is_404(client):
    project_id = _project(client)
    asset_id = _asset(client, project_id)
    resp = client.post(
        f"/api/projects/{project_id}/campaign-builder",
        json={"brief_id": "nope", "asset_id": asset_id, "campaign_type": "custom"},
    )
    assert resp.status_code == 404


def test_invalid_asset_is_404(client):
    project_id = _project(client)
    brief_id = _brief(client, project_id)
    resp = client.post(
        f"/api/projects/{project_id}/campaign-builder",
        json={"brief_id": brief_id, "asset_id": "nope", "campaign_type": "custom"},
    )
    assert resp.status_code == 404


def test_invalid_campaign_type_rejected(client):
    project_id, brief_id, asset_id = _setup(client)
    resp = client.post(
        f"/api/projects/{project_id}/campaign-builder",
        json={"brief_id": brief_id, "asset_id": asset_id, "campaign_type": "spaceship"},
    )
    assert resp.status_code == 422  # schema literal rejects unknown type


def test_workspace_includes_bundle(client):
    project_id, brief_id, asset_id = _setup(client)
    bundle_id = client.post(
        f"/api/projects/{project_id}/campaign-builder",
        json={"brief_id": brief_id, "asset_id": asset_id, "campaign_type": "custom"},
    ).json()["bundle_id"]
    workspace = client.get(f"/api/projects/{project_id}/workspace").json()
    assert any(b["id"] == bundle_id for b in workspace["campaign_bundles"])


def test_asset_library_includes_bundle(client):
    project_id, brief_id, asset_id = _setup(client)
    client.post(
        f"/api/projects/{project_id}/campaign-builder",
        json={"brief_id": brief_id, "asset_id": asset_id, "campaign_type": "custom"},
    )
    library = client.get(f"/api/library?project_id={project_id}").json()
    assert any(item["type"] == "campaign_bundle" for item in library)
