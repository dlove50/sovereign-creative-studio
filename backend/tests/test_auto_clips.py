"""Auto clips: sentence snapping, fallback, real FFmpeg cutting, and the API."""
import os
import subprocess
import sys
import tempfile

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import auto_clips as ac  # noqa: E402

FFMPEG = ac._ffmpeg_bin() if ac.probe else None

# A 60 s "talk": a sentence about every 6 s, the middle one is the busiest.
SEGMENTS = [{"start": i * 6.0, "end": i * 6.0 + 5.5, "text": "word " * (30 if 3 <= i <= 6 else 8)} for i in range(10)]


def test_normalize_snaps_to_sentence_edges_and_drops_overlaps_and_short_clips():
    raw = [
        {"start": 6.3, "end": 17.1, "title": "First"},
        {"start": 12.0, "end": 24.0, "title": "Overlaps the first"},
        {"start": 40.0, "end": 42.0, "title": "Too short"},
        {"start": 30.2, "end": 41.0, "title": "Second"},
    ]
    clips = ac.normalize_clips(raw, SEGMENTS, count=3, seconds=15)
    assert [c["title"] for c in clips] == ["First", "Second"]
    assert clips[0]["start"] == 6.0 and clips[0]["end"] == 17.5  # snapped to a segment start/end


def test_normalize_trims_overlong_clips_to_the_last_sentence_that_fits():
    clips = ac.normalize_clips([{"start": 0, "end": 59, "title": "Whole talk"}], SEGMENTS, count=1, seconds=20)
    assert len(clips) == 1 and clips[0]["end"] - clips[0]["start"] <= 30


def test_normalize_ignores_garbage_from_the_model():
    assert ac.normalize_clips([{"start": "x", "end": 5}, {"end": 3}], SEGMENTS, 3, 30) == []


def test_fallback_picks_the_densest_speech_without_overlap():
    clips = ac.fallback_clips(SEGMENTS, count=2, seconds=24)
    assert len(clips) == 2 and clips[0]["end"] <= clips[1]["start"]
    assert any(18.0 <= c["start"] <= 36.0 for c in clips)  # the busy middle is included


@pytest.fixture()
def talk_video(tmp_path):
    out = tmp_path / "talk.mp4"
    subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=25:duration=60",
                    "-f", "lavfi", "-i", "sine=duration=60", "-pix_fmt", "yuv420p", "-shortest", str(out)], check=True)
    return out


@pytest.mark.skipif(not FFMPEG, reason="FFmpeg not installed")
def test_make_clips_cuts_the_chosen_moments_with_picture_and_sound(talk_video, tmp_path, monkeypatch):
    monkeypatch.setattr(ac, "transcribe_segments", lambda path: SEGMENTS)
    monkeypatch.setattr(ac, "pick_clips_with_qwen", lambda *a, **k: [{"start": 18.0, "end": 35.5, "title": "The busy part"}])
    result = ac.make_clips(talk_video, tmp_path / "out", "t", count=1, seconds=18)
    assert result["method"] == "ai" and len(result["clips"]) == 1
    clip = result["clips"][0]
    assert clip["title"] == "The busy part" and 16 < clip["seconds"] < 19
    duration, has_video = ac.probe(tmp_path / "out" / clip["file"])
    assert has_video and abs(duration - clip["seconds"]) < 0.3


@pytest.mark.skipif(not FFMPEG, reason="FFmpeg not installed")
def test_make_clips_falls_back_when_the_model_is_unreachable(talk_video, tmp_path, monkeypatch):
    def down(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(ac, "transcribe_segments", lambda path: SEGMENTS)
    monkeypatch.setattr(ac, "pick_clips_with_qwen", down)
    result = ac.make_clips(talk_video, tmp_path / "out", "t", count=2, seconds=18)
    assert result["method"] == "fallback" and len(result["clips"]) == 2


@pytest.mark.skipif(not FFMPEG, reason="FFmpeg not installed")
def test_api_validates_and_returns_playable_clip_urls(talk_video, monkeypatch):
    monkeypatch.setattr(ac, "transcribe_segments", lambda path: SEGMENTS)
    monkeypatch.setattr(ac, "pick_clips_with_qwen", lambda *a, **k: [{"start": 18.0, "end": 35.5, "title": "Busy"}])
    with TestClient(app) as c:
        assert c.post("/api/auth/signup", json={"username": "clips_user", "password": "clipspass1", "name": "C"}).status_code == 201
        assert c.post("/api/auto-clips", files={"file": ("x.txt", b"hi", "text/plain")}).status_code == 400
        assert c.post("/api/auto-clips", data={"clip_count": "99"}, files={"file": ("t.mp4", b"x", "video/mp4")}).status_code == 422
        ok = c.post("/api/auto-clips", data={"clip_count": "1", "clip_seconds": "18"},
                    files={"file": ("talk.mp4", talk_video.read_bytes(), "video/mp4")})
        assert ok.status_code == 200, ok.text
        clip = ok.json()["clips"][0]
        assert clip["title"] == "Busy" and clip["url"].startswith("/storage/auto_clips/")
        assert c.get(clip["url"]).status_code == 200
