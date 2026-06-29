"""Phase 14A: optional Seedance/C-Dance video provider safety and billing."""
import asyncio
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

from app.main import app
from app.video_generators.base import VideoResult
from app.video_generators.seedance import SeedanceVideoGenerator
import app.services.integrations as integrations
import app.services.video_jobs as video_jobs
import app.video_generators.seedance as seedance_module

HEADER = "X-SCS-Family-User-Id"
SECRET = "sd-secret-key-should-never-leak"


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
        json={"name": "Seedance test", "description": None},
        headers={HEADER: uid},
    ).json()["id"]


def _configure_seedance(client):
    client.post("/api/admin/integrations/seedance/key", json={"api_key": SECRET})
    client.post(
        "/api/admin/integrations/seedance/config",
        json={
            "base_url": "https://seedance.example",
            "model_id": "seedance-2.0",
            "create_endpoint": "/tasks",
            "status_endpoint": "/tasks/{task_id}",
        },
    )
    client.post("/api/admin/integrations/seedance/enabled", json={"enabled": True})


def _wait(client, uid, video_id, target, tries=60):
    for _ in range(tries):
        body = client.get(f"/api/videos/{video_id}", headers={HEADER: uid}).json()
        if body["status"] == target:
            return body
        time.sleep(0.1)
    raise AssertionError(f"video did not reach {target}: {body}")


def _charge_tx(client, uid, video_id):
    txns = client.get(
        "/api/admin/credits/transactions", params={"user_id": uid}
    ).json()
    return [
        t
        for t in txns
        if t["related_id"] == video_id and t["transaction_type"] == "generation_charge"
    ]


def test_seedance_not_configured_blocks_clearly(client):
    u = _user(client, "Seedance blocked")
    pid = _project(client, u["id"])

    resp = client.post(
        "/api/videos",
        json={
            "project_id": pid,
            "prompt": "premium clip",
            "motion_preset": "slow_zoom",
            "duration_seconds": 3,
            "mode": "text_to_video",
            "provider": "seedance_api",
        },
        headers={HEADER: u["id"]},
    )

    assert resp.status_code == 409
    assert resp.json()["detail"] == "Seedance provider is not configured. Admin setup required."


def test_seedance_modes_report_readiness_and_cost(client):
    modes = client.get("/api/videos/modes").json()
    text_mode = next(m for m in modes if m["id"] == "text_to_video")
    image_mode = next(m for m in modes if m["id"] == "image_to_video")
    extension_mode = next(m for m in modes if m["id"] == "video_extension")

    assert text_mode["providers"]["local_ltx"]["cost"] == 10
    assert text_mode["providers"]["seedance_api"]["cost"] == 30
    assert text_mode["providers"]["seedance_api"]["available"] is False
    assert image_mode["providers"]["seedance_api"]["available"] is False
    assert extension_mode["providers"]["seedance_api"]["available"] is False


def test_seedance_success_charges_30_and_stores_provider_task_id(client, monkeypatch):
    class _FakeSeedance:
        async def generate(self, **kwargs):
            assert kwargs["mode"] == "text_to_video"
            return VideoResult(
                result_url="/storage/videos/seedance-result.mp4",
                provider_task_id="task-123",
            )

    _configure_seedance(client)
    monkeypatch.setattr(
        video_jobs, "get_video_generator", lambda provider="local_ltx": _FakeSeedance()
    )
    u = _user(client, "Seedance success")
    pid = _project(client, u["id"])

    resp = client.post(
        "/api/videos",
        json={
            "project_id": pid,
            "prompt": "premium clip",
            "motion_preset": "slow_zoom",
            "duration_seconds": 3,
            "mode": "text_to_video",
            "provider": "seedance_api",
        },
        headers={HEADER: u["id"]},
    )
    assert resp.status_code == 201, resp.text
    video = _wait(client, u["id"], resp.json()["id"], "completed")

    assert video["provider"] == "seedance_api"
    assert video["provider_task_id"] == "task-123"
    assert video["credits_cost"] == 30
    charges = _charge_tx(client, u["id"], video["id"])
    assert len(charges) == 1
    assert charges[0]["amount"] == -30
    assert charges[0]["related_feature"] == "video_seedance"
    assert "provider=seedance_api" in charges[0]["note"]


def test_seedance_failure_does_not_charge(client, monkeypatch):
    class _Boom:
        async def generate(self, **kwargs):
            raise RuntimeError("provider failed without secret")

    _configure_seedance(client)
    monkeypatch.setattr(
        video_jobs, "get_video_generator", lambda provider="local_ltx": _Boom()
    )
    u = _user(client, "Seedance failure")
    pid = _project(client, u["id"])

    resp = client.post(
        "/api/videos",
        json={
            "project_id": pid,
            "prompt": "premium clip",
            "motion_preset": "slow_zoom",
            "duration_seconds": 3,
            "mode": "text_to_video",
            "provider": "seedance_api",
        },
        headers={HEADER: u["id"]},
    )
    video = _wait(client, u["id"], resp.json()["id"], "failed")

    assert video["provider"] == "seedance_api"
    assert _charge_tx(client, u["id"], video["id"]) == []


def test_seedance_insufficient_credits_blocks_before_provider_call(client, monkeypatch):
    called = False

    class _ShouldNotRun:
        async def generate(self, **kwargs):
            nonlocal called
            called = True
            return VideoResult(result_url="/storage/videos/nope.mp4")

    _configure_seedance(client)
    monkeypatch.setattr(
        video_jobs, "get_video_generator", lambda provider="local_ltx": _ShouldNotRun()
    )
    u = _user(client, "Seedance broke", credits=20)
    pid = _project(client, u["id"])

    resp = client.post(
        "/api/videos",
        json={
            "project_id": pid,
            "prompt": "premium clip",
            "motion_preset": "slow_zoom",
            "duration_seconds": 3,
            "mode": "text_to_video",
            "provider": "seedance_api",
        },
        headers={HEADER: u["id"]},
    )

    assert resp.status_code == 402
    assert called is False


def test_seedance_image_to_video_sends_reference_and_downloads_output(tmp_path, monkeypatch):
    calls = []

    class _Response:
        def __init__(self, body=None, content=b"", headers=None):
            self._body = body or {}
            self.content = content
            self.headers = headers or {}

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

        async def post(self, url, headers=None, json=None):
            calls.append(("post", url, headers, json))
            return _Response({"task_id": "task-img", "video_url": "https://cdn.example.com/out.mp4"})

        async def get(self, url, **kwargs):
            calls.append(("get", url, kwargs, None))
            return _Response(content=b"fake mp4 bytes", headers={"content-type": "video/mp4"})

    monkeypatch.setattr(seedance_module, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(seedance_module.httpx, "AsyncClient", _Client)

    result = asyncio.run(
        SeedanceVideoGenerator(
            {
                "enabled": True,
                "api_key": SECRET,
                "base_url": "https://seedance.example",
                "model_id": "seedance-2.0",
                "create_endpoint": "/tasks",
                "status_endpoint": "/tasks/{task_id}",
            }
        ).generate(
            video_id="vid123",
            source_image_url="https://assets.example.com/source.png",
            prompt="move",
            motion_preset="slow_zoom",
            duration_seconds=3,
            mode="image_to_video",
        )
    )

    posted = calls[0][3]
    assert posted["image_url"] == "https://assets.example.com/source.png"
    assert calls[0][2]["Authorization"] == f"Bearer {SECRET}"
    assert result.provider_task_id == "task-img"
    assert result.result_url == "/storage/videos/vid123.mp4"
    assert (tmp_path / "videos" / "vid123.mp4").read_bytes() == b"fake mp4 bytes"


def test_seedance_rejects_unsafe_output_url(monkeypatch):
    class _Response:
        content = b""
        headers = {}

        def raise_for_status(self):
            return None

        def json(self):
            return {"task_id": "task-bad", "video_url": "http://127.0.0.1/private.mp4"}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return _Response()

    monkeypatch.setattr(seedance_module.httpx, "AsyncClient", _Client)

    with pytest.raises(RuntimeError) as exc:
        asyncio.run(
            SeedanceVideoGenerator(
                {
                    "enabled": True,
                    "api_key": SECRET,
                    "base_url": "https://seedance.example",
                    "model_id": "seedance-2.0",
                    "create_endpoint": "/tasks",
                    "status_endpoint": "/tasks/{task_id}",
                }
            ).generate(
                video_id="bad",
                source_image_url="",
                prompt="move",
                motion_preset="slow_zoom",
                duration_seconds=3,
                mode="text_to_video",
            )
        )

    message = str(exc.value)
    assert "unsafe output URL" in message
    assert SECRET not in message
