"""Clone a real person (frame + voice sample) and the avatar PATCH endpoint."""
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
from app.services import avatar_clone  # noqa: E402
from app.services.audio_merge import _ffmpeg  # noqa: E402

pytestmark = pytest.mark.skipif(not _ffmpeg(), reason="FFmpeg not installed")


def _talking_clip(path, seconds=10):
    subprocess.run(
        [_ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=size=320x480:rate=25:duration={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency=220:duration={seconds}", "-pix_fmt", "yuv420p", "-shortest", str(path)],
        check=True,
    )


def test_voice_names_are_made_safe_for_the_voice_app():
    assert avatar_clone.voice_name_for("David W. (calm)") == "David-W-calm"
    assert avatar_clone.voice_name_for("???") == "voice"


def test_clone_makes_a_frame_and_a_voice_sample(tmp_path, monkeypatch):
    clip = tmp_path / "me.mp4"
    _talking_clip(clip)
    monkeypatch.setattr(avatar_clone, "register_voice", lambda name, sample: name)
    made = avatar_clone.clone(clip, tmp_path / "work", "Test Person")
    assert made["frame"].is_file() and made["frame"].stat().st_size > 1000
    assert made["sample"].is_file() and made["voice_name"] == "Test-Person"
    assert not list((tmp_path / "work").glob("*_cand*.jpg"))  # candidate frames are cleaned up


def test_clone_rejects_clips_that_are_too_short(tmp_path):
    clip = tmp_path / "short.mp4"
    _talking_clip(clip, seconds=3)
    with pytest.raises(RuntimeError, match="at least"):
        avatar_clone.clone(clip, tmp_path / "work", "x")


def test_clone_endpoint_creates_an_avatar_with_its_voice_and_patch_changes_it(tmp_path, monkeypatch):
    clip = tmp_path / "me.mp4"
    _talking_clip(clip)
    monkeypatch.setattr(avatar_clone, "register_voice", lambda name, sample: name)
    with TestClient(app) as c:
        assert c.post("/api/auth/signup", json={"username": "clone_user", "password": "clonepass12", "name": "C"}).status_code == 201
        r = c.post("/api/avatars/clone", data={"name": "Me"}, files={"file": ("me.mp4", clip.read_bytes())})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["voice_id"] == "vibevoice:Me" and body["avatar"]["default_voice_id"] == "vibevoice:Me"
        assert body["voice_note"] is None and body["avatar"]["avatar_type"] == "photo_avatar"
        avatar_id = body["avatar"]["id"]
        patched = c.patch(f"/api/avatars/{avatar_id}", json={"name": "Renamed", "default_voice_id": "piper-voice"})
        assert patched.status_code == 200 and patched.json()["name"] == "Renamed" and patched.json()["default_voice_id"] == "piper-voice"
        cleared = c.patch(f"/api/avatars/{avatar_id}", json={"default_voice_id": ""})
        assert cleared.json()["default_voice_id"] is None
        assert c.patch("/api/avatars/nope", json={"name": "x"}).status_code == 404


def test_clone_endpoint_reports_when_the_voice_app_is_off(tmp_path, monkeypatch):
    clip = tmp_path / "me.mp4"
    _talking_clip(clip)
    monkeypatch.setattr(avatar_clone, "register_voice", lambda name, sample: None)
    with TestClient(app) as c:
        assert c.post("/api/auth/signup", json={"username": "clone_user2", "password": "clonepass12", "name": "C"}).status_code == 201
        body = c.post("/api/avatars/clone", data={"name": "Quiet"}, files={"file": ("me.mp4", clip.read_bytes())}).json()
        assert body["voice_id"] is None and "not running" in body["voice_note"]


def test_favorite_flag_and_look_from_video(tmp_path):
    clip = tmp_path / "look.mp4"
    _talking_clip(clip, seconds=4)
    with TestClient(app) as c:
        assert c.post("/api/auth/signup", json={"username": "look_user", "password": "lookpass123", "name": "L"}).status_code == 201
        base = c.post("/api/avatars/photo", data={"name": "Base"}, files={"file": ("a.png", _png_bytes())})
        assert base.status_code == 201, base.text
        base_id = base.json()["id"]
        assert base.json()["is_favorite"] is False
        assert c.patch(f"/api/avatars/{base_id}", json={"is_favorite": True}).json()["is_favorite"] is True
        look = c.post("/api/avatars/looks/from-video", data={"group_id": base_id, "look_label": "Office"}, files={"file": ("look.mp4", clip.read_bytes())})
        assert look.status_code == 201, look.text
        assert look.json()["group_id"] == base_id and look.json()["look_label"] == "Office"
        assert look.json()["thumbnail_path"].endswith(".jpg")
        bad = c.post("/api/avatars/looks/from-video", data={"group_id": "nope"}, files={"file": ("look.mp4", clip.read_bytes())})
        assert bad.status_code == 404


def _png_bytes():
    import base64

    return base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
