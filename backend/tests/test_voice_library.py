"""Voice library: preview and clone endpoints."""
import os
import subprocess
import sys
import tempfile

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.routers import voice_library  # noqa: E402
from app.services import avatar_clone  # noqa: E402
from app.services.audio_merge import _ffmpeg  # noqa: E402


def _login(c, name):
    assert c.post("/api/auth/signup", json={"username": name, "password": "voicepass12", "name": "V"}).status_code == 201


def test_preview_rejects_ids_that_are_not_real_voices(monkeypatch):
    monkeypatch.setattr(voice_library.voice_provider, "list_voices", lambda: [{"id": "real-voice"}])
    with TestClient(app) as c:
        _login(c, "vl_user1")
        assert c.get("/api/voice-library/preview", params={"voice_id": "../../etc/passwd"}).status_code == 404


def test_piper_preview_is_synthesised_once_then_cached(monkeypatch):
    calls = []

    def fake_speech(text, out_path, voice_id=None):
        calls.append(voice_id)
        out_path.write_bytes(b"RIFFfake")

    monkeypatch.setattr(voice_library.voice_provider, "list_voices", lambda: [{"id": "en_US-amy-medium"}])
    monkeypatch.setattr(voice_library.voice_provider, "generate_speech", fake_speech)
    with TestClient(app) as c:
        _login(c, "vl_user2")
        first = c.get("/api/voice-library/preview", params={"voice_id": "en_US-amy-medium"})
        second = c.get("/api/voice-library/preview", params={"voice_id": "en_US-amy-medium"})
        assert first.status_code == 200 and first.json()["kind"] == "synthesised"
        assert second.json()["url"] == first.json()["url"] and calls == ["en_US-amy-medium"]
        assert c.get(first.json()["url"]).status_code == 200


def test_clone_voice_from_an_audio_file(tmp_path, monkeypatch):
    if not _ffmpeg():
        pytest.skip("FFmpeg not installed")
    wav = tmp_path / "me.wav"
    subprocess.run([_ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=200:duration=5", str(wav)], check=True)
    monkeypatch.setattr(avatar_clone, "register_voice", lambda name, sample: name)
    with TestClient(app) as c:
        _login(c, "vl_user3")
        r = c.post("/api/voice-library/clone", data={"name": "My Voice"}, files={"file": ("me.wav", wav.read_bytes())})
        assert r.status_code == 201 and r.json() == {"voice_id": "vibevoice:My-Voice", "name": "My-Voice"}
        assert c.post("/api/voice-library/clone", data={"name": "x"}, files={"file": ("a.txt", b"x")}).status_code == 400

        monkeypatch.setattr(avatar_clone, "register_voice", lambda name, sample: None)
        off = c.post("/api/voice-library/clone", data={"name": "Quiet"}, files={"file": ("me.wav", wav.read_bytes())})
        assert off.status_code == 503 and "not running" in off.json()["detail"]
