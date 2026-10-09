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


def test_reference_upload_refuses_faces_and_accepts_clothes_or_unchecked(monkeypatch):
    from app.services import face_check

    png = b"\x89PNG\r\n\x1a\n" + b"0" * 32
    with TestClient(app) as client:
        user = _user(client, "Face check user")
        headers = {HEADER: user["id"]}
        monkeypatch.setattr(face_check, "image_has_face", lambda path: True)
        refused = client.post("/api/generations/reference-upload", files={"file": ("me.png", png)}, headers=headers)
        assert refused.status_code == 422 and "shows a face" in refused.json()["detail"]

        monkeypatch.setattr(face_check, "image_has_face", lambda path: False)
        ok = client.post("/api/generations/reference-upload", files={"file": ("jacket.png", png)}, headers=headers)
        assert ok.status_code == 201 and ok.json()["checked"] is True

        monkeypatch.setattr(face_check, "image_has_face", lambda path: None)  # vision model unreachable
        unchecked = client.post("/api/generations/reference-upload", files={"file": ("room.png", png)}, headers=headers)
        assert unchecked.status_code == 201 and unchecked.json()["checked"] is False

        bad = client.post("/api/generations/reference-upload", files={"file": ("x.txt", b"hi")}, headers=headers)
        assert bad.status_code == 400


def test_face_check_reads_yes_no_and_survives_an_offline_model(monkeypatch, tmp_path):
    from app.services import face_check

    img = tmp_path / "a.png"
    img.write_bytes(b"png")
    monkeypatch.setattr(face_check, "_free_comfyui_vram", lambda: None)

    class _Resp:
        def __init__(self, text):
            self._t = text

        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": self._t}}

    for answer, expected in [("YES", True), ("No.", False), ("Maybe", None)]:
        monkeypatch.setattr(face_check.httpx, "post", lambda *a, _t=answer, **k: _Resp(_t))
        assert face_check.image_has_face(img) is expected

    def offline(*a, **k):
        raise face_check.httpx.ConnectError("down")

    monkeypatch.setattr(face_check.httpx, "post", offline)
    assert face_check.image_has_face(img) is None
