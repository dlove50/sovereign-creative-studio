"""End-to-end API tests against the mock generator (no GPU required).

Env is pointed at a throwaway temp DB/storage *before* importing the app so the
module-level engine/config pick it up."""
import os
import tempfile
import time

_TMP = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")
os.environ["GENERATOR_BACKEND"] = "mock"
os.environ["DEFAULT_CREDITS"] = "100"
os.environ["CREDITS_PER_GENERATION"] = "5"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.services.generation_jobs as generation_jobs  # noqa: E402
import app.services.asset_jobs as asset_jobs  # noqa: E402
import app.services.product_scene_jobs as product_scene_jobs  # noqa: E402
from app.generators.base import GenerationResult  # noqa: E402
from app.product_scene_generators.base import ProductSceneResult  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    # Context-manager form runs the lifespan (create tables + seed demo user).
    with TestClient(app) as c:
        yield c


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_me_returns_seeded_owner_admin(client):
    # The local owner fallback resolves to David, the single owner/admin.
    resp = client.get("/api/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "david"
    assert body["name"] == "David"
    assert body["role"] == "owner_admin"
    assert body["credits"] == 100


def _wait_for_generation(client, generation_id, status, timeout=5):
    deadline = time.time() + timeout
    latest = None
    while time.time() < deadline:
        latest = client.get(f"/api/generations/{generation_id}").json()
        if latest["status"] == status:
            return latest
        time.sleep(0.05)
    raise AssertionError(f"Generation {generation_id} did not reach {status}: {latest}")


def test_create_generation_queues_then_completes_asset_and_charges_credits(client):
    before = client.get("/api/me").json()["credits"]

    resp = client.post(
        "/api/generations",
        json={"prompt": "a neon skyline at dusk", "media_type": "image"},
    )
    assert resp.status_code == 201
    gen = resp.json()
    assert gen["status"] == "queued"
    assert gen["file_url"] is None
    assert gen["credits_cost"] == 0

    gen = _wait_for_generation(client, gen["id"], "completed")
    assert gen["status"] == "completed"
    assert gen["file_url"].endswith(".svg")
    assert gen["credits_cost"] == 5

    filename = gen["file_url"].split("/")[-1]
    assert os.path.exists(os.path.join(os.environ["STORAGE_DIR"], filename))

    after = client.get("/api/me").json()["credits"]
    assert after == before - 5

    listed = client.get("/api/generations").json()
    assert any(g["id"] == gen["id"] for g in listed)


def test_generation_reports_running_while_worker_is_active(client, monkeypatch):
    class SlowGenerator:
        async def generate(self, *, generation_id, prompt, media_type, **kwargs):
            import asyncio

            await asyncio.sleep(0.4)
            return GenerationResult(file_url=f"/storage/{generation_id}.svg")

    monkeypatch.setattr(
        generation_jobs, "get_generator", lambda provider="local_comfyui", quality_preset=None: SlowGenerator()
    )

    resp = client.post(
        "/api/generations",
        json={"prompt": "slow render", "media_type": "image"},
    )
    assert resp.status_code == 201
    gen = resp.json()
    assert gen["status"] == "queued"

    running = _wait_for_generation(client, gen["id"], "running")
    assert running["file_url"] is None
    _wait_for_generation(client, gen["id"], "completed")


def test_generation_failure_is_persisted_without_charging(client, monkeypatch):
    class FailingGenerator:
        async def generate(self, *, generation_id, prompt, media_type, **kwargs):
            raise RuntimeError("renderer unavailable")

    monkeypatch.setattr(
        generation_jobs, "get_generator", lambda provider="local_comfyui", quality_preset=None: FailingGenerator()
    )
    before = client.get("/api/me").json()["credits"]

    resp = client.post(
        "/api/generations",
        json={"prompt": "broken render", "media_type": "image"},
    )
    assert resp.status_code == 201
    gen = _wait_for_generation(client, resp.json()["id"], "failed")
    assert gen["error"] == "renderer unavailable"
    assert gen["credits_cost"] == 0
    assert gen["file_url"] is None

    after = client.get("/api/me").json()["credits"]
    assert after == before


def test_empty_prompt_is_rejected(client):
    resp = client.post(
        "/api/generations", json={"prompt": "", "media_type": "image"}
    )
    assert resp.status_code == 422


def test_project_create_list_and_link_generation(client):
    created = client.post(
        "/api/projects", json={"name": "Launch campaign", "description": "Q3 ads"}
    )
    assert created.status_code == 201
    project_id = created.json()["id"]

    projects = client.get("/api/projects").json()
    assert any(p["id"] == project_id for p in projects)

    gen = client.post(
        "/api/generations",
        json={"prompt": "product on marble", "project_id": project_id},
    ).json()
    assert gen["project_id"] == project_id


def test_generation_to_missing_project_is_404(client):
    resp = client.post(
        "/api/generations",
        json={"prompt": "hello", "project_id": "does-not-exist"},
    )
    assert resp.status_code == 404


def test_product_asset_upload_list_and_get(client):
    project = client.post(
        "/api/projects", json={"name": "Product shoot", "description": "Assets"}
    ).json()

    resp = client.post(
        "/api/assets/upload",
        data={"project_id": project["id"]},
        files={"file": ("cup.png", b"fake image bytes", "image/png")},
    )
    assert resp.status_code == 201
    asset = resp.json()
    assert asset["project_id"] == project["id"]
    assert asset["status"] == "uploaded"
    assert asset["original_url"].startswith("/storage/uploads/")
    assert asset["processed_url"] is None

    filename = asset["original_url"].split("/")[-1]
    assert os.path.exists(os.path.join(os.environ["STORAGE_DIR"], "uploads", filename))

    detail = client.get(f"/api/assets/{asset['id']}").json()
    assert detail["id"] == asset["id"]

    listed = client.get(f"/api/assets?project_id={project['id']}").json()
    assert any(item["id"] == asset["id"] for item in listed)


def test_background_removal_mock_completes(client):
    project = client.post(
        "/api/projects", json={"name": "Background removal", "description": None}
    ).json()
    asset = client.post(
        "/api/assets/upload",
        data={"project_id": project["id"]},
        files={"file": ("bottle.jpg", b"jpg bytes", "image/jpeg")},
    ).json()

    resp = client.post(f"/api/assets/{asset['id']}/remove-background")
    assert resp.status_code == 200
    assert resp.json()["status"] == "processing"

    processed = _wait_for_asset(client, asset["id"], "completed")
    assert processed["processed_url"].startswith("/storage/processed/")
    filename = processed["processed_url"].split("/")[-1]
    assert os.path.exists(
        os.path.join(os.environ["STORAGE_DIR"], "processed", filename)
    )


def test_background_removal_failure_is_persisted(client, monkeypatch):
    class FailingRemoval:
        def remove_background(self, *, asset_id, original_path, output_path):
            raise RuntimeError("removal unavailable")

    monkeypatch.setattr(
        asset_jobs, "get_background_removal_adapter", lambda: FailingRemoval()
    )
    project = client.post(
        "/api/projects", json={"name": "Failed removal", "description": None}
    ).json()
    asset = client.post(
        "/api/assets/upload",
        data={"project_id": project["id"]},
        files={"file": ("shoe.webp", b"webp bytes", "image/webp")},
    ).json()

    client.post(f"/api/assets/{asset['id']}/remove-background")
    failed = _wait_for_asset(client, asset["id"], "failed")
    assert failed["error"] == "removal unavailable"
    assert failed["processed_url"] is None


def test_upload_requires_project_and_image_file(client):
    missing_project = client.post(
        "/api/assets/upload",
        data={"project_id": "missing"},
        files={"file": ("cup.png", b"bytes", "image/png")},
    )
    assert missing_project.status_code == 404

    project = client.post(
        "/api/projects", json={"name": "Invalid upload", "description": None}
    ).json()
    bad_file = client.post(
        "/api/assets/upload",
        data={"project_id": project["id"]},
        files={"file": ("notes.txt", b"not image", "text/plain")},
    )
    assert bad_file.status_code == 400


def test_product_scene_queues_completes_and_lists(client):
    project = client.post(
        "/api/projects", json={"name": "Scene project", "description": None}
    ).json()
    asset = client.post(
        "/api/assets/upload",
        data={"project_id": project["id"]},
        files={"file": ("watch.png", b"product bytes", "image/png")},
    ).json()

    resp = client.post(
        "/api/product-scenes",
        json={
            "project_id": project["id"],
            "asset_id": asset["id"],
            "prompt": "watch on black marble",
            "preset": "luxury",
        },
    )
    assert resp.status_code == 201
    scene = resp.json()
    assert scene["status"] == "queued"
    assert scene["result_url"] is None

    scene = _wait_for_scene(client, scene["id"], "completed")
    assert scene["result_url"].startswith("/storage/product-scenes/")
    filename = scene["result_url"].split("/")[-1]
    assert os.path.exists(
        os.path.join(os.environ["STORAGE_DIR"], "product-scenes", filename)
    )

    detail = client.get(f"/api/product-scenes/{scene['id']}").json()
    assert detail["id"] == scene["id"]

    listed = client.get(f"/api/product-scenes?project_id={project['id']}").json()
    assert any(item["id"] == scene["id"] for item in listed)


def test_product_scene_reports_running_while_worker_is_active(client, monkeypatch):
    class SlowSceneGenerator:
        async def generate(self, *, scene_id, prompt, preset, product_image_url, mask_image_url=None, seg_prompt=None):
            import asyncio

            await asyncio.sleep(0.4)
            return ProductSceneResult(result_url=f"/storage/product-scenes/{scene_id}.svg")

    monkeypatch.setattr(
        product_scene_jobs,
        "get_product_scene_generator",
        lambda mode=None, target_attribute=None:SlowSceneGenerator(),
    )
    project = client.post(
        "/api/projects", json={"name": "Running scene", "description": None}
    ).json()
    asset = client.post(
        "/api/assets/upload",
        data={"project_id": project["id"]},
        files={"file": ("watch.png", b"product bytes", "image/png")},
    ).json()

    scene = client.post(
        "/api/product-scenes",
        json={
            "project_id": project["id"],
            "asset_id": asset["id"],
            "prompt": "slow product scene",
            "preset": "studio",
        },
    ).json()

    running = _wait_for_scene(client, scene["id"], "running")
    assert running["result_url"] is None
    _wait_for_scene(client, scene["id"], "completed")


def test_product_scene_uses_processed_asset_when_available(client, monkeypatch):
    seen = {}

    class RecordingSceneGenerator:
        async def generate(self, *, scene_id, prompt, preset, product_image_url, mask_image_url=None, seg_prompt=None):
            seen["product_image_url"] = product_image_url
            return ProductSceneResult(result_url=f"/storage/product-scenes/{scene_id}.svg")

    monkeypatch.setattr(
        product_scene_jobs,
        "get_product_scene_generator",
        lambda mode=None, target_attribute=None:RecordingSceneGenerator(),
    )
    project = client.post(
        "/api/projects", json={"name": "Processed source", "description": None}
    ).json()
    asset = client.post(
        "/api/assets/upload",
        data={"project_id": project["id"]},
        files={"file": ("bag.png", b"product bytes", "image/png")},
    ).json()
    client.post(f"/api/assets/{asset['id']}/remove-background")
    asset = _wait_for_asset(client, asset["id"], "completed")

    scene = client.post(
        "/api/product-scenes",
        json={
            "project_id": project["id"],
            "asset_id": asset["id"],
            "prompt": "bag on seamless background",
            "preset": "studio",
        },
    ).json()
    _wait_for_scene(client, scene["id"], "completed")
    assert seen["product_image_url"] == asset["processed_url"]


def test_product_scene_failure_is_persisted(client, monkeypatch):
    class FailingSceneGenerator:
        async def generate(self, *, scene_id, prompt, preset, product_image_url, mask_image_url=None, seg_prompt=None):
            raise RuntimeError("scene generator offline")

    monkeypatch.setattr(
        product_scene_jobs,
        "get_product_scene_generator",
        lambda mode=None, target_attribute=None:FailingSceneGenerator(),
    )
    project = client.post(
        "/api/projects", json={"name": "Failed scene", "description": None}
    ).json()
    asset = client.post(
        "/api/assets/upload",
        data={"project_id": project["id"]},
        files={"file": ("lamp.jpg", b"product bytes", "image/jpeg")},
    ).json()

    scene = client.post(
        "/api/product-scenes",
        json={
            "project_id": project["id"],
            "asset_id": asset["id"],
            "prompt": "lamp in a room",
            "preset": "outdoor",
        },
    ).json()
    failed = _wait_for_scene(client, scene["id"], "failed")
    assert failed["error"] == "scene generator offline"
    assert failed["result_url"] is None


def test_product_scene_rejects_missing_or_unready_asset(client):
    project = client.post(
        "/api/projects", json={"name": "Scene validation", "description": None}
    ).json()

    missing = client.post(
        "/api/product-scenes",
        json={
            "project_id": project["id"],
            "asset_id": "missing",
            "prompt": "hello",
            "preset": "social ad",
        },
    )
    assert missing.status_code == 404

    asset = client.post(
        "/api/assets/upload",
        data={"project_id": project["id"]},
        files={"file": ("broken.png", b"product bytes", "image/png")},
    ).json()
    client.post(f"/api/assets/{asset['id']}/remove-background")
    asset = _wait_for_asset(client, asset["id"], "completed")

    # Completed assets are valid.
    ok = client.post(
        "/api/product-scenes",
        json={
            "project_id": project["id"],
            "asset_id": asset["id"],
            "prompt": "valid completed asset",
            "preset": "social ad",
        },
    )
    assert ok.status_code == 201


def test_completed_asset_is_listed_as_product_scene_ready(client):
    project = client.post(
        "/api/projects", json={"name": "Ready Assets", "description": None}
    ).json()
    asset = client.post(
        "/api/assets/upload",
        data={"project_id": project["id"]},
        files={"file": ("ready.png", b"product bytes", "image/png")},
    ).json()
    client.post(f"/api/assets/{asset['id']}/remove-background")
    completed = _wait_for_asset(client, asset["id"], "completed")

    ready_assets = client.get(
        f"/api/assets?project_id={project['id']}&ready_for=product_scenes"
    ).json()
    assert [item["id"] for item in ready_assets] == [completed["id"]]
    assert ready_assets[0]["status"] == "completed"

    scene = client.post(
        "/api/product-scenes",
        json={
            "project_id": project["id"],
            "asset_id": completed["id"],
            "prompt": "ready completed product",
            "preset": "studio",
        },
    )
    assert scene.status_code == 201


def test_product_scene_saves_creative_fashion_edit_mode(client):
    project = client.post(
        "/api/projects", json={"name": "Creative Fashion", "description": None}
    ).json()
    asset = client.post(
        "/api/assets/upload",
        data={"project_id": project["id"]},
        files={"file": ("fashion.png", b"product bytes", "image/png")},
    ).json()

    scene = client.post(
        "/api/product-scenes",
        json={
            "project_id": project["id"],
            "asset_id": asset["id"],
            "prompt": "Change pose to confident runway stance",
            "preset": "luxury",
            "mode": "creative_fashion_edit",
        },
    )

    assert scene.status_code == 201
    body = scene.json()
    assert body["mode"] == "creative_fashion_edit"
    saved = client.get(f"/api/product-scenes/{body['id']}").json()
    assert saved["mode"] == "creative_fashion_edit"


def test_product_scene_saves_film_studio_transformation_mode(client):
    project = client.post(
        "/api/projects", json={"name": "Film Studio Mode", "description": None}
    ).json()
    asset = client.post(
        "/api/assets/upload",
        data={"project_id": project["id"]},
        files={"file": ("character.png", b"product bytes", "image/png")},
    ).json()

    scene = client.post(
        "/api/product-scenes",
        json={
            "project_id": project["id"],
            "asset_id": asset["id"],
            "prompt": "Reimagine as a cyberpunk film hero",
            "preset": "luxury",
            "mode": "character_reimagination",
        },
    )

    assert scene.status_code == 201
    assert scene.json()["mode"] == "character_reimagination"


def _wait_for_asset(client, asset_id, status, timeout=5):
    deadline = time.time() + timeout
    latest = None
    while time.time() < deadline:
        latest = client.get(f"/api/assets/{asset_id}").json()
        if latest["status"] == status:
            return latest
        time.sleep(0.05)
    raise AssertionError(f"Asset {asset_id} did not reach {status}: {latest}")


def _wait_for_scene(client, scene_id, status, timeout=5):
    deadline = time.time() + timeout
    latest = None
    while time.time() < deadline:
        latest = client.get(f"/api/product-scenes/{scene_id}").json()
        if latest["status"] == status:
            return latest
        time.sleep(0.05)
    raise AssertionError(f"Scene {scene_id} did not reach {status}: {latest}")
