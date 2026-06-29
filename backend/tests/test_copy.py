"""AI Copy Studio tests: mock template generator + API flow."""
import os
import tempfile
import time

# Configure a throwaway DB/storage before importing the app (shared with other
# modules via setdefault if they imported first).
_TMP = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(_TMP, 'test.db')}")
os.environ.setdefault("STORAGE_DIR", os.path.join(_TMP, "storage"))
os.environ.setdefault("GENERATOR_BACKEND", "mock")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.copy_generators.mock import build_copy  # noqa: E402
from app.main import app  # noqa: E402

COPY_TYPES = [
    "product_description",
    "instagram_caption",
    "facebook_ad",
    "tiktok_hook",
    "seo_title",
]


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _wait_for_copy(client, copy_id, status, timeout=5.0):
    deadline = time.time() + timeout
    latest = None
    while time.time() < deadline:
        latest = client.get(f"/api/copy/{copy_id}").json()
        if latest["status"] == status:
            return latest
        time.sleep(0.05)
    raise AssertionError(f"Copy {copy_id} did not reach {status}: {latest}")


def _project(client) -> str:
    return client.post(
        "/api/projects", json={"name": "Copy project", "description": None}
    ).json()["id"]


# --- mock generator unit tests ----------------------------------------------
@pytest.mark.parametrize("copy_type", COPY_TYPES)
def test_build_copy_produces_text_for_each_type(copy_type):
    text = build_copy(
        copy_type=copy_type,
        tone="luxury",
        audience="busy parents",
        prompt="ceramic coffee mug",
        product_context=None,
    )
    assert isinstance(text, str) and text.strip()


def test_seo_title_is_capped_at_60_chars():
    text = build_copy(
        copy_type="seo_title",
        tone="bold",
        audience="runners everywhere who want the very best gear today",
        prompt="ultralight trail running shoe",
        product_context=None,
    )
    assert len(text) <= 60


def test_build_copy_reflects_tone_and_audience():
    text = build_copy(
        copy_type="product_description",
        tone="luxury",
        audience="collectors",
        prompt="leather wallet",
        product_context="Product image: wallet.png",
    )
    assert "collectors" in text
    assert "exquisite" in text  # luxury tone adjective
    assert "wallet.png" in text  # product context woven in


# --- API tests ---------------------------------------------------------------
def test_create_copy_completes(client):
    project_id = _project(client)
    resp = client.post(
        "/api/copy",
        json={
            "project_id": project_id,
            "copy_type": "instagram_caption",
            "tone": "playful",
            "audience": "gen z shoppers",
            "prompt": "neon water bottle",
        },
    )
    assert resp.status_code == 201
    created = resp.json()
    assert created["status"] == "queued"

    done = _wait_for_copy(client, created["id"], "completed")
    assert done["result_text"]
    assert "neon water bottle" in done["result_text"]

    listed = client.get("/api/copy").json()
    assert any(item["id"] == created["id"] for item in listed)


def test_create_copy_links_product_asset(client):
    project_id = _project(client)
    asset = client.post(
        "/api/assets/upload",
        data={"project_id": project_id},
        files={"file": ("mug.png", b"bytes", "image/png")},
    ).json()

    created = client.post(
        "/api/copy",
        json={
            "project_id": project_id,
            "product_asset_id": asset["id"],
            "copy_type": "product_description",
            "tone": "professional",
            "audience": "office teams",
            "prompt": "insulated mug",
        },
    ).json()
    done = _wait_for_copy(client, created["id"], "completed")
    assert done["product_asset_id"] == asset["id"]
    # The stored filename (asset.filename) is woven into the copy as context.
    assert asset["filename"] in done["result_text"]


def test_copy_without_audience_is_allowed(client):
    project_id = _project(client)
    created = client.post(
        "/api/copy",
        json={
            "project_id": project_id,
            "copy_type": "tiktok_hook",
            "tone": "bold",
            "prompt": "wireless earbuds",
        },
    )
    assert created.status_code == 201
    done = _wait_for_copy(client, created.json()["id"], "completed")
    assert done["audience"] is None
    assert done["result_text"]


def test_empty_prompt_rejected(client):
    project_id = _project(client)
    resp = client.post(
        "/api/copy",
        json={
            "project_id": project_id,
            "copy_type": "seo_title",
            "tone": "friendly",
            "prompt": "",
        },
    )
    assert resp.status_code == 422


def test_invalid_copy_type_rejected(client):
    project_id = _project(client)
    resp = client.post(
        "/api/copy",
        json={
            "project_id": project_id,
            "copy_type": "haiku",
            "tone": "friendly",
            "prompt": "a thing",
        },
    )
    assert resp.status_code == 422


def test_copy_to_missing_project_is_404(client):
    resp = client.post(
        "/api/copy",
        json={
            "project_id": "nope",
            "copy_type": "facebook_ad",
            "tone": "friendly",
            "prompt": "a thing",
        },
    )
    assert resp.status_code == 404


def test_copy_with_missing_asset_is_404(client):
    project_id = _project(client)
    resp = client.post(
        "/api/copy",
        json={
            "project_id": project_id,
            "product_asset_id": "does-not-exist",
            "copy_type": "facebook_ad",
            "tone": "friendly",
            "prompt": "a thing",
        },
    )
    assert resp.status_code == 404
