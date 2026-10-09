"""Screen recordings: WebM upload from the browser is converted to MP4 and saved to the library."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config  # noqa: E402
from app.main import app  # noqa: E402
from app.services.audio_merge import _ffmpeg  # noqa: E402

FFMPEG = _ffmpeg()
needs_ffmpeg = pytest.mark.skipif(not FFMPEG, reason="FFmpeg not installed")


def _webm(path: Path, audio: bool, odd_size: bool = True) -> bytes:
    size = "101x75" if odd_size else "128x96"  # odd sizes cannot be H.264 encoded without rounding
    command = [FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=s={size}:d=1:r=10"]
    if audio:
        command += ["-f", "lavfi", "-i", "sine=frequency=440:d=1"]
    command += ["-c:v", "libvpx", "-b:v", "200k"] + (["-c:a", "libopus"] if audio else []) + [str(path)]
    subprocess.run(command, check=True)
    return path.read_bytes()


def _client(name):
    c = TestClient(app)
    assert c.post("/api/auth/signup", json={"username": name, "password": "recordpass1", "name": name}).status_code == 201
    return c


@needs_ffmpeg
def test_recording_is_converted_to_mp4_and_listed_as_a_library_clip(tmp_path):
    with TestClient(app):
        c = _client("rec_user")
        made = c.post("/api/recordings", data={"title": "  Intro   walkthrough "},
                      files={"file": ("screen.webm", _webm(tmp_path / "a.webm", audio=True), "video/webm")})
        assert made.status_code == 201, made.text
        body = made.json()
        assert body["title"] == "Intro walkthrough" and body["has_audio"] is True
        assert body["result_url"].endswith(".mp4") and 0.5 <= body["duration_seconds"] <= 2.0
        stored = config.STORAGE_DIR / "videos" / Path(body["result_url"]).name
        assert stored.is_file() and (config.STORAGE_DIR / "videos" / Path(body["poster_url"]).name).is_file()
        facts = subprocess.run([FFMPEG, "-i", str(stored)], capture_output=True, text=True).stderr
        assert "Video: h264" in facts and "Audio: aac" in facts
        assert "yuv420p" in facts and " 100x74" in facts  # odd 101x75 was rounded down to even
        assert c.get(body["result_url"]).status_code == 200
        clips = c.get("/api/interactive/clips")
        assert clips.status_code == 200 and any(x.get("url") == body["result_url"] or x.get("result_url") == body["result_url"] for x in clips.json())


@needs_ffmpeg
def test_silent_recordings_are_accepted_and_other_files_rejected(tmp_path):
    with TestClient(app):
        c = _client("rec_other")
        silent = c.post("/api/recordings", files={"file": ("quiet.webm", _webm(tmp_path / "b.webm", audio=False, odd_size=False), "video/webm")})
        assert silent.status_code == 201 and silent.json()["has_audio"] is False
        assert silent.json()["title"].startswith("Screen recording ")
        assert c.post("/api/recordings", files={"file": ("x.exe", b"MZ")}).status_code == 400
        assert c.post("/api/recordings", files={"file": ("empty.webm", b"")}).status_code == 422
        assert c.post("/api/recordings", files={"file": ("junk.webm", b"this is not a video at all")}).status_code == 422
