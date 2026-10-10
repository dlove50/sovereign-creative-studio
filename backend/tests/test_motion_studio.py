"""Real media processing and mocked provider contracts; never consumes cloud credits."""
import io
import json
import shutil
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import fal_client
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app import config
from app.deps import get_current_user
from app.routers.motion_studio import router
from app.services import motion_studio as studio, integrations
from app.services.private_storage import PublicStorage


@pytest.fixture
def client(tmp_path, monkeypatch):
    storage = tmp_path / "storage"
    storage.mkdir()
    monkeypatch.setattr(config, "STORAGE_DIR", storage)
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path / "secrets")
    monkeypatch.delenv("FAL_KEY", raising=False)
    app = FastAPI()
    app.include_router(router)
    app.mount("/storage", PublicStorage(directory=storage))
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="owner", role="owner_admin")
    with TestClient(app) as test:
        yield test


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg unavailable")
    path = tmp_path_factory.mktemp("motion-media") / "source.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x320:rate=24",
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", "3", "-c:v", "libx264", "-c:a", "aac", str(path)], check=True)
    return path.read_bytes()


def upload(client, media, request_id=None):
    return client.post("/api/motion-studio/jobs", data={"request_id": request_id or str(uuid.uuid4()), "title": "Synthetic test", "seconds": 2},
                       files={"file": ("source.mp4", media, "video/mp4")})


def ready(client, media):
    response = upload(client, media)
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]
    assert client.get(f"/api/motion-studio/jobs/{job_id}").json()["status"] == "review"
    assert client.post(f"/api/motion-studio/jobs/{job_id}/approve").status_code == 200
    image = io.BytesIO()
    Image.new("RGB", (64, 64), (12, 210, 150)).save(image, "PNG")
    assert client.post(f"/api/motion-studio/jobs/{job_id}/characters/1", files={"file": ("ref.png", image.getvalue(), "image/png")}).status_code == 200
    return job_id


def payload(**extra):
    return {"request_id": str(uuid.uuid4()), "accept_charges": True, **extra}


def test_real_preparation_idempotency_and_private_storage(client, media):
    request_id = str(uuid.uuid4())
    assert upload(client, media, request_id).status_code == 202
    job = client.get(f"/api/motion-studio/jobs/{request_id}").json()
    assert job["status"] == "review"
    assert "fingerprint" not in job and "user_id" not in job
    info = studio.probe(studio.folder(request_id) / "prepared.mp4")
    assert info["has_audio"] and info["duration"] == pytest.approx(2, abs=.1)
    assert upload(client, media, request_id).status_code == 202
    assert len(client.get("/api/motion-studio/jobs").json()) == 1
    assert client.get(f"/storage/motion_studio/{request_id}/job.json").status_code == 404
    assert client.get(f"/storage/motion_studio/{request_id}/prepared.mp4").status_code == 404
    assert client.get(f"/api/motion-studio/jobs/{request_id}/files/prepared.mp4").status_code == 200
    client.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="other", role="owner_admin")
    assert client.get(f"/api/motion-studio/jobs/{request_id}").status_code == 404
    assert client.get(f"/api/motion-studio/jobs/{request_id}/files/prepared.mp4").status_code == 404
    assert client.get("/api/motion-studio/jobs").json() == []


def test_approval_setup_and_authorization_guards(client, media):
    job_id = upload(client, media).json()["id"]
    path = f"/api/motion-studio/jobs/{job_id}"
    assert client.post(path + "/render/draft", json=payload()).status_code == 409
    assert client.post(path + "/approve").status_code == 200
    assert client.post(path + "/render/draft", json=payload()).status_code == 409
    ready_id = ready(client, media)
    assert client.post(f"/api/motion-studio/jobs/{ready_id}/render/draft", json=payload()).status_code == 409
    assert client.post(path + "/render/draft", json={"request_id": str(uuid.uuid4()), "accept_charges": False}).status_code == 422
    assert client.post(path + "/characters/3", files={"file": ("x.png", b"x")}).status_code == 422
    client.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="family", role="family_user")
    assert client.get("/api/motion-studio/status").status_code == 403
    assert client.get(path).status_code == 403


def test_reject_invalid_media_and_bounds(client, media):
    assert upload(client, b"not a movie").status_code == 422
    assert client.post("/api/motion-studio/jobs", data={"request_id": str(uuid.uuid4()), "seconds": 31}, files={"file": ("source.mp4", media)}).status_code == 422
    job_id = upload(client, media).json()["id"]
    assert client.post(f"/api/motion-studio/jobs/{job_id}/characters/1", files={"file": ("ref.jpg", b"not an image")}).status_code == 422
    assert client.get("/api/motion-studio/jobs/not-a-uuid").status_code == 404


def test_remove_character_and_provider_rejection(client, media, monkeypatch):
    job_id = ready(client, media)
    path = f"/api/motion-studio/jobs/{job_id}"
    assert client.delete(path + "/characters/1").status_code == 200
    assert client.get(path).json()["characters"] == []
    assert client.get(path + "/files/character-1.jpg").status_code == 404
    job = studio.read(job_id)
    job.update(status="rendering")
    job["operations"] = [{"id": "op", "kind": "draft", "status": "rendering", "remote_id": "rid", "model": studio.MODEL}]
    studio.save(job)
    fake = SimpleNamespace(get_handle=lambda model, rid: SimpleNamespace(status=lambda: fal_client.Completed(logs=[], metrics={}, error="rejected")))
    monkeypatch.setattr(studio, "sdk", lambda: fake)
    assert client.delete(path + "/characters/1").status_code == 409
    rejected = client.post(path + "/refresh").json()
    assert rejected["status"] == "failed"
    assert rejected["operations"][0]["remote_id"] == "rid"


def test_silent_source_remains_silent_and_private_download_rejected(client, media, tmp_path):
    raw = tmp_path / "raw.mp4"
    output = tmp_path / "silent.mp4"
    raw.write_bytes(media)
    studio.restore_audio(raw, raw, output, False)
    assert studio.probe(output)["has_audio"] is False
    with pytest.raises(ValueError):
        studio._download("https://127.0.0.1/private.mp4", tmp_path / "download.mp4")
    assert not (tmp_path / "download.mp4").exists()


def test_draft_and_native_completion_no_duplicate_paid_posts(client, media, monkeypatch):
    job_id = ready(client, media)
    calls = []
    result = {"video": {"url": "https://v3.fal.media/generated.mp4"}, "draft_id": "provider-draft-original", "seed": 123}
    fake_sdk = SimpleNamespace(key="never-expose-test-key", upload_file=lambda path: "https://v3.fal.media/" + path.name,
                               get_handle=lambda model, rid: SimpleNamespace(status=lambda: fal_client.Completed(logs=[], metrics={}), get=lambda: result))
    monkeypatch.setattr(studio, "sdk", lambda: fake_sdk)
    real_client = httpx.Client

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"request_id": "remote-" + str(len(calls))})

    monkeypatch.setattr(studio.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setattr(studio, "_download", lambda url, destination: destination.write_bytes(media))
    body = payload(prompt="Replace @Video1 character with @Image1", scene="A green studio")
    path = f"/api/motion-studio/jobs/{job_id}"
    assert client.post(path + "/render/draft", json=body).status_code == 202
    assert client.post(path + "/render/draft", json=body).status_code == 202
    assert len(calls) == 1
    draft_input = json.loads(calls[0].content)
    assert draft_input["task"] == "editing" and draft_input["draft"] is True
    assert draft_input["video_urls"] == ["https://v3.fal.media/prepared.mp4"]
    assert "A green studio" in draft_input["prompt"]
    assert client.post(path + "/render/draft", json={**body, "prompt": "different"}).status_code == 409
    refreshed = client.post(path + "/refresh").json()
    assert refreshed["status"] == "draft", refreshed
    draft = refreshed["operations"][0]
    assert draft["draft_id"] == "provider-draft-original"
    assert studio.probe(studio.folder(job_id) / draft["file"])["has_audio"]
    assert "never-expose-test-key" not in json.dumps(refreshed)
    final = payload(draft_id=draft["id"])
    assert client.post(path + "/render/final", json=final).status_code == 202
    assert json.loads(calls[1].content) == {"draft_id": "provider-draft-original", "resolution": "1080p", "codec": "H264"}
    assert client.post(path + "/render/final", json=final).status_code == 202
    assert len(calls) == 2
    completed = client.post(path + "/refresh").json()
    assert completed["status"] == "completed" and completed["final_file"]


def test_interrupted_submission_never_automatically_replayed(client, media, monkeypatch):
    job_id = ready(client, media)
    monkeypatch.setattr(studio, "sdk", lambda: SimpleNamespace(key="key", upload_file=lambda p: "https://v3.fal.media/x"))
    real_client = httpx.Client
    requests = []

    def fail(request):
        requests.append(request)
        raise httpx.ReadTimeout("lost response")

    monkeypatch.setattr(studio.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(fail), **kwargs))
    body = payload()
    path = f"/api/motion-studio/jobs/{job_id}"
    client.post(path + "/render/draft", json=body)
    job = client.get(path).json()
    assert job["status"] == "failed"
    assert "billing outcome may be unknown" in job["error"]
    client.post(path + "/render/draft", json=body)
    assert len(requests) == 1


def test_recovery_and_expiry_do_not_submit(client, media, monkeypatch):
    job_id = ready(client, media)
    job = studio.read(job_id)
    job["status"] = "submitting"
    job["operations"] = [{"id": "interrupted", "status": "submitting"}]
    studio.save(job)
    studio.recover()
    assert studio.read(job_id)["status"] == "failed"
    job = studio.read(job_id)
    draft_id = str(uuid.uuid4())
    job["operations"] = [{"id": draft_id, "kind": "draft", "status": "completed", "draft_id": "expired-native",
                          "expires_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()}]
    studio.save(job)
    assert client.post(f"/api/motion-studio/jobs/{job_id}/render/final", json=payload(draft_id=draft_id)).status_code == 409
