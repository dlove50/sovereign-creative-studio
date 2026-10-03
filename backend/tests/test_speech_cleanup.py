"""Speech cleanup: range planning, pause cutting with real FFmpeg, filler cutting, API."""
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
from app.services import speech_cleanup as sc  # noqa: E402

FFMPEG = sc._ffmpeg()
needs_ffmpeg = pytest.mark.skipif(not FFMPEG, reason="FFmpeg not installed")


def test_plan_keep_merges_overlaps_and_inverts():
    keep = sc.plan_keep(10.0, [(2.0, 3.0), (2.5, 4.0), (8.0, 10.0)])
    assert keep == [(0.0, 2.0), (4.0, 8.0)]


def test_plan_keep_drops_slivers_and_clamps():
    assert sc.plan_keep(5.0, [(-1.0, 0.99), (4.98, 9.0)]) == [(0.99, 4.98)]
    assert sc.plan_keep(5.0, [(0.0, 5.0)]) == []
    assert sc.plan_keep(5.0, []) == [(0.0, 5.0)]


@pytest.fixture()
def tone_gap_tone(tmp_path):
    """1 s tone, 2 s silence, 1 s tone = 4 s."""
    out = tmp_path / "gap.wav"
    subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=2", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                    "-filter_complex", "[0][1][2]concat=n=3:v=0:a=1", "-ar", "44100", str(out)], check=True)
    return out


@needs_ffmpeg
def test_long_pause_is_trimmed_but_a_natural_beat_is_kept(tone_gap_tone, tmp_path):
    out = tmp_path / "clean.m4a"
    result = sc.clean(tone_gap_tone, out, remove_pauses=True, remove_fillers=False)
    assert result["pauses_removed"] == 1 and result["fillers_removed"] == 0
    # 2 s of silence keeps 0.15 s at each side -> about 1.7 s removed
    assert 1.5 < result["seconds_removed"] < 1.9 and 2.1 < result["new_seconds"] < 2.5
    duration, has_video = sc.probe(out)
    assert abs(duration - result["new_seconds"]) < 0.25 and not has_video


@needs_ffmpeg
def test_video_keeps_picture_and_sound_in_sync_after_cuts(tmp_path):
    src = tmp_path / "talk.mp4"
    subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=25:duration=4",
                    "-f", "lavfi", "-i", "sine=duration=1", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=2",
                    "-f", "lavfi", "-i", "sine=duration=1", "-filter_complex", "[1][2][3]concat=n=3:v=0:a=1[a]",
                    "-map", "0:v", "-map", "[a]", "-pix_fmt", "yuv420p", "-shortest", str(src)], check=True)
    out = tmp_path / "talk_clean.mp4"
    result = sc.clean(src, out, remove_pauses=True, remove_fillers=False)
    assert result["has_video"] and result["pauses_removed"] == 1
    duration, has_video = sc.probe(out)
    assert has_video and 2.0 < duration < 2.6


@needs_ffmpeg
def test_filler_words_are_cut_using_whisper_timestamps(tone_gap_tone, tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "detect_fillers", lambda path: [(0.4, 0.8)])
    out = tmp_path / "clean.m4a"
    result = sc.clean(tone_gap_tone, out, remove_pauses=False, remove_fillers=True)
    assert result["fillers_removed"] == 1 and result["pauses_removed"] == 0
    assert 0.35 < result["seconds_removed"] < 0.45


@needs_ffmpeg
def test_nothing_to_remove_returns_the_file_unchanged(tmp_path):
    src = tmp_path / "tone.wav"
    subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "sine=duration=2", str(src)], check=True)
    out = tmp_path / "same.wav"
    result = sc.clean(src, out, remove_pauses=True, remove_fillers=False)
    assert result["seconds_removed"] == 0 and out.read_bytes() == src.read_bytes()


@needs_ffmpeg
def test_api_cleans_an_upload_and_validates_input(tone_gap_tone):
    with TestClient(app) as c:
        assert c.post("/api/auth/signup", json={"username": "cleanup_user", "password": "cleanpass1", "name": "C"}).status_code == 201
        bad = c.post("/api/speech-cleanup", files={"file": ("notes.txt", b"hello", "text/plain")})
        assert bad.status_code == 400
        none = c.post("/api/speech-cleanup", data={"remove_pauses": "false", "remove_fillers": "false"},
                      files={"file": ("gap.wav", tone_gap_tone.read_bytes(), "audio/wav")})
        assert none.status_code == 400 and "at least one" in none.json()["detail"]
        ok = c.post("/api/speech-cleanup", data={"remove_pauses": "true", "remove_fillers": "false"},
                    files={"file": ("gap.wav", tone_gap_tone.read_bytes(), "audio/wav")})
        assert ok.status_code == 200, ok.text
        body = ok.json()
        assert body["pauses_removed"] == 1 and body["output_url"].endswith("_clean.m4a")
        assert c.get(body["output_url"]).status_code == 200
