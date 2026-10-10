"""Voice Studio: the Sovereign side of the VibeVoice integration (the engine service is faked)."""
import os
import struct
import sys
import tempfile

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import voice_studio as vs  # noqa: E402


def _wav(seconds: float = 2.0) -> bytes:
    samples = int(24000 * seconds)
    data = b"\x00\x00" * samples
    header = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, 24000, 48000, 2, 16)
    return header + b"data" + struct.pack("<I", len(data)) + data


@pytest.fixture()
def engine(monkeypatch):
    seen = {"calls": []}

    def fake_call(method, path, body=None, timeout=30.0):
        seen["calls"].append((method, path, body))
        if path == "/status":
            return {"ready": True, "loading": None, "model": "VibeVoice 1.5B: faster, clones your voices", "kind": "full", "generating": False, "voices": 3}
        if path == "/models":
            return {"current": "m", "models": [{"label": "VibeVoice 1.5B: faster, clones your voices", "kind": "full"}]}
        if path == "/voices":
            return {"voices": [{"name": "en-Alice_woman", "file": "en-Alice_woman.wav", "preset": True}], "realtime": ["en-Emma_woman"]}
        if path == "/examples":
            return {"examples": [{"num_speakers": 2, "script": "Speaker 1: Hi\nSpeaker 2: Hello"}]}
        if path == "/generate":
            return {"id": "job123"}
        if path == "/realtime":
            return {"id": "rt456"}
        if path.startswith("/jobs/job123/chunks"):
            return {"sample_rate": 24000, "next": 1, "chunks": ["AAAA"], "status": "running"}
        if path == "/jobs/job123":
            return {"id": "job123", "kind": "podcast", "status": "done", "log": "ok", "error": None, "chunk_count": 1, "streamed_seconds": 2.0,
                    "elapsed": 12.5, "has_audio": True, "meta": {"speakers": ["en-Alice_woman"], "model": "m", "cfg_scale": 1.3, "inference_steps": 5, "seed": 42}}
        if path == "/jobs/job123/stop":
            return {"stopping": True}
        raise vs.VoiceStudioError("unexpected " + path)

    monkeypatch.setattr(vs, "call", fake_call)
    monkeypatch.setattr(vs, "fetch_bytes", lambda path, timeout=60.0: _wav())
    monkeypatch.setattr(vs, "engine_status", lambda: {"installed": True, "online": True, "ready": True, "loading": None, "model": "m", "kind": "full",
                                                      "generating": False, "voices": 3})
    return seen


def _client():
    c = TestClient(app)
    assert c.post("/api/auth/signup", json={"username": "vs_user", "password": "voicepass1", "name": "VS"}).status_code in (201, 409)
    return c


def test_status_models_voices_and_examples_are_forwarded(engine):
    with TestClient(app) as c:
        assert c.get("/api/voice-studio/status").json()["ready"] is True
        assert c.get("/api/voice-studio/models").json()["models"][0]["kind"] == "full"
        voices = c.get("/api/voice-studio/voices").json()
        assert voices["voices"][0]["name"] == "en-Alice_woman" and voices["realtime"] == ["en-Emma_woman"]
        assert c.get("/api/voice-studio/examples").json()["examples"][0]["num_speakers"] == 2


def test_generate_validates_and_forwards(engine):
    with TestClient(app) as c:
        bad = c.post("/api/voice-studio/generate", json={"script": "", "num_speakers": 2, "speakers": []})
        assert bad.status_code == 422
        too_many = c.post("/api/voice-studio/generate", json={"script": "hi", "num_speakers": 5, "speakers": []})
        assert too_many.status_code == 422
        ok = c.post("/api/voice-studio/generate", json={"script": "Speaker 1: Hi", "num_speakers": 1, "speakers": ["en-Alice_woman"], "seed": -1})
        assert ok.status_code == 202 and ok.json()["id"] == "job123"
        sent = [b for m, p, b in engine["calls"] if p == "/generate"][0]
        assert sent["speakers"] == ["en-Alice_woman"] and sent["seed"] == -1 and sent["disable_voice_cloning"] is False


def test_a_finished_job_is_saved_to_the_library_once_and_can_be_deleted(engine):
    with TestClient(app) as c:
        c.post("/api/voice-studio/generate", json={"script": "Speaker 1: Hi there", "num_speakers": 1, "speakers": ["en-Alice_woman"]})
        first = c.get("/api/voice-studio/jobs/job123").json()
        assert first["status"] == "done" and first["clip"]["id"]
        again = c.get("/api/voice-studio/jobs/job123").json()
        assert again["clip"]["id"] == first["clip"]["id"]  # saved once
        clips = c.get("/api/voice-studio/clips").json()
        assert any(x["id"] == first["clip"]["id"] and x["script"] == "Speaker 1: Hi there" for x in clips)
        audio = c.get(f"/api/voice-studio/clips/{first['clip']['id']}/audio")
        assert audio.status_code == 200 and audio.content[:4] == b"RIFF"
        assert c.delete(f"/api/voice-studio/clips/{first['clip']['id']}").status_code == 204
        assert not any(x["id"] == first["clip"]["id"] for x in c.get("/api/voice-studio/clips").json())
        assert c.get(f"/api/voice-studio/clips/{first['clip']['id']}/audio").status_code == 404


def test_chunks_and_stop_are_forwarded(engine):
    with TestClient(app) as c:
        out = c.get("/api/voice-studio/jobs/job123/chunks?after=0").json()
        assert out["next"] == 1 and out["chunks"] == ["AAAA"]
        assert c.post("/api/voice-studio/jobs/job123/stop").json()["stopping"] is True


def test_an_asleep_engine_is_reported_not_crashed(monkeypatch):
    monkeypatch.setattr(vs, "installed", lambda: True)

    def down(method, path, body=None, timeout=30.0):
        raise vs.VoiceStudioError("The voice engine is not running.")

    monkeypatch.setattr(vs, "call", down)
    with TestClient(app) as c:
        status = c.get("/api/voice-studio/status").json()
        assert status["online"] is False and status["ready"] is False
        refused = c.get("/api/voice-studio/voices")
        assert refused.status_code == 409 and "not running" in refused.json()["detail"]


def test_a_voice_upload_is_checked_and_forwarded(engine, monkeypatch):
    got = {}

    def fake_upload(filename, content):
        got["name"], got["size"] = filename, len(content)
        return {"added": "my-voice", "voices": ["en-Alice_woman", "my-voice"]}

    monkeypatch.setattr(vs, "upload_voice", fake_upload)
    with TestClient(app) as c:
        assert c.post("/api/voice-studio/voices", files={"file": ("empty.wav", b"")}).status_code == 422
        ok = c.post("/api/voice-studio/voices", files={"file": ("my voice.m4a", b"1234567890")})
        assert ok.status_code == 201 and ok.json()["added"] == "my-voice" and got == {"name": "my voice.m4a", "size": 10}


def test_a_busy_render_engine_is_explained_not_a_server_error(monkeypatch):
    monkeypatch.setattr(vs, "installed", lambda: True)
    monkeypatch.setattr(vs, "engine_status", lambda: {"installed": True, "online": False, "ready": False, "loading": None, "model": None,
                                                      "kind": None, "generating": False, "voices": 0})
    monkeypatch.setattr(vs, "stop_gradio_demo", lambda: False)

    def busy():
        raise vs.VoiceStudioError("The image, video or music engine is busy rendering. Wait for it to finish, then start the voice engine.")

    monkeypatch.setattr(vs, "free_graphics_card", busy)
    with TestClient(app) as c:
        out = c.post("/api/voice-studio/start", json={})
        assert out.status_code == 409 and "busy rendering" in out.json()["detail"]


def test_an_unexpected_start_failure_gets_a_readable_message(monkeypatch):
    def boom(model=None):
        raise OSError("disk exploded")

    monkeypatch.setattr(vs, "start", boom)
    with TestClient(app) as c:
        out = c.post("/api/voice-studio/start", json={})
        assert out.status_code == 409 and "disk exploded" in out.json()["detail"]
