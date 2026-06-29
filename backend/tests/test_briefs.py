"""Creative brief CRUD, workspace inclusion, and lightweight generation
integration."""
import os
import tempfile

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
        "/api/projects", json={"name": "Brief project", "description": None}
    ).json()["id"]


def _brief_payload(**overrides):
    payload = {
        "title": "Spring Launch",
        "campaign_goal": "Drive pre-orders for the spring collection",
        "target_channels": "Instagram, TikTok, email",
        "deliverables": "3 scenes, 2 captions, 1 video",
        "key_messages": "Fresh, bold, limited run",
        "creative_direction": "Bright daylight, pastel palette",
        "reference_notes": "See last year's launch deck",
        "selected_asset_ids": [],
        "status": "draft",
    }
    payload.update(overrides)
    return payload


def test_create_and_get_brief(client):
    project_id = _project(client)
    resp = client.post(
        f"/api/projects/{project_id}/briefs", json=_brief_payload()
    )
    assert resp.status_code == 201
    brief = resp.json()
    assert brief["title"] == "Spring Launch"
    assert brief["status"] == "draft"
    assert brief["project_id"] == project_id

    got = client.get(f"/api/projects/{project_id}/briefs/{brief['id']}")
    assert got.status_code == 200
    assert got.json()["campaign_goal"] == "Drive pre-orders for the spring collection"


def test_list_briefs(client):
    project_id = _project(client)
    client.post(f"/api/projects/{project_id}/briefs", json=_brief_payload(title="A"))
    client.post(f"/api/projects/{project_id}/briefs", json=_brief_payload(title="B"))
    listed = client.get(f"/api/projects/{project_id}/briefs").json()
    assert {b["title"] for b in listed} >= {"A", "B"}


def test_update_brief(client):
    project_id = _project(client)
    brief = client.post(
        f"/api/projects/{project_id}/briefs", json=_brief_payload()
    ).json()
    resp = client.put(
        f"/api/projects/{project_id}/briefs/{brief['id']}",
        json={"status": "approved", "campaign_goal": "Updated goal"},
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["status"] == "approved"
    assert updated["campaign_goal"] == "Updated goal"
    # Untouched field preserved (partial update).
    assert updated["title"] == "Spring Launch"


def test_delete_brief(client):
    project_id = _project(client)
    brief = client.post(
        f"/api/projects/{project_id}/briefs", json=_brief_payload()
    ).json()
    resp = client.delete(f"/api/projects/{project_id}/briefs/{brief['id']}")
    assert resp.status_code == 204
    assert (
        client.get(f"/api/projects/{project_id}/briefs/{brief['id']}").status_code
        == 404
    )


def test_workspace_includes_briefs(client):
    project_id = _project(client)
    brief = client.post(
        f"/api/projects/{project_id}/briefs", json=_brief_payload(title="In workspace")
    ).json()
    workspace = client.get(f"/api/projects/{project_id}/workspace").json()
    assert any(b["id"] == brief["id"] for b in workspace["creative_briefs"])


def test_brief_on_missing_project_is_404(client):
    assert client.get("/api/projects/nope/briefs").status_code == 404
    assert (
        client.post("/api/projects/nope/briefs", json=_brief_payload()).status_code
        == 404
    )


def test_missing_brief_is_404(client):
    project_id = _project(client)
    assert (
        client.get(f"/api/projects/{project_id}/briefs/nope").status_code == 404
    )
    assert (
        client.put(
            f"/api/projects/{project_id}/briefs/nope", json={"status": "approved"}
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/projects/{project_id}/briefs/nope").status_code == 404
    )


# --- lightweight generation integration --------------------------------------
def test_scene_with_brief_appends_context(client):
    project_id = _project(client)
    asset = client.post(
        "/api/assets/upload",
        data={"project_id": project_id},
        files={"file": ("p.png", b"bytes", "image/png")},
    ).json()
    brief = client.post(
        f"/api/projects/{project_id}/briefs",
        json=_brief_payload(campaign_goal="Sell the spring bundle"),
    ).json()

    scene = client.post(
        "/api/product-scenes",
        json={
            "project_id": project_id,
            "asset_id": asset["id"],
            "prompt": "product on marble",
            "preset": "studio",
            "brief_id": brief["id"],
        },
    )
    assert scene.status_code == 201
    stored_prompt = scene.json()["prompt"]
    assert "Creative brief:" in stored_prompt
    assert "Sell the spring bundle" in stored_prompt


def test_copy_with_invalid_brief_is_404(client):
    project_id = _project(client)
    resp = client.post(
        "/api/copy",
        json={
            "project_id": project_id,
            "copy_type": "instagram_caption",
            "tone": "playful",
            "prompt": "x",
            "brief_id": "does-not-exist",
        },
    )
    assert resp.status_code == 404
