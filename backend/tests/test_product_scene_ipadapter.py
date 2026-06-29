"""ComfyUI IPAdapter product-scene tests. All HTTP is faked, so these run
without a ComfyUI server, IPAdapter custom nodes, or a GPU."""
import asyncio
from pathlib import Path

import pytest

import app.product_scene_generators as scene_generators
import app.product_scene_generators.comfyui as scene_mod
from app.product_scene_generators.comfyui import ComfyUIProductSceneGenerator

WORKFLOWS = Path(__file__).resolve().parent.parent / "workflows"
IPA_WORKFLOW = WORKFLOWS / "product_scene_ipadapter.json"
IMG2IMG_WORKFLOW = WORKFLOWS / "product_scene.json"
TEST_STORAGE = Path(__file__).resolve().parent.parent / "storage" / "_test_ipadapter"
_PNG_BYTES = b"\x89PNG\r\n\x1a\nIPASCENE"
_PRODUCT_BYTES = b"\x89PNG\r\n\x1a\nPRODUCT"

_FULL_NODE_INFO = {
    "IPAdapterUnifiedLoader": {},
    "IPAdapterAdvanced": {},
    "CheckpointLoaderSimple": {},
    "LoadImage": {},
}


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
    available_nodes = _FULL_NODE_INFO
    last_prompt_json = None
    calls = []

    def __init__(self, *args, **kwargs):
        self.history_calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, files=None, data=None):
        _FakeAsyncClient.calls.append(("POST", url))
        if url == "/upload/image":
            return _FakeResponse(json_data={"name": "scene_input.png", "subfolder": ""})
        if url == "/prompt":
            _FakeAsyncClient.last_prompt_json = json
            return _FakeResponse(json_data={"prompt_id": "pid-ipa"})
        raise AssertionError(f"unexpected POST {url}")

    async def get(self, url, params=None):
        _FakeAsyncClient.calls.append(("GET", url))
        if url == "/object_info":
            return _FakeResponse(json_data=_FakeAsyncClient.available_nodes)
        if url.startswith("/history/"):
            self.history_calls += 1
            if self.history_calls == 1:
                return _FakeResponse(json_data={"pid-ipa": {}})
            return _FakeResponse(
                json_data={
                    "pid-ipa": {
                        "outputs": {
                            "9": {
                                "images": [
                                    {"filename": "s_00001_.png", "subfolder": "", "type": "output"}
                                ]
                            }
                        }
                    }
                }
            )
        if url == "/view":
            return _FakeResponse(content=_PNG_BYTES)
        raise AssertionError(f"unexpected GET {url}")


def _reset(monkeypatch, available=_FULL_NODE_INFO):
    _FakeAsyncClient.available_nodes = available
    _FakeAsyncClient.last_prompt_json = None
    _FakeAsyncClient.calls = []
    monkeypatch.setattr(scene_mod.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(scene_mod, "STORAGE_DIR", TEST_STORAGE)
    monkeypatch.setattr(scene_mod, "_POLL_INTERVAL_SECONDS", 0)


def _make_product_image() -> str:
    uploads = TEST_STORAGE / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    (uploads / "p1.png").write_bytes(_PRODUCT_BYTES)
    return "/storage/uploads/p1.png"


def test_ipadapter_verifies_nodes_then_generates(monkeypatch):
    _reset(monkeypatch)
    product_url = _make_product_image()

    gen = ComfyUIProductSceneGenerator(
        "http://comfy.local:8188", str(IPA_WORKFLOW), mode="ipadapter"
    )
    result = asyncio.run(
        gen.generate(
            scene_id="ipa1",
            prompt="a watch on a stone ledge",
            preset="studio",
            product_image_url=product_url,
        )
    )

    assert result.result_url == "/storage/product-scenes/ipa1.png"
    saved = TEST_STORAGE / "product-scenes" / "ipa1.png"
    assert saved.read_bytes() == _PNG_BYTES
    saved.unlink()

    # Availability is checked first (fail fast), before any upload/submit.
    assert _FakeAsyncClient.calls[0] == ("GET", "/object_info")
    assert ("POST", "/upload/image") in _FakeAsyncClient.calls

    # Product image fed into the IPAdapter node's LoadImage input.
    posted = _FakeAsyncClient.last_prompt_json["prompt"]
    assert posted["10"]["inputs"]["image"] == "scene_input.png"
    assert "a watch on a stone ledge" in posted["6"]["inputs"]["text"]


def test_ipadapter_missing_nodes_raises_clear_error(monkeypatch):
    # ComfyUI without the IPAdapter custom nodes installed.
    _reset(monkeypatch, available={"CheckpointLoaderSimple": {}, "LoadImage": {}})
    product_url = _make_product_image()

    gen = ComfyUIProductSceneGenerator(
        "http://comfy.local:8188", str(IPA_WORKFLOW), mode="ipadapter"
    )
    with pytest.raises(RuntimeError, match="IPAdapter"):
        asyncio.run(
            gen.generate(
                scene_id="x", prompt="hi", preset="studio", product_image_url=product_url
            )
        )
    # Fails before uploading or submitting anything.
    assert ("POST", "/upload/image") not in _FakeAsyncClient.calls
    assert ("POST", "/prompt") not in _FakeAsyncClient.calls


def test_ipadapter_mode_with_non_ipadapter_workflow_raises(monkeypatch):
    _reset(monkeypatch)
    product_url = _make_product_image()

    # Pointing ipadapter mode at the plain img2img workflow is a config error.
    gen = ComfyUIProductSceneGenerator(
        "http://comfy.local:8188", str(IMG2IMG_WORKFLOW), mode="ipadapter"
    )
    with pytest.raises(RuntimeError, match="no IPAdapter nodes"):
        asyncio.run(
            gen.generate(
                scene_id="x", prompt="hi", preset="studio", product_image_url=product_url
            )
        )
    assert ("GET", "/object_info") not in _FakeAsyncClient.calls


def test_img2img_mode_does_not_query_object_info(monkeypatch):
    _reset(monkeypatch)
    product_url = _make_product_image()

    gen = ComfyUIProductSceneGenerator(
        "http://comfy.local:8188", str(IMG2IMG_WORKFLOW), mode="img2img"
    )
    asyncio.run(
        gen.generate(
            scene_id="img1", prompt="cup", preset="studio", product_image_url=product_url
        )
    )
    (TEST_STORAGE / "product-scenes" / "img1.png").unlink()
    assert ("GET", "/object_info") not in _FakeAsyncClient.calls


def test_factory_selects_ipadapter_workflow_and_mode(monkeypatch):
    monkeypatch.setattr(scene_generators, "PRODUCT_SCENE_BACKEND", "comfyui")
    monkeypatch.setattr(scene_generators, "COMFYUI_PRODUCT_SCENE_MODE", "ipadapter")
    gen = scene_generators.get_product_scene_generator()
    assert isinstance(gen, ComfyUIProductSceneGenerator)
    assert gen.mode == "ipadapter"
    assert str(gen.workflow_path).endswith("product_scene_ipadapter.json")


def test_factory_defaults_to_img2img_workflow(monkeypatch):
    monkeypatch.setattr(scene_generators, "PRODUCT_SCENE_BACKEND", "comfyui")
    monkeypatch.setattr(scene_generators, "COMFYUI_PRODUCT_SCENE_MODE", "img2img")
    gen = scene_generators.get_product_scene_generator()
    assert gen.mode == "img2img"
    assert str(gen.workflow_path).endswith("product_scene.json")
