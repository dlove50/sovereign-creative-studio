"""VibeVoice cloned-voice bridge in the voice service (fake VibeVoice server)."""
import os
import sys
import tempfile

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")
    os.environ["DEFAULT_CREDITS"] = "100"
    os.environ["DEFAULT_SIGNUP_CREDITS"] = "50"

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.services import voice as vsvc  # noqa: E402

_REAL_CLIENT = httpx.Client


def _fake_vibevoice(monkeypatch, *, final_status="done", calls=None):
    """Route every httpx call in the voice service to an in-memory VibeVoice."""
    calls = calls if calls is not None else []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, request.content))
        path = request.url.path
        if path == "/api/voices":
            return httpx.Response(200, json={"voices": [{"name": "en-Carter_man", "preset": True}, {"name": "david", "preset": False}]})
        if path == "/api/generate":
            return httpx.Response(200, json={"id": "job1", "status": "queued"})
        if path == "/api/jobs/job1":
            return httpx.Response(200, json={"id": "job1", "status": final_status, "error": "boom" if final_status == "failed" else None})
        if path == "/api/jobs/job1/audio":
            return httpx.Response(200, content=b"RIFF\x00\x00\x00\x00WAVEclone")
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(vsvc.httpx, "Client", lambda **kw: _REAL_CLIENT(transport=transport, **kw))
    monkeypatch.setattr(vsvc.httpx, "get", lambda url, **kw: _REAL_CLIENT(transport=transport).get(url, **kw))
    monkeypatch.setattr(vsvc.httpx, "post", lambda url, **kw: _REAL_CLIENT(transport=transport).post(url, **kw))
    return calls


def test_vibevoice_voices_are_listed_with_prefix(monkeypatch):
    _fake_vibevoice(monkeypatch)
    ids = [v["id"] for v in vsvc._vibevoice_voices()]
    assert ids == ["vibevoice:en-Carter_man", "vibevoice:david"]


def test_vibevoice_voices_empty_when_app_not_running(monkeypatch):
    def down(*_a, **_kw):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(vsvc.httpx, "get", down)
    assert vsvc._vibevoice_voices() == []


def test_clone_speech_writes_wav_and_hands_gpu_back(monkeypatch, tmp_path):
    calls = _fake_vibevoice(monkeypatch)
    out = tmp_path / "clone.wav"
    vsvc.generate_speech("Hello   there.\nSecond line.", out, voice_id="vibevoice:david")

    assert out.read_bytes().endswith(b"clone")
    paths = [p for _m, p, _c in calls]
    # ComfyUI freed first, VibeVoice unloaded last, so the GPU is shared in turn.
    assert paths[0] == "/free" and paths[-1] == "/api/models/unload"
    generate_body = next(c for _m, p, c in calls if p == "/api/generate")
    assert b'"Speaker 1: Hello there. Second line."' in generate_body
    assert b'"voices":["david"]' in generate_body.replace(b" ", b"")


def test_clone_speech_failure_raises_and_writes_nothing(monkeypatch, tmp_path):
    _fake_vibevoice(monkeypatch, final_status="failed")
    out = tmp_path / "clone.wav"
    with pytest.raises(RuntimeError, match="VibeVoice failed: boom"):
        vsvc.generate_speech("Hi", out, voice_id="vibevoice:david")
    assert not out.exists()
