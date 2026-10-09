"""Captions: caption splitting and a real FFmpeg burn-in (the speech step is faked)."""
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

from app import config  # noqa: E402
from app.main import app  # noqa: E402
from app.services import captions  # noqa: E402
from app.services.audio_merge import _ffmpeg  # noqa: E402


def test_long_segments_become_two_line_captions_with_proportional_timing():
    seg = {"start": 0.0, "end": 10.0, "text": "word " * 40}
    parts = captions.split_for_captions([seg])
    assert len(parts) >= 2
    assert parts[0]["start"] == 0.0 and abs(parts[-1]["end"] - 10.0) < 1e-6
    assert all(len(p["text"].splitlines()) <= 2 and all(len(l) <= captions.MAX_LINE_CHARS for l in p["text"].splitlines()) for p in parts)
    assert all(a["end"] <= b["start"] + 1e-6 for a, b in zip(parts, parts[1:]))


def test_blank_segments_are_dropped():
    assert captions.split_for_captions([{"start": 0, "end": 1, "text": "   "}]) == []


@pytest.mark.skipif(not _ffmpeg(), reason="FFmpeg not installed")
def test_endpoint_burns_captions_into_a_stored_video(monkeypatch):
    storage = config.STORAGE_DIR
    storage.mkdir(parents=True, exist_ok=True)
    clip = storage / "talk.mp4"
    subprocess.run([_ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x480:rate=25:duration=4",
                    "-f", "lavfi", "-i", "sine=frequency=300:duration=4", "-pix_fmt", "yuv420p", "-shortest", str(clip)], check=True)
    monkeypatch.setattr(captions, "transcribe_segments", lambda p: [{"start": 0.2, "end": 3.5, "text": "Hello and welcome to the show"}])
    with TestClient(app) as c:
        assert c.post("/api/auth/signup", json={"username": "cap_user", "password": "captionpw12", "name": "C"}).status_code == 201
        r = c.post("/api/captions", json={"video_url": "/storage/talk.mp4"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["captions"] == 1
        out = c.get(body["video_url"])
        assert out.status_code == 200 and len(out.content) > 1000
        assert "Hello and welcome" in c.get(body["srt_url"]).text

        assert c.post("/api/captions", json={"video_url": "/storage/nope.mp4"}).status_code == 400
        assert c.post("/api/captions", json={"video_url": "/storage/talk.wav"}).status_code == 400
        monkeypatch.setattr(captions, "transcribe_segments", lambda p: [])
        assert c.post("/api/captions", json={"video_url": "/storage/talk.mp4"}).status_code == 422
