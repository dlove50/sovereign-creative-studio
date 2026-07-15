"""Image quality presets (FLUX.2 Klein 4B etc.) + Animal Portrait prompt preset."""
import os
import sys
import tempfile

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")
    os.environ["DEFAULT_CREDITS"] = "100"

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import image_presets, prompt_presets


@pytest.fixture(scope="module", autouse=True)
def _app_ready():
    with TestClient(app):
        yield


def _client():
    return TestClient(app)


def test_presets_endpoint_lists_quality_and_style():
    body = _client().get("/api/generations/presets").json()
    ids = {p["id"] for p in body["quality_presets"]}
    assert {"local_fast", "flux2_klein", "flux1_dev", "sdxl"} <= ids
    flux2 = next(p for p in body["quality_presets"] if p["id"] == "flux2_klein")
    assert flux2["recommended"] is True
    local = next(p for p in body["quality_presets"] if p["id"] == "local_fast")
    assert local["is_default"] is True and local["ready"] is True  # always safe
    style_ids = {s["id"] for s in body["style_presets"]}
    assert {"none", "animal_portrait"} <= style_ids


def test_flux2_dev_is_not_offered():
    ids = {p["id"] for p in image_presets.list_image_presets()}
    assert "flux2_dev" not in ids and "flux2-dev" not in ids


def test_animal_portrait_frames_subject_and_avoids_distant():
    out = prompt_presets.apply_style_preset("a golden retriever", "animal_portrait")
    assert out.startswith("a golden retriever,")
    low = out.lower()
    assert "main subject" in low and "filling most of the frame" in low
    assert "not a tiny distant animal" in low


def test_none_style_leaves_prompt_unchanged():
    assert prompt_presets.apply_style_preset("a cat", "none") == "a cat"
    assert prompt_presets.apply_style_preset("a cat", None) == "a cat"


def test_create_generation_applies_style_preset():
    c = _client()
    r = c.post(
        "/api/generations",
        json={"prompt": "a husky in snow", "media_type": "image", "style_preset": "animal_portrait"},
    )
    assert r.status_code == 201, r.text
    gen = r.json()
    assert "main subject" in gen["prompt"].lower()
    # local default preset is stored as the provider_model for local generations
    assert gen["provider_model"] == "local_fast"


def test_unknown_quality_preset_rejected():
    r = _client().post(
        "/api/generations",
        json={"prompt": "x", "media_type": "image", "quality_preset": "does_not_exist"},
    )
    assert r.status_code == 400


def test_presets_endpoint_lists_modes_and_refine_status():
    body = _client().get("/api/generations/presets").json()
    mode_ids = {m["id"] for m in body["image_modes"]}
    assert mode_ids == {
        "realistic_general", "portrait_human", "animal_pet",
        "krea2_turbo_fp8",
        "product_shot", "anime_illustration", "cartoon_3d", "fallback",
    }
    # Face/subject refine is architecture-only for now.
    assert body["face_refine"]["available"] is False
    assert "coming soon" in body["face_refine"]["detail"].lower()


def test_animal_and_human_modes_have_quality_enhancers_and_guidance():
    from app.services import image_modes

    animal = image_modes.apply_mode_prompt("a golden retriever on a path", "animal_pet").lower()
    assert "main subject" in animal and "35-45%" in animal
    assert "symmetrical eyes" in animal and "not a tiny distant animal" in animal

    human = image_modes.apply_mode_prompt("a woman", "portrait_human").lower()
    assert "symmetrical eyes" in human and "natural skin texture" in human

    modes = {m["id"]: m for m in image_modes.list_image_modes()}
    assert modes["animal_pet"]["subject_size_guidance"]
    assert modes["portrait_human"]["subject_size_guidance"]
    assert modes["realistic_general"]["subject_size_guidance"] is None


def test_anime_mode_reports_setup_required_but_still_resolves(monkeypatch):
    from app.services import image_modes

    # Deterministic: simulate ComfyUI unreachable so the anime checkpoint is not
    # ready regardless of what is installed on the machine running the tests.
    monkeypatch.setattr(image_presets, "_object_info", lambda: None)

    modes = {m["id"]: m for m in image_modes.list_image_modes()}
    anime = modes["anime_illustration"]
    # Anime checkpoint unavailable -> recommended not ready, but a ready model is used.
    assert anime["recommended_ready"] is False
    assert anime["setup_note"] and "illustrious" in anime["setup_note"].lower()
    assert anime["effective_preset"]  # never empty (falls back to a ready preset)


def test_create_with_image_mode_applies_enhancer_and_resolves_model():
    c = _client()
    r = c.post(
        "/api/generations",
        json={"prompt": "golden retriever on a gravel path", "media_type": "image", "image_mode": "animal_pet"},
    )
    assert r.status_code == 201, r.text
    gen = r.json()
    assert "main subject" in gen["prompt"].lower() and "35-45%" in gen["prompt"]
    # mode resolves to a ready preset (local_fast when ComfyUI is offline in tests)
    assert gen["provider_model"] in {
        "local_fast",
        "flux1_krea",
        "krea2_turbo_fp8",
        "flux1_dev",
        "flux2_klein",
        "sdxl",
        "illustrious_xl",
    }


def test_unknown_image_mode_rejected():
    r = _client().post(
        "/api/generations",
        json={"prompt": "x", "media_type": "image", "image_mode": "nope"},
    )
    assert r.status_code == 400


def test_unready_preset_blocks_on_real_backend(monkeypatch):
    # Simulate the real ComfyUI backend with the chosen preset not installed.
    import app.routers.generations as gens

    monkeypatch.setattr(gens, "GENERATOR_BACKEND", "comfyui")
    monkeypatch.setattr(gens.image_presets, "preset_ready", lambda pid: False)
    r = _client().post(
        "/api/generations",
        json={"prompt": "a dog", "media_type": "image", "quality_preset": "flux2_klein"},
    )
    assert r.status_code == 409
    assert "setup required" in r.json()["detail"].lower()
