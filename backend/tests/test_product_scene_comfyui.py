"""ComfyUI product-scene adapter tests. All HTTP is faked, so these run without
a ComfyUI server or GPU."""
import asyncio
from pathlib import Path

import pytest

import app.product_scene_generators as scene_generators
import app.product_scene_generators.comfyui as scene_mod
from app.product_scene_generators.comfyui import ComfyUIProductSceneGenerator
from app.product_scene_generators.mock import MockProductSceneGenerator

WORKFLOW = (
    Path(__file__).resolve().parent.parent / "workflows" / "product_scene.json"
)
TEST_STORAGE = Path(__file__).resolve().parent.parent / "storage" / "_test_product_scene"
_PNG_BYTES = b"\x89PNG\r\n\x1a\nSCENEIMAGE"
_PRODUCT_BYTES = b"\x89PNG\r\n\x1a\nPRODUCT"


class _FakeResponse:
    def __init__(self, *, json_data=None, content=b""):
        self._json = json_data
        self.content = content
        self.status_code = 200

    def json(self):
        return self._json

    def raise_for_status(self):
        return None


class _FakeAsyncClient:
    last_upload_files = None
    last_prompt_json = None
    last_view_params = None
    calls = []
    available_nodes = {}

    def __init__(self, *args, **kwargs):
        self.history_calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, files=None, data=None):
        _FakeAsyncClient.calls.append(("POST", url))
        if url == "/upload/image":
            _FakeAsyncClient.last_upload_files = files
            return _FakeResponse(
                json_data={"name": "scene_input.png", "subfolder": "", "type": "input"}
            )
        if url == "/prompt":
            _FakeAsyncClient.last_prompt_json = json
            return _FakeResponse(json_data={"prompt_id": "pid-xyz"})
        raise AssertionError(f"unexpected POST {url}")

    async def get(self, url, params=None):
        if url == "/object_info":
            _FakeAsyncClient.calls.append(("GET", url))
            return _FakeResponse(json_data=_FakeAsyncClient.available_nodes)
        if url.startswith("/history/"):
            _FakeAsyncClient.calls.append(("GET", url))
            self.history_calls += 1
            if self.history_calls == 1:
                return _FakeResponse(json_data={"pid-xyz": {}})
            return _FakeResponse(
                json_data={
                    "pid-xyz": {
                        "outputs": {
                            "9": {
                                "images": [
                                    {
                                        "filename": "sovereign_scene_00001_.png",
                                        "subfolder": "",
                                        "type": "output",
                                    }
                                ]
                            }
                        }
                    }
                }
            )
        if url == "/view":
            _FakeAsyncClient.calls.append(("GET", url))
            _FakeAsyncClient.last_view_params = params
            return _FakeResponse(content=_PNG_BYTES)
        raise AssertionError(f"unexpected GET {url}")


def _make_product_image() -> str:
    uploads = TEST_STORAGE / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    (uploads / "p1.png").write_bytes(_PRODUCT_BYTES)
    return "/storage/uploads/p1.png"


def test_product_scene_generate_uploads_image_injects_prompt_and_saves(monkeypatch):
    _FakeAsyncClient.last_upload_files = None
    _FakeAsyncClient.last_prompt_json = None
    _FakeAsyncClient.last_view_params = None
    _FakeAsyncClient.calls = []
    _FakeAsyncClient.available_nodes = {}

    monkeypatch.setattr(scene_mod.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(scene_mod, "STORAGE_DIR", TEST_STORAGE)
    monkeypatch.setattr(scene_mod, "_POLL_INTERVAL_SECONDS", 0)

    product_url = _make_product_image()
    gen = ComfyUIProductSceneGenerator("http://comfy.local:8188/", str(WORKFLOW))
    result = asyncio.run(
        gen.generate(
            scene_id="scene1",
            prompt="a sleek bottle on a marble counter",
            preset="luxury",
            product_image_url=product_url,
        )
    )

    # Same response shape as the mock generator.
    assert result.result_url == "/storage/product-scenes/scene1.png"
    saved = TEST_STORAGE / "product-scenes" / "scene1.png"
    assert saved.read_bytes() == _PNG_BYTES
    saved.unlink()

    # The product image was uploaded to ComfyUI.
    assert _FakeAsyncClient.last_upload_files["image"][0] == "p1.png"
    assert _FakeAsyncClient.last_upload_files["image"][1] == _PRODUCT_BYTES

    # Prompt + preset style were injected; LoadImage points at the upload.
    posted = _FakeAsyncClient.last_prompt_json["prompt"]
    positive = posted["6"]["inputs"]["text"]
    assert "a sleek bottle on a marble counter" in positive
    assert "luxury product photography" in positive
    assert "__PROMPT__" not in positive and "__PRESET__" not in positive
    assert posted["10"]["inputs"]["image"] == "scene_input.png"

    # Expected ComfyUI call order: upload -> submit -> poll -> poll -> download.
    assert _FakeAsyncClient.calls == [
        ("POST", "/upload/image"),
        ("POST", "/prompt"),
        ("GET", "/history/pid-xyz"),
        ("GET", "/history/pid-xyz"),
        ("GET", "/view"),
    ]
    assert _FakeAsyncClient.last_view_params["filename"] == "sovereign_scene_00001_.png"


def test_product_scene_unknown_preset_falls_back_to_studio(monkeypatch):
    _FakeAsyncClient.last_prompt_json = None
    _FakeAsyncClient.calls = []
    _FakeAsyncClient.available_nodes = {}
    monkeypatch.setattr(scene_mod.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(scene_mod, "STORAGE_DIR", TEST_STORAGE)
    monkeypatch.setattr(scene_mod, "_POLL_INTERVAL_SECONDS", 0)

    product_url = _make_product_image()
    gen = ComfyUIProductSceneGenerator("http://comfy.local:8188", str(WORKFLOW))
    asyncio.run(
        gen.generate(
            scene_id="scene2",
            prompt="cup",
            preset="nonsense",
            product_image_url=product_url,
        )
    )
    (TEST_STORAGE / "product-scenes" / "scene2.png").unlink()

    positive = _FakeAsyncClient.last_prompt_json["prompt"]["6"]["inputs"]["text"]
    assert "studio product photography" in positive


def test_product_scene_missing_file_raises(monkeypatch):
    monkeypatch.setattr(scene_mod, "STORAGE_DIR", TEST_STORAGE)
    gen = ComfyUIProductSceneGenerator("http://comfy.local:8188", str(WORKFLOW))
    with pytest.raises(RuntimeError):
        asyncio.run(
            gen.generate(
                scene_id="x",
                prompt="hi",
                preset="studio",
                product_image_url="/storage/uploads/does-not-exist.png",
            )
        )


def test_product_scene_non_storage_url_raises(monkeypatch):
    gen = ComfyUIProductSceneGenerator("http://comfy.local:8188", str(WORKFLOW))
    with pytest.raises(RuntimeError):
        asyncio.run(
            gen.generate(
                scene_id="x",
                prompt="hi",
                preset="studio",
                product_image_url="https://example.com/image.png",
            )
        )


def test_factory_returns_comfyui_when_selected(monkeypatch):
    monkeypatch.setattr(scene_generators, "PRODUCT_SCENE_BACKEND", "comfyui")
    assert isinstance(
        scene_generators.get_product_scene_generator(),
        ComfyUIProductSceneGenerator,
    )


def test_factory_selects_product_scene_model_workflow(monkeypatch):
    monkeypatch.setattr(scene_generators, "PRODUCT_SCENE_BACKEND", "comfyui")
    monkeypatch.setattr(scene_generators, "PRODUCT_SCENE_MODEL", "flux-kontext")

    gen = scene_generators.get_product_scene_generator()

    assert isinstance(gen, ComfyUIProductSceneGenerator)
    assert gen.model_key == "flux-kontext"
    assert str(gen.workflow_path).endswith("product_scene_flux_kontext.json")


def test_product_scene_model_preflight_reports_missing_model(monkeypatch):
    _FakeAsyncClient.last_prompt_json = None
    _FakeAsyncClient.calls = []
    _FakeAsyncClient.available_nodes = {
        "LoadImage": {},
        "UNETLoader": {"input": {"required": {"unet_name": [["flux1-dev.safetensors"]]}}},
        "CLIPLoader": {
            "input": {
                "required": {
                    "clip_name": [["qwen_2.5_vl_7b_fp8_scaled.safetensors"]],
                }
            }
        },
        "VAELoader": {"input": {"required": {"vae_name": [["ae.safetensors"]]}}},
        "TextEncodeQwenImageEdit": {},
        "VAEEncode": {},
        "KSampler": {},
        "VAEDecode": {},
        "SaveImage": {},
    }
    monkeypatch.setattr(scene_mod.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(scene_mod, "STORAGE_DIR", TEST_STORAGE)
    monkeypatch.setattr(scene_mod, "_POLL_INTERVAL_SECONDS", 0)

    product_url = _make_product_image()
    workflow = Path(__file__).resolve().parent.parent / "workflows" / "product_scene_qwen_image.json"
    gen = ComfyUIProductSceneGenerator(
        "http://comfy.local:8188",
        str(workflow),
        model_key="qwen-image",
    )

    with pytest.raises(RuntimeError, match="qwen_image_edit_2509_fp8_e4m3fn"):
        asyncio.run(
            gen.generate(
                scene_id="qwen-missing",
                prompt="fashion ad",
                preset="studio",
                product_image_url=product_url,
            )
        )

    assert ("GET", "/object_info") in _FakeAsyncClient.calls
    assert ("POST", "/prompt") not in _FakeAsyncClient.calls


def test_factory_falls_back_to_mock(monkeypatch):
    monkeypatch.setattr(scene_generators, "PRODUCT_SCENE_BACKEND", "mock")
    assert isinstance(
        scene_generators.get_product_scene_generator(), MockProductSceneGenerator
    )
    monkeypatch.setattr(scene_generators, "PRODUCT_SCENE_BACKEND", "banana")
    assert isinstance(
        scene_generators.get_product_scene_generator(), MockProductSceneGenerator
    )
