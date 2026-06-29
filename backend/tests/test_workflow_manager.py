"""Workflow Manager: config read/update, availability, fallback, discovery.

ComfyUI is offline in tests, so comfyui-only selections are unavailable — which
is exactly what the fallback tests rely on. An autouse fixture snapshots and
restores the managed runtime globals so these tests don't leak into others."""
import os
import tempfile

_TMP = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(_TMP, 'test.db')}")
os.environ.setdefault("STORAGE_DIR", os.path.join(_TMP, "storage"))
os.environ.setdefault("GENERATOR_BACKEND", "mock")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import model_manager, workflow_manager  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _restore_runtime():
    snapshot = workflow_manager.export_runtime()
    yield
    workflow_manager.import_runtime(snapshot)


def test_status_reports_active_config(client):
    body = client.get("/api/workflow-manager/status").json()
    for key in (
        "active_image_model",
        "active_scene_workflow",
        "active_scene_mode",
        "active_video_backend",
        "active_copy_backend",
        "generator_backend",
        "product_scene_backend",
        "comfyui_reachable",
    ):
        assert key in body
    # Defaults in the test env: mock copy, img2img scene mode, mock video.
    assert body["active_copy_backend"] == "mock"
    assert body["active_scene_mode"] == "img2img"
    assert body["active_video_backend"] == "mock"


def test_models_catalog_lists_all_families(client):
    body = client.get("/api/workflow-manager/models").json()
    image_ids = {m["id"] for m in body["image_models"]}
    assert {"flux-kontext", "qwen-image", "hidream-e1", "sdxl", "sd1.5"} <= image_ids
    video_ids = {m["id"] for m in body["video_models"]}
    assert {"mock", "ltx-2.3", "ltx-2.3.1", "wan-2.2"} <= video_ids
    copy_ids = {m["id"] for m in body["copy_models"]}
    assert {"mock", "openai", "claude", "gemini"} <= copy_ids
    # Mock video is always available; the mock copy backend is active by default.
    assert next(m for m in body["video_models"] if m["id"] == "mock")["available"]
    assert next(m for m in body["copy_models"] if m["id"] == "mock")["active"]
    # Claude/Gemini have no adapter yet -> reported but unavailable.
    assert not next(m for m in body["copy_models"] if m["id"] == "claude")["available"]


def test_workflows_discovery(client):
    workflows = client.get("/api/workflow-manager/workflows").json()
    names = {w["name"] for w in workflows}
    assert "Product Scene" in names
    assert any(w["kind"] == "video" for w in workflows)
    assert all("path" in w and "exists" in w for w in workflows)


def test_update_copy_backend_applies(client, monkeypatch):
    # OpenAI is available once a key is present (C8 gates providers on keys).
    import app.config as cfg

    monkeypatch.setattr(cfg, "OPENAI_API_KEY", "sk-test")
    resp = client.put("/api/workflow-manager/config", json={"copy_backend": "openai"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["applied"].get("copy_backend") == "openai"
    assert body["status"]["active_copy_backend"] == "openai"
    # The live copy factory reflects the change immediately.
    import app.copy_generators as copy_generators

    assert copy_generators.COPY_BACKEND == "openai"


def test_update_scene_mode_applies(client):
    resp = client.put("/api/workflow-manager/config", json={"scene_mode": "inpaint"})
    assert resp.status_code == 200
    assert resp.json()["status"]["active_scene_mode"] == "inpaint"


def test_unavailable_video_backend_falls_back(client, monkeypatch):
    # Simulate ComfyUI/LTX unavailable explicitly so this stays deterministic on
    # dev machines where a local ComfyUI install may actually be reachable.
    workflow_manager.update_config({"video_backend": "mock"}, persist=False)
    empty = model_manager._ComfySnapshot(
        status=model_manager.ComfyUIStatusOut(
            base_url="http://x", reachable=False, error="offline"
        ),
        object_info={},
    )
    monkeypatch.setattr(model_manager, "_load_comfy_snapshot", lambda: empty)
    resp = client.put("/api/workflow-manager/config", json={"video_backend": "ltx-2.3"})
    assert resp.status_code == 200
    body = resp.json()
    assert "video_backend" not in body["applied"]
    assert body["warnings"]
    assert body["status"]["active_video_backend"] == "mock"


def test_wan_video_backend_reports_unavailable_without_models(client, monkeypatch):
    object_info = {
        "WanImageToVideo": {},
        "UNETLoader": {"input": {"required": {"unet_name": [["flux1-dev.safetensors"]]}}},
        "CLIPLoader": {
            "input": {
                "required": {"clip_name": [["t5xxl_fp8_e4m3fn_scaled.safetensors"]]}
            }
        },
        "VAELoader": {"input": {"required": {"vae_name": [["ae.safetensors"]]}}},
        "CreateVideo": {},
        "SaveVideo": {},
    }
    snapshot = model_manager._ComfySnapshot(
        status=model_manager.ComfyUIStatusOut(base_url="http://x", reachable=True),
        object_info=object_info,
    )
    monkeypatch.setattr(model_manager, "_load_comfy_snapshot", lambda: snapshot)

    models = client.get("/api/workflow-manager/models").json()
    wan = next(m for m in models["video_models"] if m["id"] == "wan-2.2")
    assert not wan["available"]

    resp = client.put("/api/workflow-manager/config", json={"video_backend": "wan-2.2"})
    body = resp.json()
    assert "video_backend" not in body["applied"]
    assert body["status"]["active_video_backend"] == "mock"


def test_unknown_value_is_rejected_with_warning(client):
    resp = client.put("/api/workflow-manager/config", json={"copy_backend": "banana"})
    body = resp.json()
    assert "copy_backend" not in body["applied"]
    assert body["warnings"]
    # Unchanged.
    assert body["status"]["active_copy_backend"] == "mock"


def test_unknown_scene_mode_rejected(client):
    resp = client.put(
        "/api/workflow-manager/config", json={"scene_mode": "hologram"}
    )
    body = resp.json()
    assert "scene_mode" not in body["applied"]
    assert body["warnings"]


# --- C9: creative scene modes ------------------------------------------------
def test_creative_scene_modes_listed(client):
    body = client.get("/api/workflow-manager/models").json()
    mode_ids = {m["id"] for m in body["scene_modes"]}
    assert {
        "segmented_composite",
        "segmented_composite_polished",
        "advertising_scene",
        "fashion_editorial",
    } <= mode_ids


def test_polished_workflow_discovered(client):
    workflows = client.get("/api/workflow-manager/workflows").json()
    paths = [w["path"].replace("\\", "/") for w in workflows]
    assert any(
        p.endswith("product_scene_segmented_composite_polished.json") for p in paths
    )


def test_advertising_and_fashion_available_with_workflow(client):
    # These modes only need their workflow file (no ComfyUI dependency to list).
    body = client.get("/api/workflow-manager/models").json()
    modes = {m["id"]: m for m in body["scene_modes"]}
    assert modes["advertising_scene"]["available"]
    assert modes["fashion_editorial"]["available"]

    resp = client.put(
        "/api/workflow-manager/config", json={"scene_mode": "advertising_scene"}
    )
    body = resp.json()
    assert body["applied"].get("scene_mode") == "advertising_scene"
    assert body["status"]["active_scene_mode"] == "advertising_scene"


def test_segmented_composite_disabled_without_rembg(client, monkeypatch):
    # Simulate ComfyUI offline (no RemBG) -> segmented_composite unavailable.
    empty = model_manager._ComfySnapshot(
        status=model_manager.ComfyUIStatusOut(
            base_url="http://x", reachable=False, error="offline"
        ),
        object_info={},
    )
    monkeypatch.setattr(model_manager, "_load_comfy_snapshot", lambda: empty)

    body = client.get("/api/workflow-manager/models").json()
    seg = next(m for m in body["scene_modes"] if m["id"] == "segmented_composite")
    assert not seg["available"]
    assert seg["note"]

    resp = client.put(
        "/api/workflow-manager/config", json={"scene_mode": "segmented_composite"}
    )
    assert "scene_mode" not in resp.json()["applied"]


def test_update_persists_to_disk(client, monkeypatch):
    import json

    import app.config as cfg

    monkeypatch.setattr(cfg, "OPENAI_API_KEY", "sk-test")
    client.put("/api/workflow-manager/config", json={"copy_backend": "openai"})
    persisted = workflow_manager._persist_path()
    assert persisted.is_file()
    data = json.loads(persisted.read_text(encoding="utf-8"))
    assert data["copy_backend"] == "openai"


# --- C8: copy provider availability ------------------------------------------
def test_copy_providers_unavailable_without_keys_or_ollama(client, monkeypatch):
    # Force Ollama "offline" so the assertion holds even if a dev box runs it.
    monkeypatch.setattr(workflow_manager, "_ollama_model_names", lambda: None)
    body = client.get("/api/workflow-manager/models").json()
    copy = {m["id"]: m for m in body["copy_models"]}
    # Mock always available; key-gated providers unavailable in the test env.
    assert copy["mock"]["available"]
    assert not copy["openai"]["available"]
    assert not copy["claude"]["available"]
    assert not copy["gemini"]["available"]
    # Each unavailable provider explains why.
    assert copy["claude"]["note"]
    # Ollama-backed providers unavailable when Ollama is offline.
    assert not copy["ollama"]["available"]
    assert not copy["local-qwen"]["available"]


def test_select_unavailable_claude_is_rejected(client):
    resp = client.put("/api/workflow-manager/config", json={"copy_backend": "claude"})
    body = resp.json()
    assert "copy_backend" not in body["applied"]
    assert body["warnings"]
    assert body["status"]["active_copy_backend"] == "mock"


def test_select_available_claude_applies(client, monkeypatch):
    import app.config as cfg

    monkeypatch.setattr(cfg, "ANTHROPIC_API_KEY", "sk-ant")
    resp = client.put("/api/workflow-manager/config", json={"copy_backend": "claude"})
    body = resp.json()
    assert body["applied"].get("copy_backend") == "claude"
    assert body["status"]["active_copy_backend"] == "claude"
    assert body["status"]["active_copy_model"]


def test_select_mock_copy_always_available(client):
    resp = client.put("/api/workflow-manager/config", json={"copy_backend": "mock"})
    assert resp.json()["status"]["active_copy_backend"] == "mock"
