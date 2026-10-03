"""Reference images for local image edits: workflow wiring, validation and the job hand-off."""
import time

import pytest
from fastapi.testclient import TestClient

from app import config
import app.routers.generations as generation_router
import app.services.generation_jobs as generation_jobs
from app.generators.base import GenerationResult
from app.generators.comfyui import ComfyUIGenerator
from app.main import app

HEADER = "X-SCS-Family-User-Id"


def test_references_become_image2_and_image3_on_both_prompt_encoders():
    gen = ComfyUIGenerator()
    wf = gen._build_workflow("wear the jacket from image 2", mode="image_edit", source_image_name="me.png",
                             reference_image_names=["jacket.png", "office.png"])
    encoders = [n for n in wf.values() if n["class_type"] == "TextEncodeQwenImageEditPlus"]
    assert len(encoders) == 2
    for enc in encoders:
        assert "image1" in enc["inputs"] and "image2" in enc["inputs"] and "image3" in enc["inputs"]
        assert all(enc["inputs"][k][0] in wf for k in ("image2", "image3"))
    loads = sorted(n["inputs"]["image"] for n in wf.values() if n["class_type"] == "LoadImage")
    assert loads == ["jacket.png", "me.png", "office.png"]


def test_no_references_leaves_the_workflow_as_before():
    wf = ComfyUIGenerator()._build_workflow("x", mode="image_edit", source_image_name="me.png")
    assert not any("image2" in n["inputs"] for n in wf.values())


def _user(client, name):
    return client.post("/api/admin/family-users", json={"display_name": name, "role": "family_user", "initial_credits": 100}).json()


def _body(project_id, **extra):
    return {"project_id": project_id, "prompt": "new outfit", "media_type": "image", "provider": "local_comfyui",
            "mode": "image_edit", "source_image_url": "/storage/image-edit-sources/a.png", **extra}


def test_reference_urls_are_validated_and_reach_the_generator(monkeypatch):
    seen = {}

    class _Gen:
        async def generate(self, **kw):
            seen.update(kw)
            return GenerationResult(file_url="/storage/done.png")

    monkeypatch.setattr(generation_router, "_local_image_edit_ready", lambda: (True, None))
    monkeypatch.setattr(generation_jobs, "get_generator", lambda *a, **k: _Gen())
    with TestClient(app) as client:
        user = _user(client, "Ref user")
        headers = {HEADER: user["id"]}
        project_id = client.post("/api/projects", json={"name": "Refs", "description": None}, headers=headers).json()["id"]

        too_many = client.post("/api/generations", json=_body(project_id, reference_image_urls=["/storage/a.png"] * 3), headers=headers)
        assert too_many.status_code == 422
        not_image = client.post("/api/generations", json=_body(project_id, reference_image_urls=["/storage/a.txt"]), headers=headers)
        assert not_image.status_code == 400
        escape = client.post("/api/generations", json=_body(project_id, reference_image_urls=["/storage/../secret.png"]), headers=headers)
        assert escape.status_code == 400
        text_mode = client.post("/api/generations", json={"project_id": project_id, "prompt": "x", "media_type": "image",
                                                          "provider": "local_comfyui", "mode": "text_to_image",
                                                          "reference_image_urls": ["/storage/a.png"]}, headers=headers)
        assert text_mode.status_code == 400

        (config.STORAGE_DIR / "image-edit-sources").mkdir(parents=True, exist_ok=True)
        (config.STORAGE_DIR / "image-edit-sources" / "b.png").write_bytes(b"png")
        missing = client.post("/api/generations", json=_body(project_id, reference_image_urls=["/storage/image-edit-sources/gone.png"]), headers=headers)
        assert missing.status_code == 400 and "not found" in missing.json()["detail"]

        ok = client.post("/api/generations", json=_body(project_id, reference_image_urls=["/storage/image-edit-sources/b.png"]), headers=headers)
        assert ok.status_code == 201, ok.text
        for _ in range(60):
            if seen:
                break
            time.sleep(0.1)
    assert seen["reference_image_urls"] == ["/storage/image-edit-sources/b.png"]
