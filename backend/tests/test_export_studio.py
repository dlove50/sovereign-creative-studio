"""Export Studio package tests."""
import io
import os
import tempfile
import time
import zipfile

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


def _project_package(client):
    project = client.post(
        "/api/projects", json={"name": "Export Studio", "description": None}
    ).json()
    client.put(
        f"/api/projects/{project['id']}/brand-kit",
        json={"brand_name": "Atlas", "brand_voice": "premium"},
    )
    brief = client.post(
        f"/api/projects/{project['id']}/briefs",
        json={
            "title": "Launch brief",
            "campaign_goal": "Launch the collection",
            "target_channels": "Instagram, LinkedIn",
            "deliverables": "Scene, copy, video prompt",
            "status": "draft",
        },
    ).json()
    asset = client.post(
        "/api/assets/upload",
        data={"project_id": project["id"]},
        files={"file": ("thing.png", b"asset", "image/png")},
    ).json()
    scene = client.post(
        "/api/product-scenes",
        json={
            "project_id": project["id"],
            "asset_id": asset["id"],
            "prompt": "premium launch scene",
            "preset": "luxury",
            "brief_id": brief["id"],
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
            "audience": "buyers",
            "prompt": "launch caption",
            "brief_id": brief["id"],
        },
    ).json()
    copy = _wait(client, f"/api/copy/{copy['id']}", "completed")
    video = client.post(
        "/api/videos",
        json={
            "project_id": project["id"],
            "product_scene_id": scene["id"],
            "prompt": "slow reveal",
            "motion_preset": "slow_zoom",
            "duration_seconds": 3,
            "brief_id": brief["id"],
        },
    ).json()
    _wait(client, f"/api/videos/{video['id']}", "completed")
    return project, brief


def _zip_names(response):
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        return set(zf.namelist())


def test_social_bundle_contains_platform_packages(client):
    project, brief = _project_package(client)
    resp = client.post(
        "/api/exports/social-bundle",
        json={
            "project_id": project["id"],
            "brief_id": brief["id"],
            "platforms": ["instagram", "linkedin"],
        },
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    names = _zip_names(resp)
    assert "metadata.json" in names
    assert "brief.txt" in names
    assert "brand-kit.json" in names
    assert "social/instagram/metadata.json" in names
    assert "social/linkedin/metadata.json" in names
    assert any(name.startswith("copy/") for name in names)
    assert any(name.startswith("images/") for name in names)
    assert any(name.startswith("video-prompts/") for name in names)


def test_marketing_bundle_validates_project(client):
    resp = client.post(
        "/api/exports/marketing-bundle",
        json={"project_id": "nope", "platforms": []},
    )
    assert resp.status_code == 404


def test_marketing_bundle_contains_project_metadata(client):
    project, brief = _project_package(client)
    resp = client.post(
        "/api/exports/marketing-bundle",
        json={"project_id": project["id"], "brief_id": brief["id"]},
    )

    assert resp.status_code == 200
    names = _zip_names(resp)
    assert "metadata.json" in names
    assert "brief.txt" in names
    assert "brand-kit.json" in names
    assert any(name.startswith("prompts/") for name in names)
