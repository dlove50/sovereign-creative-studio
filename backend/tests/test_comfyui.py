"""ComfyUI adapter tests. All HTTP is faked, so these run without a ComfyUI
server or GPU."""
import asyncio
from pathlib import Path

import httpx
import pytest

import app.generators as generators
import app.generators.comfyui as comfyui_mod
from app.generators.comfyui import ComfyUIGenerator
from app.generators.mock import MockGenerator

WORKFLOW = Path(__file__).resolve().parent.parent / "workflows" / "text_to_image.json"
IMAGE_EDIT_WORKFLOW = (
    Path(__file__).resolve().parent.parent / "workflows" / "image_edit_qwen_2509.json"
)
TEST_STORAGE = Path(__file__).resolve().parent.parent / "storage" / "_test_comfyui"
_PNG_BYTES = b"\x89PNG\r\n\x1a\nFAKEIMAGE"


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
    """Records the submitted workflow and returns canned ComfyUI responses."""

    last_post_json = None
    last_upload_file = None
    last_view_params = None
    calls = []

    def __init__(self, *args, **kwargs):
        self.history_calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, data=None, files=None):
        if url == "/upload/image":
            _FakeAsyncClient.calls.append(("POST", url))
            _FakeAsyncClient.last_upload_file = files["image"][0]
            return _FakeResponse(json_data={"name": files["image"][0], "subfolder": ""})
        assert url == "/prompt"
        _FakeAsyncClient.calls.append(("POST", url))
        _FakeAsyncClient.last_post_json = json
        return _FakeResponse(json_data={"prompt_id": "pid-123"})

    async def get(self, url, params=None):
        if url.startswith("/history/"):
            _FakeAsyncClient.calls.append(("GET", url))
            self.history_calls += 1
            if self.history_calls == 1:
                return _FakeResponse(json_data={"pid-123": {}})
            return _FakeResponse(
                json_data={
                    "pid-123": {
                        "outputs": {
                            "9": {
                                "images": [
                                    {
                                        "filename": "sovereign_00001_.png",
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


def test_comfyui_generate_injects_prompt_and_saves_image(monkeypatch):
    _FakeAsyncClient.last_post_json = None
    _FakeAsyncClient.last_view_params = None
    _FakeAsyncClient.calls = []

    monkeypatch.setattr(comfyui_mod.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(comfyui_mod, "STORAGE_DIR", TEST_STORAGE)
    monkeypatch.setattr(comfyui_mod, "_POLL_INTERVAL_SECONDS", 0)

    gen = ComfyUIGenerator("http://comfy.local:8188/", str(WORKFLOW))
    result = asyncio.run(
        gen.generate(generation_id="abc123", prompt="a red fox in snow", media_type="image")
    )

    # Same response shape as the mock: a /storage/<id>.<ext> url.
    assert result.file_url == "/storage/abc123.png"
    saved = TEST_STORAGE / "abc123.png"
    assert saved.read_bytes() == _PNG_BYTES
    saved.unlink()

    # Prompt was injected into the workflow that got POSTed.
    posted = _FakeAsyncClient.last_post_json["prompt"]
    texts = [n.get("inputs", {}).get("text") for n in posted.values()]
    assert "a red fox in snow" in texts
    assert "__PROMPT__" not in texts

    assert _FakeAsyncClient.calls == [
        ("POST", "/prompt"),
        ("GET", "/history/pid-123"),
        ("GET", "/history/pid-123"),
        ("GET", "/view"),
    ]

    # The /view download used the filename from history.
    assert _FakeAsyncClient.last_view_params["filename"] == "sovereign_00001_.png"


def test_comfyui_image_edit_uploads_source_and_injects_prompt(monkeypatch):
    _FakeAsyncClient.last_post_json = None
    _FakeAsyncClient.last_upload_file = None
    _FakeAsyncClient.calls = []
    TEST_STORAGE.mkdir(parents=True, exist_ok=True)
    source = TEST_STORAGE / "source.png"
    source.write_bytes(_PNG_BYTES)

    monkeypatch.setattr(comfyui_mod.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(comfyui_mod, "STORAGE_DIR", TEST_STORAGE)
    monkeypatch.setattr(comfyui_mod, "_POLL_INTERVAL_SECONDS", 0)

    gen = ComfyUIGenerator(
        "http://comfy.local:8188/",
        str(WORKFLOW),
        str(IMAGE_EDIT_WORKFLOW),
    )
    result = asyncio.run(
        gen.generate(
            generation_id="edit123",
            prompt="make it a polished cartoon",
            media_type="image",
            mode="image_edit",
            source_image_url="/storage/source.png",
        )
    )

    assert result.file_url == "/storage/edit123.png"
    assert _FakeAsyncClient.last_upload_file == "source.png"
    posted = _FakeAsyncClient.last_post_json["prompt"]
    prompts = [n.get("inputs", {}).get("prompt") for n in posted.values()]
    images = [n.get("inputs", {}).get("image") for n in posted.values()]
    assert "make it a polished cartoon" in prompts
    assert "source.png" in images
    assert "__PROMPT__" not in prompts
    assert "__SOURCE_IMAGE__" not in images
    (TEST_STORAGE / "edit123.png").unlink()
    source.unlink()


def test_comfyui_image_edit_rejects_unsafe_source(monkeypatch):
    monkeypatch.setattr(comfyui_mod, "STORAGE_DIR", TEST_STORAGE)
    gen = ComfyUIGenerator("http://comfy.local:8188/", str(WORKFLOW), str(IMAGE_EDIT_WORKFLOW))
    with pytest.raises(RuntimeError) as exc:
        asyncio.run(
            gen.generate(
                generation_id="bad",
                prompt="edit",
                media_type="image",
                mode="image_edit",
                source_image_url="/storage/../secrets.png",
            )
        )
    assert "requires a source image stored under /storage" in str(exc.value)


def test_comfyui_raises_when_no_image_in_outputs(monkeypatch):
    class _NoImageClient(_FakeAsyncClient):
        async def get(self, url, params=None):
            if url.startswith("/history/"):
                return _FakeResponse(json_data={"pid-123": {"outputs": {"9": {}}}})
            raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr(comfyui_mod.httpx, "AsyncClient", _NoImageClient)
    monkeypatch.setattr(comfyui_mod, "STORAGE_DIR", TEST_STORAGE)

    gen = ComfyUIGenerator("http://comfy.local:8188", str(WORKFLOW))
    with pytest.raises(RuntimeError):
        asyncio.run(
            gen.generate(generation_id="x", prompt="hello", media_type="image")
        )


def test_comfyui_rejects_video_generation():
    gen = ComfyUIGenerator("http://comfy.local:8188", str(WORKFLOW))
    with pytest.raises(ValueError):
        asyncio.run(
            gen.generate(generation_id="x", prompt="hello", media_type="video")
        )


def test_factory_returns_comfyui_when_selected(monkeypatch):
    monkeypatch.setattr(generators, "GENERATOR_BACKEND", "comfyui")
    assert isinstance(generators.get_generator(), ComfyUIGenerator)


def test_factory_falls_back_to_mock(monkeypatch):
    monkeypatch.setattr(generators, "GENERATOR_BACKEND", "mock")
    assert isinstance(generators.get_generator(), MockGenerator)
    # Unknown value also falls back to mock rather than crashing.
    monkeypatch.setattr(generators, "GENERATOR_BACKEND", "banana")
    assert isinstance(generators.get_generator(), MockGenerator)
