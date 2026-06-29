"""ComfyUI inpaint product-scene tests. All HTTP is faked, so these run without
a ComfyUI server, inpaint nodes, or a GPU."""
import asyncio
from pathlib import Path

import pytest

import app.product_scene_generators as scene_generators
import app.product_scene_generators.comfyui as scene_mod
from app.product_scene_generators.comfyui import ComfyUIProductSceneGenerator

WORKFLOWS = Path(__file__).resolve().parent.parent / "workflows"
INPAINT_WORKFLOW = WORKFLOWS / "product_scene_inpaint.json"
IMG2IMG_WORKFLOW = WORKFLOWS / "product_scene.json"
IPA_WORKFLOW = WORKFLOWS / "product_scene_ipadapter.json"
TEST_STORAGE = Path(__file__).resolve().parent.parent / "storage" / "_test_inpaint"
_PNG = b"\x89PNG\r\n\x1a\nINPAINT"

_INPAINT_NODES = {
    "VAEEncodeForInpaint": {},
    "LoadImageMask": {},
    "InvertMask": {},
    "CheckpointLoaderSimple": {},
}


class _FakeResponse:
    def __init__(self, *, json_data=None, content=b""):
        self._json = json_data
        self.content = content

    def json(self):
        return self._json

    def raise_for_status(self):
        return None


class _FakeAsyncClient:
    available_nodes = _INPAINT_NODES
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
            # Echo the filename back as the uploaded name to distinguish uploads.
            return _FakeResponse(json_data={"name": files["image"][0], "subfolder": ""})
        if url == "/prompt":
            _FakeAsyncClient.last_prompt_json = json
            return _FakeResponse(json_data={"prompt_id": "pid-inp"})
        raise AssertionError(f"unexpected POST {url}")

    async def get(self, url, params=None):
        _FakeAsyncClient.calls.append(("GET", url))
        if url == "/object_info":
            return _FakeResponse(json_data=_FakeAsyncClient.available_nodes)
        if url.startswith("/history/"):
            self.history_calls += 1
            if self.history_calls == 1:
                return _FakeResponse(json_data={"pid-inp": {}})
            return _FakeResponse(
                json_data={
                    "pid-inp": {
                        "outputs": {"9": {"images": [{"filename": "o.png", "subfolder": "", "type": "output"}]}}
                    }
                }
            )
        if url == "/view":
            return _FakeResponse(content=_PNG)
        raise AssertionError(f"unexpected GET {url}")


def _reset(monkeypatch, available=_INPAINT_NODES):
    _FakeAsyncClient.available_nodes = available
    _FakeAsyncClient.last_prompt_json = None
    _FakeAsyncClient.calls = []
    monkeypatch.setattr(scene_mod.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(scene_mod, "STORAGE_DIR", TEST_STORAGE)
    monkeypatch.setattr(scene_mod, "_POLL_INTERVAL_SECONDS", 0)


def _make_files() -> tuple[str, str]:
    (TEST_STORAGE / "uploads").mkdir(parents=True, exist_ok=True)
    (TEST_STORAGE / "masks").mkdir(parents=True, exist_ok=True)
    (TEST_STORAGE / "uploads" / "p1.png").write_bytes(b"PRODUCT")
    (TEST_STORAGE / "masks" / "m1.png").write_bytes(b"MASK")
    return "/storage/uploads/p1.png", "/storage/masks/m1.png"


def _inpaint_gen():
    return ComfyUIProductSceneGenerator(
        "http://comfy.local:8188",
        str(INPAINT_WORKFLOW),
        mode="inpaint",
        fallback_mode="img2img",
        fallback_workflow_path=str(IMG2IMG_WORKFLOW),
    )


def test_inpaint_with_mask_uploads_both_and_injects_mask(monkeypatch):
    _reset(monkeypatch)
    product_url, mask_url = _make_files()

    result = asyncio.run(
        _inpaint_gen().generate(
            scene_id="inp1",
            prompt="bottle on wet sand",
            preset="outdoor",
            product_image_url=product_url,
            mask_image_url=mask_url,
        )
    )

    assert result.result_url == "/storage/product-scenes/inp1.png"
    saved = TEST_STORAGE / "product-scenes" / "inp1.png"
    assert saved.read_bytes() == _PNG
    saved.unlink()

    # Inpaint node availability checked first, then both images uploaded.
    assert _FakeAsyncClient.calls[0] == ("GET", "/object_info")
    assert _FakeAsyncClient.calls.count(("POST", "/upload/image")) == 2

    posted = _FakeAsyncClient.last_prompt_json["prompt"]
    assert posted["10"]["inputs"]["image"] == "p1.png"  # product
    assert posted["12"]["inputs"]["image"] == "m1.png"  # mask
    assert "bottle on wet sand" in posted["6"]["inputs"]["text"]


def test_inpaint_missing_nodes_raises_before_upload(monkeypatch):
    _reset(monkeypatch, available={"CheckpointLoaderSimple": {}, "LoadImageMask": {}})
    product_url, mask_url = _make_files()

    with pytest.raises(RuntimeError, match="VAEEncodeForInpaint"):
        asyncio.run(
            _inpaint_gen().generate(
                scene_id="x",
                prompt="hi",
                preset="studio",
                product_image_url=product_url,
                mask_image_url=mask_url,
            )
        )
    assert ("POST", "/upload/image") not in _FakeAsyncClient.calls
    assert ("POST", "/prompt") not in _FakeAsyncClient.calls


def test_inpaint_without_mask_falls_back_to_img2img(monkeypatch):
    _reset(monkeypatch)
    product_url, _ = _make_files()

    asyncio.run(
        _inpaint_gen().generate(
            scene_id="fb1",
            prompt="cup",
            preset="studio",
            product_image_url=product_url,
            mask_image_url=None,
        )
    )
    (TEST_STORAGE / "product-scenes" / "fb1.png").unlink()

    # Fell back to img2img: no node check, single upload, no inpaint node in workflow.
    assert ("GET", "/object_info") not in _FakeAsyncClient.calls
    assert _FakeAsyncClient.calls.count(("POST", "/upload/image")) == 1
    posted = _FakeAsyncClient.last_prompt_json["prompt"]
    class_types = [n.get("class_type") for n in posted.values()]
    assert "VAEEncodeForInpaint" not in class_types


def test_inpaint_without_mask_can_fall_back_to_ipadapter(monkeypatch):
    _reset(monkeypatch, available={**_INPAINT_NODES, "IPAdapterUnifiedLoader": {}, "IPAdapterAdvanced": {}})
    product_url, _ = _make_files()

    gen = ComfyUIProductSceneGenerator(
        "http://comfy.local:8188",
        str(INPAINT_WORKFLOW),
        mode="inpaint",
        fallback_mode="ipadapter",
        fallback_workflow_path=str(IPA_WORKFLOW),
    )
    asyncio.run(
        gen.generate(
            scene_id="fb2",
            prompt="cup",
            preset="studio",
            product_image_url=product_url,
            mask_image_url=None,
        )
    )
    (TEST_STORAGE / "product-scenes" / "fb2.png").unlink()

    # IPAdapter fallback path runs its node check.
    assert ("GET", "/object_info") in _FakeAsyncClient.calls
    posted = _FakeAsyncClient.last_prompt_json["prompt"]
    class_types = [n.get("class_type") for n in posted.values()]
    assert "IPAdapterAdvanced" in class_types


def test_inpaint_no_mask_and_no_fallback_configured_raises(monkeypatch):
    _reset(monkeypatch)
    product_url, _ = _make_files()
    gen = ComfyUIProductSceneGenerator(
        "http://comfy.local:8188", str(INPAINT_WORKFLOW), mode="inpaint"
    )
    with pytest.raises(RuntimeError, match="fallback"):
        asyncio.run(
            gen.generate(
                scene_id="x",
                prompt="hi",
                preset="studio",
                product_image_url=product_url,
                mask_image_url=None,
            )
        )


def test_factory_inpaint_selects_workflow_and_default_fallback(monkeypatch):
    monkeypatch.setattr(scene_generators, "PRODUCT_SCENE_BACKEND", "comfyui")
    monkeypatch.setattr(scene_generators, "COMFYUI_PRODUCT_SCENE_INPAINT_FALLBACK", "img2img")
    gen = scene_generators.get_product_scene_generator("inpaint")
    assert gen.mode == "inpaint"
    assert str(gen.workflow_path).endswith("product_scene_inpaint.json")
    assert gen.fallback_mode == "img2img"
    assert str(gen.fallback_workflow_path).endswith("product_scene.json")


def test_factory_inpaint_fallback_ipadapter_from_config(monkeypatch):
    monkeypatch.setattr(scene_generators, "PRODUCT_SCENE_BACKEND", "comfyui")
    monkeypatch.setattr(scene_generators, "COMFYUI_PRODUCT_SCENE_INPAINT_FALLBACK", "ipadapter")
    gen = scene_generators.get_product_scene_generator("inpaint")
    assert gen.fallback_mode == "ipadapter"
    assert str(gen.fallback_workflow_path).endswith("product_scene_ipadapter.json")
