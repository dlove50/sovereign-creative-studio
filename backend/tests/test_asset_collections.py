"""Asset collection and multi-asset campaign tests."""
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


def _project(client):
    return client.post(
        "/api/projects", json={"name": "Collection Project", "description": None}
    ).json()


def _asset(client, project_id, name):
    return client.post(
        "/api/assets/upload",
        data={"project_id": project_id},
        files={"file": (name, b"image", "image/png")},
    ).json()


def _brief(client, project_id):
    return client.post(
        f"/api/projects/{project_id}/briefs",
        json={"title": "Collection brief", "campaign_goal": "Launch collection"},
    ).json()


def test_collection_crud(client):
    project = _project(client)
    a1 = _asset(client, project["id"], "a.png")
    a2 = _asset(client, project["id"], "b.png")

    created = client.post(
        f"/api/projects/{project['id']}/collections",
        json={
            "name": "Hero products",
            "description": "Launch assets",
            "asset_ids": [a1["id"], a2["id"]],
        },
    )

    assert created.status_code == 201
    collection = created.json()
    assert collection["asset_ids"] == [a1["id"], a2["id"]]

    listed = client.get(f"/api/projects/{project['id']}/collections").json()
    assert any(item["id"] == collection["id"] for item in listed)

    updated = client.put(
        f"/api/projects/{project['id']}/collections/{collection['id']}",
        json={"name": "Updated", "asset_ids": [a1["id"]]},
    )
    assert updated.status_code == 200
    assert updated.json()["asset_ids"] == [a1["id"]]

    deleted = client.delete(
        f"/api/projects/{project['id']}/collections/{collection['id']}"
    )
    assert deleted.status_code == 204


def test_collection_campaign_creates_bundle_outputs(client, monkeypatch):
    from app.routers import collections as collection_router

    monkeypatch.setattr(collection_router, "enqueue_product_scene", lambda scene_id: None)
    monkeypatch.setattr(collection_router, "enqueue_copy", lambda copy_id: None)
    monkeypatch.setattr(collection_router, "enqueue_video", lambda video_id: None)

    project = _project(client)
    brief = _brief(client, project["id"])
    assets = [_asset(client, project["id"], "one.png"), _asset(client, project["id"], "two.png")]
    collection = client.post(
        f"/api/projects/{project['id']}/collections",
        json={
            "name": "Two products",
            "asset_ids": [asset["id"] for asset in assets],
        },
    ).json()

    resp = client.post(
        f"/api/projects/{project['id']}/collections/{collection['id']}/campaign",
        json={
            "brief_id": brief["id"],
            "collection_id": collection["id"],
            "campaign_type": "ecommerce",
        },
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["asset_count"] == 2
    assert body["scene_count"] == 4
    assert body["copy_count"] == 4
    assert body["bundle"]["selected_asset_id"] is None


def test_collection_errors_are_clean(client):
    assert client.get("/api/projects/nope/collections").status_code == 404
    project = _project(client)
    assert (
        client.post(
            f"/api/projects/{project['id']}/collections",
            json={"name": "Bad", "asset_ids": ["nope"]},
        ).status_code
        == 404
    )
