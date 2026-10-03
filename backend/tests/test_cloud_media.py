"""Cloud contract tests run without real keys, provider charges or GPU work."""
import json
import uuid
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app import config
from app.deps import get_current_user
from app.main import app
from app.services import cloud_media as cloud, integrations

REAL_CLIENT = httpx.Client


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(cloud, "root", lambda: tmp_path / "cloud")
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path / "secrets")
    for provider in ("heygen", "elevenlabs"):
        integrations.set_key(provider, "test-secret-do-not-expose")
        integrations.set_enabled(provider, True)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="owner", role="owner_admin")
    # No lifespan or production DB is needed for the cloud router.
    with TestClient(app, raise_server_exceptions=True) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def provider(monkeypatch):
    requests = []
    responses = []

    def handler(request):
        requests.append(request)
        assert responses, f"Unexpected network request: {request.method} {request.url}"
        status, body, content_type = responses.pop(0)
        if isinstance(body, dict):
            return httpx.Response(status, json=body)
        return httpx.Response(status, content=body, headers={"content-type": content_type})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(cloud.httpx, "Client", lambda **kwargs: REAL_CLIENT(transport=transport, **kwargs))
    return requests, responses


def payload(operation="tts", **overrides):
    return {"request_id": str(uuid.uuid4()), "operation": operation, "accept_charges": True,
            "text": "A short line.", "voice_id": "voice_123", "avatar_id": "look_123", **overrides}


def test_catalog_pagination_and_default_voice(client, provider):
    requests, responses = provider
    responses.append((200, {"data": [{"id": "look_123", "name": "Annie", "default_voice_id": "voice_123",
                                    "preview_image_url": "https://files.heygen.ai/preview.jpg"}],
                            "has_more": True, "next_token": "next-page"}, ""))
    result = client.get("/api/cloud/heygen/catalog/avatars?ownership=private&token=cursor").json()
    assert result["items"][0]["default_voice_id"] == "voice_123"
    assert result["next_token"] == "next-page"
    assert requests[0].url.path == "/v3/avatars/looks"
    assert requests[0].url.params["ownership"] == "private"
    assert requests[0].url.params["token"] == "cursor"
    responses.append((200, {"voices": [{"voice_id": "v1", "name": "Adam"}], "has_more": False}, ""))
    assert client.get("/api/cloud/elevenlabs/catalog/voices").json()["items"][0]["id"] == "v1"
    assert requests[-1].url.path == "/v2/voices"


@pytest.mark.parametrize("operation,endpoint", [("tts", "/v1/text-to-speech/voice_123"), ("sound-effects", "/v1/sound-generation")])
def test_text_generation_saved_once(client, provider, operation, endpoint):
    requests, responses = provider
    responses.append((200, b"ID3-generated-audio", "audio/mpeg"))
    body = payload(operation)
    assert client.post("/api/cloud/jobs", json=body).status_code == 202
    job = client.get(f"/api/cloud/jobs/{body['request_id']}").json()
    assert job["status"] == "completed"
    assert job["files"] == ["output.mp3"]
    assert "fingerprint" not in job
    output = client.get(f"/api/cloud/jobs/{job['id']}/files/output.mp3")
    assert output.content == b"ID3-generated-audio"
    assert requests[0].url.path == endpoint
    assert requests[0].headers["xi-api-key"] == "test-secret-do-not-expose"
    request_body = json.loads(requests[0].content)
    assert request_body["model_id"] == ("eleven_multilingual_v2" if operation == "tts" else "eleven_text_to_sound_v2")
    assert client.post("/api/cloud/jobs", json=body).status_code == 202
    assert len(requests) == 1  # Replaying a client request must never charge twice.
    body["text"] = "different"
    assert client.post("/api/cloud/jobs", json=body).status_code == 409


@pytest.mark.parametrize("operation,endpoint,extension", [
    ("voice-changer", "/v1/speech-to-speech/voice_123", "mp3"),
    ("isolate", "/v1/audio-isolation", "wav"),
    ("transcribe", "/v1/speech-to-text", "txt"),
])
def test_upload_workflows(client, provider, operation, endpoint, extension):
    requests, responses = provider
    response = {"text": "Hello world", "words": []} if operation == "transcribe" else b"audio"
    responses.append((200, response, "audio/wav" if operation == "isolate" else "audio/mpeg"))
    body = payload(operation)
    result = client.post("/api/cloud/upload-jobs", data={"payload": json.dumps(body)}, files={"file": ("recording.mp3", b"input recording", "audio/mpeg")})
    assert result.status_code == 202
    job = cloud.read(body["request_id"])
    assert job["status"] == "completed", job
    assert any(name.endswith(extension) for name in job["files"])
    assert requests[0].url.path == endpoint
    assert b"input recording" in requests[0].content
    assert not (cloud.folder(job["id"]) / "input.mp3").exists()
    if operation == "transcribe":
        assert (cloud.folder(job["id"]) / "transcript.txt").read_text() == "Hello world"


def test_heygen_submit_poll_download_never_leaks_key_to_cdn(client, provider):
    requests, responses = provider
    responses.append((200, {"data": {"video_id": "video123", "status": "pending"}}, ""))
    body = payload("avatar-video", voice_id="")
    client.post("/api/cloud/jobs", json=body)
    sent = json.loads(requests[0].content)
    assert sent["type"] == "avatar" and sent["avatar_id"] == "look_123"
    assert "voice_id" not in sent  # Preserve the original profile's default voice.
    assert sent["engine"] == {"type": "avatar_iv"}
    assert cloud.read(body["request_id"])["remote_id"] == "video123"
    responses.extend([(200, {"data": {"status": "completed", "video_url": "https://files.heygen.ai/video/test.mp4"}}, ""),
                      (200, b"video data", "video/mp4")])
    job = client.post(f"/api/cloud/jobs/{body['request_id']}/refresh").json()
    assert job["status"] == "completed"
    assert job["files"] == ["output.mp4"]
    assert "x-api-key" not in requests[-1].headers
    assert client.post(f"/api/cloud/jobs/{job['id']}/refresh").status_code == 200
    assert len(requests) == 3


def test_dubbing_submit_and_download(client, provider):
    requests, responses = provider
    responses.append((200, {"dubbing_id": "dub123"}, ""))
    body = payload("dubbing", target_lang="fr")
    client.post("/api/cloud/upload-jobs", data={"payload": json.dumps(body)}, files={"file": ("movie.mp4", b"movie", "video/mp4")})
    assert requests[0].url.path == "/v1/dubbing"
    assert b'name="target_lang"\r\n\r\nfr' in requests[0].content
    responses.extend([(200, {"status": "dubbed"}, ""), (200, b"dubbed movie", "video/mp4")])
    result = client.post(f"/api/cloud/jobs/{body['request_id']}/refresh").json()
    assert result["files"] == ["output.mp4"]
    assert requests[-1].url.path == "/v1/dubbing/dub123/audio/fr"


def test_disabled_and_validation_never_call_provider(client, provider):
    requests, _ = provider
    integrations.set_enabled("elevenlabs", False)
    assert client.post("/api/cloud/jobs", json=payload()).status_code == 409
    assert client.post("/api/cloud/jobs", json=payload(accept_charges=False)).status_code == 422
    assert client.post("/api/cloud/jobs", json=payload(voice_id="../../secret")).status_code == 422
    assert client.post("/api/cloud/jobs", json=payload("sound-effects", duration_seconds=100)).status_code == 422
    assert client.post("/api/cloud/jobs", json=payload("transcribe")).status_code == 400
    assert not requests


def test_provider_failure_is_saved_sanitized_without_retry(client, provider):
    requests, responses = provider
    responses.append((401, {"error": "test-secret-do-not-expose"}, ""))
    body = payload()
    client.post("/api/cloud/jobs", json=body)
    response = client.get("/api/cloud/jobs")
    assert response.json()[0]["status"] == "failed"
    assert "test-secret" not in response.text
    assert "key was rejected" in response.text
    assert len(requests) == 1


def test_untrusted_download_host_blocked_and_job_remains_retryable(client, provider):
    requests, responses = provider
    responses.extend([(200, {"data": {"video_id": "video123"}}, ""),
                      (200, {"data": {"status": "completed", "video_url": "https://127.0.0.1/private"}}, "")])
    body = payload("avatar-video")
    client.post("/api/cloud/jobs", json=body)
    result = client.post(f"/api/cloud/jobs/{body['request_id']}/refresh")
    assert result.status_code == 502
    assert cloud.read(body["request_id"])["status"] == "processing"
    assert len(requests) == 2


def test_admin_required_for_catalog_submit_and_download(client, provider):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="family", role="family")
    assert client.get("/api/cloud/status").status_code == 403
    assert client.get("/api/cloud/heygen/catalog/avatars").status_code == 403
    assert client.post("/api/cloud/jobs", json=payload()).status_code == 403
    assert client.get(f"/api/cloud/jobs/{uuid.uuid4()}/files/output.mp3").status_code == 403


def test_recovery_preserves_remote_jobs_and_does_not_resubmit(client, provider):
    job, _ = cloud.create(payload())
    remote, _ = cloud.create(payload("avatar-video"))
    remote.update(status="processing", remote_id="video123")
    cloud.save(remote)
    cloud.recover()
    assert cloud.read(job["id"])["status"] == "failed"
    assert cloud.read(remote["id"])["status"] == "processing"
    assert not provider[0]


def test_secrets_and_cloud_sources_not_served_as_public_storage(client, monkeypatch):
    monkeypatch.setattr(config, "SECRETS_DIR", config.STORAGE_DIR / "secrets")
    config.SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    (config.SECRETS_DIR / "private-test.txt").write_text("secret")
    source = config.STORAGE_DIR / "cloud" / "private-test.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("private")
    assert client.get("/storage/secrets/private-test.txt").status_code == 404
    assert client.get("/storage/cloud/private-test.txt").status_code == 404


def test_live_connection_check_is_read_only(client, provider):
    requests, responses = provider
    responses.append((200, {"voices": []}, ""))
    result = integrations.test_connection("elevenlabs")
    assert "Connected" in result["result"]
    assert [request.method for request in requests] == ["GET"]


def test_music_duration_and_instrumental_saved_once(client, provider):
    requests, responses = provider
    responses.append((200, b"ID3-music", "audio/mpeg"))
    body = payload("music", music_seconds=45, instrumental=True)
    assert client.post("/api/cloud/jobs", json=body).status_code == 202
    assert cloud.read(body["request_id"])["files"] == ["output.mp3"]
    assert requests[0].url.path == "/v1/music"
    assert json.loads(requests[0].content) == {
        "prompt": body["text"], "music_length_ms": 45000,
        "force_instrumental": True, "model_id": "music_v1",
    }
    assert client.post("/api/cloud/jobs", json=body).status_code == 202
    assert len(requests) == 1


def test_alignment_upload_preserves_timings_and_removes_source(client, provider):
    requests, responses = provider
    timings = {"words": [{"text": "Hello", "start": 0.25, "end": 0.8}], "characters": [], "loss": 0.1}
    responses.append((200, timings, ""))
    body = payload("align", text="Hello")
    result = client.post("/api/cloud/upload-jobs", data={"payload": json.dumps(body)},
                         files={"file": ("voice.wav", b"source", "audio/wav")})
    assert result.status_code == 202
    job = cloud.read(body["request_id"])
    assert job["status"] == "completed"
    assert job["files"] == ["alignment.json", "transcript.txt"]
    assert requests[0].url.path == "/v1/forced-alignment"
    assert b'name="text"\r\n\r\nHello' in requests[0].content
    assert json.loads((cloud.folder(job["id"]) / "alignment.json").read_text()) == timings
    assert not (cloud.folder(job["id"]) / "input.wav").exists()


@pytest.mark.parametrize("operation,fields", [
    ("music", {"music_seconds": 2}), ("music", {"music_seconds": 601}),
    ("music", {"text": "x" * 4101}), ("align", {"text": " "}),
])
def test_additional_tools_validate_before_provider_call(client, provider, operation, fields):
    assert client.post("/api/cloud/jobs", json=payload(operation, **fields)).status_code == 422
    assert not provider[0]
