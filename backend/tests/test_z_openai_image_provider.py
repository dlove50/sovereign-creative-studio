"""Phase 14B: optional OpenAI Image API provider safety and billing."""
import asyncio
import base64
import os
import sys
import tempfile
import time

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")
    os.environ["DEFAULT_CREDITS"] = "100"

import pytest
from fastapi.testclient import TestClient

from app.generators.base import GenerationResult
from app.generators.openai_image import OpenAIImageGenerator
from app.main import app
import app.generators.openai_image as openai_image_module
import app.services.generation_jobs as generation_jobs
import app.services.integrations as integrations

HEADER = "X-SCS-Family-User-Id"
SECRET = "sk-openai-secret-should-never-leak"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _isolated_integrations(monkeypatch, tmp_path):
    path = tmp_path / "integrations.json"
    monkeypatch.setattr(integrations, "_path", lambda: path)
    yield


def _user(client, name, credits=100):
    return client.post(
        "/api/admin/family-users",
        json={"display_name": name, "role": "family_user", "initial_credits": credits},
    ).json()


def _project(client, uid):
    return client.post(
        "/api/projects",
        json={"name": "OpenAI image test", "description": None},
        headers={HEADER: uid},
    ).json()["id"]


def _configure_openai(client):
    client.post("/api/admin/integrations/openai/key", json={"api_key": SECRET})
    client.post(
        "/api/admin/integrations/openai/config",
        json={
            "base_url": "https://api.openai.example/v1",
            "image_model": "gpt-image-2",
            "image_size": "1024x1024",
            "image_quality": "low",
        },
    )
    client.post("/api/admin/integrations/openai/enabled", json={"enabled": True})


def _wait(client, uid, generation_id, target, tries=60):
    for _ in range(tries):
        body = client.get(f"/api/generations/{generation_id}", headers={HEADER: uid}).json()
        if body["status"] == target:
            return body
        time.sleep(0.1)
    raise AssertionError(f"generation did not reach {target}: {body}")


def _charge_tx(client, uid, generation_id):
    txns = client.get(
        "/api/admin/credits/transactions", params={"user_id": uid}
    ).json()
    return [
        t
        for t in txns
        if t["related_id"] == generation_id and t["transaction_type"] == "generation_charge"
    ]


def test_local_image_provider_remains_default(client):
    modes = client.get("/api/generations/modes").json()
    text_mode = next(m for m in modes if m["id"] == "text_to_image")
    assert text_mode["providers"]["local_comfyui"]["available"] is True
    assert text_mode["providers"]["local_comfyui"]["cost"] == 5

    resp = client.post(
        "/api/generations",
        json={"prompt": "local default image", "media_type": "image"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["provider"] == "local_comfyui"


def test_openai_not_configured_blocks_clearly(client):
    u = _user(client, "OpenAI blocked")
    pid = _project(client, u["id"])

    resp = client.post(
        "/api/generations",
        json={
            "project_id": pid,
            "prompt": "premium image",
            "media_type": "image",
            "provider": "openai_image_api",
        },
        headers={HEADER: u["id"]},
    )

    assert resp.status_code == 409
    assert resp.json()["detail"] == "OpenAI provider is not configured. Admin setup required."


def test_openai_key_is_masked_and_never_returned(client):
    out = client.post("/api/admin/integrations/openai/key", json={"api_key": SECRET}).json()
    openai = next(p for p in out if p["id"] == "openai")
    assert openai["configured"] is True
    assert openai["masked_key"] and SECRET not in openai["masked_key"]
    assert SECRET not in client.get("/api/admin/integrations").text


def test_openai_success_charges_15_and_uses_image_ledger(client, monkeypatch):
    class _FakeOpenAI:
        async def generate(self, **kwargs):
            assert kwargs["mode"] == "text_to_image"
            return GenerationResult(file_url="/storage/generated/openai-result.png")

    _configure_openai(client)
    monkeypatch.setattr(
        generation_jobs, "get_generator", lambda provider="local_comfyui", quality_preset=None: _FakeOpenAI()
    )
    u = _user(client, "OpenAI success")
    pid = _project(client, u["id"])

    resp = client.post(
        "/api/generations",
        json={
            "project_id": pid,
            "prompt": "premium image",
            "media_type": "image",
            "provider": "openai_image_api",
            "mode": "text_to_image",
        },
        headers={HEADER: u["id"]},
    )
    assert resp.status_code == 201, resp.text
    generation = _wait(client, u["id"], resp.json()["id"], "completed")

    assert generation["provider"] == "openai_image_api"
    assert generation["provider_model"] == "gpt-image-2"
    assert generation["credits_cost"] == 15
    charges = _charge_tx(client, u["id"], generation["id"])
    assert len(charges) == 1
    assert charges[0]["amount"] == -15
    assert charges[0]["related_feature"] == "image_openai"
    assert "provider=openai_image_api" in charges[0]["note"]
    library = client.get("/api/library", headers={HEADER: u["id"]}).json()
    assert any(
        item["type"] == "image"
        and item["source_entity_id"] == generation["id"]
        and item["asset_url"] == generation["file_url"]
        for item in library
    )


def test_openai_failure_does_not_charge(client, monkeypatch):
    class _Boom:
        async def generate(self, **kwargs):
            raise RuntimeError("provider failed without secret")

    _configure_openai(client)
    monkeypatch.setattr(
        generation_jobs, "get_generator", lambda provider="local_comfyui", quality_preset=None: _Boom()
    )
    u = _user(client, "OpenAI failure")
    pid = _project(client, u["id"])
    resp = client.post(
        "/api/generations",
        json={
            "project_id": pid,
            "prompt": "premium image",
            "media_type": "image",
            "provider": "openai_image_api",
        },
        headers={HEADER: u["id"]},
    )
    generation = _wait(client, u["id"], resp.json()["id"], "failed")
    assert generation["provider"] == "openai_image_api"
    assert _charge_tx(client, u["id"], generation["id"]) == []


def test_openai_insufficient_credits_blocks_before_provider_call(client, monkeypatch):
    called = False

    class _ShouldNotRun:
        async def generate(self, **kwargs):
            nonlocal called
            called = True
            return GenerationResult(file_url="/storage/generated/nope.png")

    _configure_openai(client)
    monkeypatch.setattr(
        generation_jobs, "get_generator", lambda provider="local_comfyui", quality_preset=None: _ShouldNotRun()
    )
    u = _user(client, "OpenAI broke", credits=10)
    pid = _project(client, u["id"])
    resp = client.post(
        "/api/generations",
        json={
            "project_id": pid,
            "prompt": "premium image",
            "media_type": "image",
            "provider": "openai_image_api",
        },
        headers={HEADER: u["id"]},
    )
    assert resp.status_code == 402
    assert called is False


def test_openai_adapter_text_to_image_saves_local_png(tmp_path, monkeypatch):
    png = b"fake png bytes"
    encoded = base64.b64encode(png).decode("ascii")
    calls = []

    class _Response:
        def __init__(self, body):
            self._body = body
            self.headers = {}
            self.content = b""

        def raise_for_status(self):
            return None

        def json(self):
            return self._body

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, headers=None, json=None, data=None, files=None):
            calls.append({"url": url, "headers": headers, "json": json, "data": data, "files": files})
            return _Response({"data": [{"b64_json": encoded}]})

    monkeypatch.setattr(openai_image_module, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(openai_image_module.httpx, "AsyncClient", _Client)

    result = asyncio.run(
        OpenAIImageGenerator(
            {
                "enabled": True,
                "api_key": SECRET,
                "base_url": "https://api.openai.example/v1",
                "image_model": "gpt-image-2",
                "image_size": "1024x1024",
                "image_quality": "low",
            }
        ).generate(
            generation_id="gen123",
            prompt="luxury image",
            media_type="image",
            mode="text_to_image",
        )
    )

    assert calls[0]["url"].endswith("/images/generations")
    assert calls[0]["headers"]["Authorization"] == f"Bearer {SECRET}"
    assert calls[0]["json"]["model"] == "gpt-image-2"
    assert result.file_url == "/storage/generated/gen123.png"
    assert (tmp_path / "generated" / "gen123.png").read_bytes() == png


def test_openai_adapter_image_edit_sends_image_file(tmp_path, monkeypatch):
    source_dir = tmp_path / "uploads"
    source_dir.mkdir()
    source = source_dir / "source.png"
    source.write_bytes(b"source bytes")
    encoded = base64.b64encode(b"edited png").decode("ascii")
    calls = []

    class _Response:
        headers = {}
        content = b""

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"b64_json": encoded}]}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, headers=None, json=None, data=None, files=None):
            calls.append({"url": url, "headers": headers, "json": json, "data": data, "files": files})
            return _Response()

    monkeypatch.setattr(openai_image_module, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(openai_image_module.httpx, "AsyncClient", _Client)

    result = asyncio.run(
        OpenAIImageGenerator(
            {
                "enabled": True,
                "api_key": SECRET,
                "base_url": "https://api.openai.example/v1",
                "image_model": "gpt-image-2",
                "image_size": "1024x1024",
                "image_quality": "low",
            }
        ).generate(
            generation_id="edit123",
            prompt="edit image",
            media_type="image",
            mode="image_edit",
            source_image_url="/storage/uploads/source.png",
        )
    )

    assert calls[0]["url"].endswith("/images/edits")
    assert calls[0]["data"]["model"] == "gpt-image-2"
    assert calls[0]["files"]["image"][0] == "source.png"
    assert result.file_url == "/storage/generated/edit123.png"


def test_openai_rejects_unsafe_output_url(monkeypatch):
    class _Response:
        headers = {}
        content = b""

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"url": "http://127.0.0.1/private.png"}]}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return _Response()

    monkeypatch.setattr(openai_image_module.httpx, "AsyncClient", _Client)

    with pytest.raises(RuntimeError) as exc:
        asyncio.run(
            OpenAIImageGenerator(
                {
                    "enabled": True,
                    "api_key": SECRET,
                    "base_url": "https://api.openai.example/v1",
                    "image_model": "gpt-image-2",
                    "image_size": "1024x1024",
                    "image_quality": "low",
                }
            ).generate(
                generation_id="bad",
                prompt="bad",
                media_type="image",
                mode="text_to_image",
            )
        )

    message = str(exc.value)
    assert "unsafe output URL" in message
    assert SECRET not in message


def test_resolve_storage_path_handles_nested_posix_path(monkeypatch, tmp_path):
    """A /storage/ URL with subdirectories must resolve to the real nested file.

    Regression: the separator was rewritten to a backslash, which pathlib treats
    as a separator on Windows but as a literal filename character on Linux.
    """
    nested = tmp_path / "uploads" / "source.png"
    nested.parent.mkdir(parents=True)
    nested.write_bytes(b"source bytes")
    monkeypatch.setattr(openai_image_module, "STORAGE_DIR", tmp_path)

    resolved = openai_image_module._resolve_storage_path("/storage/uploads/source.png")

    assert resolved == nested.resolve()
    assert resolved.is_file()


def test_resolve_storage_path_accepts_absolute_url(monkeypatch, tmp_path):
    nested = tmp_path / "uploads" / "source.png"
    nested.parent.mkdir(parents=True)
    nested.write_bytes(b"source bytes")
    monkeypatch.setattr(openai_image_module, "STORAGE_DIR", tmp_path)

    resolved = openai_image_module._resolve_storage_path(
        "https://studio.example/storage/uploads/source.png"
    )

    assert resolved == nested.resolve()


def test_resolve_storage_path_rejects_paths_outside_storage(monkeypatch, tmp_path):
    storage = tmp_path / "storage"
    storage.mkdir()
    (tmp_path / "secret.txt").write_bytes(b"secret")
    monkeypatch.setattr(openai_image_module, "STORAGE_DIR", storage)

    # Traversal, a leading slash that would otherwise reset the join, and a URL
    # that is not under /storage/ at all.
    assert openai_image_module._resolve_storage_path("/storage/../secret.txt") is None
    assert openai_image_module._resolve_storage_path("/storage//etc/passwd") is None
    assert openai_image_module._resolve_storage_path("/uploads/source.png") is None
