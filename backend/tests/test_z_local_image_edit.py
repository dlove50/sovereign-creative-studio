import time

from fastapi.testclient import TestClient

import app.routers.generations as generation_router
import app.services.generation_jobs as generation_jobs
from app.generators.base import GenerationResult
from app.main import app

HEADER = "X-SCS-Family-User-Id"


def _user(client: TestClient, name: str, credits: int = 100) -> dict:
    return client.post(
        "/api/admin/family-users",
        json={"display_name": name, "role": "family_user", "initial_credits": credits},
    ).json()


def _project(client: TestClient, user_id: str) -> str:
    return client.post(
        "/api/projects",
        json={"name": "Local image edit test", "description": None},
        headers={HEADER: user_id},
    ).json()["id"]


def _wait(client: TestClient, user_id: str, generation_id: str, target: str) -> dict:
    body = {}
    for _ in range(60):
        body = client.get(
            f"/api/generations/{generation_id}", headers={HEADER: user_id}
        ).json()
        if body["status"] == target:
            return body
        time.sleep(0.1)
    raise AssertionError(f"generation did not reach {target}: {body}")


def test_local_image_edit_mode_reports_qwen_ready(monkeypatch):
    monkeypatch.setattr(generation_router, "_local_image_edit_ready", lambda: (True, None))
    with TestClient(app) as client:
        modes = client.get("/api/generations/modes").json()

    edit = next(m for m in modes if m["id"] == "image_edit")
    assert edit["providers"]["local_comfyui"]["available"] is True
    assert edit["providers"]["local_comfyui"]["cost"] == 5


def test_local_image_edit_requires_source(monkeypatch):
    monkeypatch.setattr(generation_router, "_local_image_edit_ready", lambda: (True, None))
    with TestClient(app) as client:
        user = _user(client, "Edit no source")
        project_id = _project(client, user["id"])
        resp = client.post(
            "/api/generations",
            json={
                "project_id": project_id,
                "prompt": "edit this",
                "media_type": "image",
                "provider": "local_comfyui",
                "mode": "image_edit",
            },
            headers={HEADER: user["id"]},
        )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Local Image Edit requires source_image_url."


def test_image_edit_source_upload_without_project():
    with TestClient(app) as client:
        resp = client.post(
            "/api/generations/source-upload",
            files={"file": ("source.png", b"PNGDATA", "image/png")},
        )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["project_id"] is None
    assert body["source_image_url"].startswith("/storage/image-edit-sources/")
    assert body["source_image_url"].endswith(".png")


def test_image_edit_source_upload_with_project_validates_ownership():
    with TestClient(app) as client:
        user = _user(client, "Source upload project")
        project_id = _project(client, user["id"])

        ok = client.post(
            "/api/generations/source-upload",
            data={"project_id": project_id},
            files={"file": ("source.webp", b"WEBP", "image/webp")},
            headers={HEADER: user["id"]},
        )
        assert ok.status_code == 201, ok.text
        assert ok.json()["project_id"] == project_id

        missing = client.post(
            "/api/generations/source-upload",
            data={"project_id": "missing-project"},
            files={"file": ("source.png", b"PNGDATA", "image/png")},
            headers={HEADER: user["id"]},
        )
    assert missing.status_code == 404


def test_image_edit_source_upload_rejects_non_image():
    with TestClient(app) as client:
        resp = client.post(
            "/api/generations/source-upload",
            files={"file": ("source.txt", b"not image", "text/plain")},
        )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Source upload must be an image file"


def test_local_image_edit_job_saves_source_and_charges_on_success(monkeypatch):
    captured = {}

    class _FakeGenerator:
        async def generate(self, **kwargs):
            captured.update(kwargs)
            return GenerationResult(file_url="/storage/edit-result.png")

    monkeypatch.setattr(generation_router, "_local_image_edit_ready", lambda: (True, None))
    monkeypatch.setattr(
        generation_jobs,
        "get_generator",
        lambda provider="local_comfyui", quality_preset=None: _FakeGenerator(),
    )

    with TestClient(app) as client:
        user = _user(client, "Edit success")
        project_id = _project(client, user["id"])
        resp = client.post(
            "/api/generations",
            json={
                "project_id": project_id,
                "prompt": "make it cinematic",
                "media_type": "image",
                "provider": "local_comfyui",
                "mode": "image_edit",
                "source_image_url": "/storage/uploads/source.png",
            },
            headers={HEADER: user["id"]},
        )
        assert resp.status_code == 201, resp.text
        generation = _wait(client, user["id"], resp.json()["id"], "completed")
        txns = client.get(
            "/api/admin/credits/transactions", params={"user_id": user["id"]}
        ).json()
        library = client.get("/api/library", headers={HEADER: user["id"]}).json()

    assert captured["mode"] == "image_edit"
    assert captured["source_image_url"] == "/storage/uploads/source.png"
    assert generation["source_image_url"] == "/storage/uploads/source.png"
    assert generation["provider_model"] == "qwen_image_edit_2509_fp8_e4m3fn.safetensors"
    assert generation["credits_cost"] == 5
    assert any(
        t["related_id"] == generation["id"]
        and t["transaction_type"] == "generation_charge"
        and t["amount"] == -5
        for t in txns
    )
    assert any(
        item["source_entity_id"] == generation["id"]
        and item["asset_url"] == "/storage/edit-result.png"
        for item in library
    )
