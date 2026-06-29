"""Creative Director recommendation tests."""
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


def test_creative_director_returns_recommendations(client):
    project = client.post(
        "/api/projects", json={"name": "Director", "description": None}
    ).json()
    client.put(
        f"/api/projects/{project['id']}/brand-kit",
        json={"brand_voice": "premium", "target_audience": "fashion buyers"},
    )
    brief = client.post(
        f"/api/projects/{project['id']}/briefs",
        json={
            "title": "Director brief",
            "campaign_goal": "Launch a hero campaign",
            "target_channels": "Instagram, LinkedIn",
            "deliverables": "Scene and copy",
        },
    ).json()

    resp = client.post(
        "/api/creative-director/recommendations",
        json={"project_id": project["id"], "brief_id": brief["id"]},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == project["id"]
    assert body["brief_id"] == brief["id"]
    assert body["summary"]
    categories = {item["category"] for item in body["recommendations"]}
    assert {"campaign", "scene", "copy", "video", "audience"} <= categories
    assert all(0 <= item["confidence"] <= 1 for item in body["recommendations"])


def test_creative_director_invalid_project_and_brief(client):
    assert (
        client.post(
            "/api/creative-director/recommendations",
            json={"project_id": "nope"},
        ).status_code
        == 404
    )
    project = client.post(
        "/api/projects", json={"name": "Director 404", "description": None}
    ).json()
    assert (
        client.post(
            "/api/creative-director/recommendations",
            json={"project_id": project["id"], "brief_id": "nope"},
        ).status_code
        == 404
    )
