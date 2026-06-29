"""Model Manager endpoints. ComfyUI HTTP is faked, so these do not require GPU."""
import os
import tempfile

_TMP = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(_TMP, 'test.db')}")
os.environ.setdefault("STORAGE_DIR", os.path.join(_TMP, "storage"))
os.environ.setdefault("GENERATOR_BACKEND", "mock")

from fastapi.testclient import TestClient  # noqa: E402

import app.services.model_manager as model_manager  # noqa: E402
from app.main import app  # noqa: E402


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class _FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, path):
        if path == "/system_stats":
            return _FakeResponse({"system": {"comfyui_version": "0.test"}})
        if path == "/object_info":
            return _FakeResponse(
                {
                    "FluxKontextImageScale": {},
                    "UNETLoader": {
                        "input": {
                            "required": {
                                "unet_name": [
                                    [
                                        "flux1-dev.safetensors",
                                        "qwen_image_edit_2509_fp8_e4m3fn.safetensors",
                                    ]
                                ]
                            }
                        }
                    },
                    "DualCLIPLoader": {
                        "input": {
                            "required": {
                                "clip_name1": [
                                    [
                                        "clip_l.safetensors",
                                        "qwen_2.5_vl_7b_fp8_scaled.safetensors",
                                    ]
                                ],
                                "clip_name2": [
                                    [
                                        "t5xxl_fp8_e4m3fn_scaled.safetensors",
                                        "qwen_2.5_vl_7b_fp8_scaled.safetensors",
                                    ]
                                ],
                            }
                        }
                    },
                    "VAELoader": {
                        "input": {"required": {"vae_name": [["ae.safetensors"]]}}
                    },
                    "CLIPTextEncodeFlux": {},
                    "TextEncodeQwenImageEdit": {},
                    "CheckpointLoaderSimple": {
                        "input": {
                            "required": {
                                "ckpt_name": [
                                    [
                                        "v1-5-pruned-emaonly-fp16.safetensors",
                                        "ltx-2.3-22b-dev-fp8.safetensors",
                                    ]
                                ]
                            }
                        }
                    },
                    "LTXAVTextEncoderLoader": {
                        "input": {
                            "required": {
                                "text_encoder": [
                                    ["gemma_3_12B_it_fp4_mixed.safetensors"]
                                ],
                                "ckpt_name": [["ltx-2.3-22b-dev-fp8.safetensors"]],
                            }
                        }
                    },
                    "LoraLoaderModelOnly": {
                        "input": {
                            "required": {
                                "lora_name": [
                                    ["ltx-2.3-22b-distilled-lora-384.safetensors"]
                                ]
                            }
                        }
                    },
                    "LTXVConditioning": {},
                    "LTXVImgToVideo": {},
                    "ModelSamplingLTXV": {},
                    "CreateVideo": {},
                    "SaveVideo": {},
                    "RemBGSession+": {},
                    "ImageRemoveBackground+": {},
                }
            )
        raise AssertionError(path)


class _OfflineClient(_FakeClient):
    def get(self, path):
        raise RuntimeError("offline")


def test_model_status_reports_comfyui_models(monkeypatch):
    monkeypatch.setattr(model_manager.httpx, "Client", _FakeClient)
    monkeypatch.setattr(model_manager, "PRODUCT_SCENE_MODEL", "flux-kontext")

    with TestClient(app) as client:
        resp = client.get("/api/models/status")

    assert resp.status_code == 200
    body = resp.json()
    assert body["comfyui"]["reachable"] is True
    assert body["comfyui"]["version"] == "0.test"
    flux = next(item for item in body["image_models"] if item["name"] == "Flux Kontext")
    assert flux["installed"] is True
    assert flux["active"] is True
    ltx = next(item for item in body["video_models"] if item["name"] == "LTX 2.3")
    assert ltx["installed"] is True
    assert body["video_generation_ready"] == "mock-active; real LTX appears available"
    assert any(item["exists"] for item in body["workflows"])


def test_model_status_reports_real_ltx_ready_when_selected(monkeypatch):
    monkeypatch.setattr(model_manager.httpx, "Client", _FakeClient)
    monkeypatch.setattr(model_manager, "VIDEO_BACKEND", "comfyui")
    monkeypatch.setattr(
        model_manager,
        "COMFYUI_VIDEO_MODEL_NAME",
        "ltx-2.3-22b-dev-fp8.safetensors",
    )

    with TestClient(app) as client:
        resp = client.get("/api/models/status")

    assert resp.status_code == 200
    body = resp.json()
    assert body["current_config"]["video_backend"] == "comfyui"
    assert body["video_generation_ready"] == "real-ltx-ready"


def test_model_status_degrades_when_comfyui_offline(monkeypatch):
    monkeypatch.setattr(model_manager.httpx, "Client", _OfflineClient)

    with TestClient(app) as client:
        resp = client.get("/api/models/status")

    assert resp.status_code == 200
    body = resp.json()
    assert body["comfyui"]["reachable"] is False
    assert body["comfyui"]["error"]
    assert body["video_generation_ready"] == "mock-active"
    assert body["image_models"]
    assert any(not item["installed"] for item in body["image_models"])


def test_model_sub_endpoints(monkeypatch):
    monkeypatch.setattr(model_manager.httpx, "Client", _FakeClient)

    with TestClient(app) as client:
        image_resp = client.get("/api/models/image")
        video_resp = client.get("/api/models/video")
        workflow_resp = client.get("/api/models/workflows")

    assert image_resp.status_code == 200
    assert video_resp.status_code == 200
    assert workflow_resp.status_code == 200
    assert any(item["name"] == "Qwen Image" for item in image_resp.json())
    assert any(item["name"] == "LTX text encoder" for item in video_resp.json())
    assert any(item["path"].endswith(".json") for item in workflow_resp.json())
