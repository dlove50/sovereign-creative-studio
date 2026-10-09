"""Music Lab: request validation, workflow wiring, song store, job flow and API.

The ComfyUI engine is faked, so these tests need no GPU and no running engine.
"""
import os
import tempfile
import time

_TMP = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(_TMP, 'test.db')}")
os.environ.setdefault("STORAGE_DIR", os.path.join(_TMP, "storage"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config  # noqa: E402
from app.main import app  # noqa: E402
from app.services import music  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_music_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MUSIC_DIR", tmp_path / "music")
    music._jobs.clear()
    monkeypatch.setattr(music, "_release_main_engine", lambda: None)  # never touch a real ComfyUI from these tests
    from app.services import music_compose
    monkeypatch.setattr(music_compose, "unload_models", lambda: None)  # nor a real Ollama
    yield


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _params(**over):
    base = dict(title="Harbor Lights", style="indie folk, acoustic guitar", lyrics="[verse]\nla la",
                instrumental=False, duration=30.0, seed=7, quality="V0")
    base.update(over)
    return base


def _seed_song(**over):
    return music._save_song(b"ID3fakeaudio", _params(**over), 1.5)


# --- validation -----------------------------------------------------------------

def test_normalize_requires_style_and_lyrics_or_instrumental():
    with pytest.raises(music.MusicError):
        music.normalize_request(title=None, style="  ", lyrics="x", instrumental=False, duration=30, seed=1, quality="V0")
    with pytest.raises(music.MusicError):
        music.normalize_request(title=None, style="folk", lyrics="", instrumental=False, duration=30, seed=1, quality="V0")


def test_normalize_limits_and_quality():
    ok = dict(title=None, style="folk", lyrics="la", instrumental=False, seed=1, quality="V0")
    with pytest.raises(music.MusicError):
        music.normalize_request(**ok, duration=music.MIN_SECONDS - 1)
    with pytest.raises(music.MusicError):
        music.normalize_request(**ok, duration=music.MAX_SECONDS + 1)
    with pytest.raises(music.MusicError):
        music.normalize_request(**{**ok, "quality": "lossless"}, duration=30)
    with pytest.raises(music.MusicError):
        music.normalize_request(**{**ok, "lyrics": "x" * (music.MAX_LYRICS_CHARS + 1)}, duration=30)


def test_normalize_instrumental_clears_lyrics_and_tags_style():
    p = music.normalize_request(title=None, style="Synthwave, Dark", lyrics="ignored words", instrumental=True,
                                duration=45, seed=None, quality="320k")
    assert p["lyrics"] == ""
    assert "instrumental" in p["style"].lower()
    assert isinstance(p["seed"], int)
    assert p["title"] == "Synthwave"


def test_normalize_cleans_line_endings():
    p = music.normalize_request(title="T", style="folk", lyrics="a\r\nb\rc", instrumental=False, duration=30, seed=1, quality="V0")
    assert p["lyrics"] == "a\nb\nc"


# --- workflow ---------------------------------------------------------------------

def test_workflow_links_are_consistent():
    wf = music.build_workflow(style="folk", lyrics="la", duration=42.0, seed=9, quality="128k", filename_prefix="audio/x")
    assert {n["class_type"] for n in wf.values()} >= {
        "CheckpointLoaderSimple", "YuE2GenerateABC", "YuE2GenerateMusic", "EmptyYuE2LatentAudio",
        "KSampler", "VAEDecodeAudio", "SaveAudioMP3"}
    for node in wf.values():
        for value in node["inputs"].values():
            if isinstance(value, list):
                assert value[0] in wf, f"dangling link {value}"
    assert wf["1"]["inputs"]["ckpt_name"] == config.MUSIC_CHECKPOINT
    assert wf["3"]["inputs"]["max_duration"] == 42.0
    assert wf["8"]["inputs"]["quality"] == "128k"
    assert wf["2"]["inputs"]["seed"] == wf["3"]["inputs"]["seed"] == wf["6"]["inputs"]["seed"] == 9


# --- song store -------------------------------------------------------------------

def test_song_store_round_trip():
    song = _seed_song()
    assert music.get_song(song["id"])["title"] == "Harbor Lights"
    assert [s["id"] for s in music.list_songs()] == [song["id"]]
    assert music.update_song(song["id"], favorite=True, title="Renamed")["favorite"] is True
    assert music.get_song(song["id"])["title"] == "Renamed"
    assert music.delete_song(song["id"]) is True
    assert music.get_song(song["id"]) is None
    assert music.delete_song(song["id"]) is False


def test_song_store_rejects_bad_ids():
    for bad in ("../../etc/passwd", "short", "ZZZZZZZZZZZZ", ""):
        with pytest.raises(music.MusicError):
            music.get_song(bad)


def test_list_is_newest_first():
    a = _seed_song(title="A")
    time.sleep(1.1)
    b = _seed_song(title="B")
    assert [s["id"] for s in music.list_songs()] == [b["id"], a["id"]]


# --- job flow with a fake engine ---------------------------------------------------

class _Resp:
    def __init__(self, data):
        self._d = data

    def read(self):
        return self._d

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _wait_job(job_id, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        job = music.get_job(job_id)
        if job["status"] in ("done", "error"):
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_job_completes_and_saves_song(monkeypatch):
    monkeypatch.setattr(music, "engine_status", lambda: {"online": True, "ready": True, "detail": "ready"})
    monkeypatch.setattr(music, "_comfy_post", lambda path, payload, timeout=30.0: {"prompt_id": "p1"})
    history = {"p1": {"status": {"status_str": "success"}, "outputs": {"8": {"audio": [
        {"filename": "x.mp3", "subfolder": "audio", "type": "output"}]}}}}
    monkeypatch.setattr(music, "_comfy_get", lambda path, timeout=5.0: history)
    monkeypatch.setattr(music.urllib.request, "urlopen", lambda url, timeout=60: _Resp(b"ID3-song-bytes"))
    job = music.create_job(music.normalize_request(title="Test", style="folk", lyrics="la", instrumental=False,
                                                   duration=30, seed=1, quality="V0"))
    done = _wait_job(job["id"])
    assert done["status"] == "done", done
    song = music.get_song(done["song_id"])
    assert song["provider"] == "yue2" and song["size_bytes"] == len(b"ID3-song-bytes")
    assert music.audio_path(song["id"]).read_bytes() == b"ID3-song-bytes"


def test_job_reports_engine_problems_clearly(monkeypatch):
    monkeypatch.setattr(music, "engine_status", lambda: {"online": True, "ready": False, "detail": "model file missing"})
    job = music.create_job(music.normalize_request(title=None, style="folk", lyrics="la", instrumental=False,
                                                   duration=30, seed=1, quality="V0"))
    done = _wait_job(job["id"])
    assert done["status"] == "error" and "model file missing" in done["message"]
    assert music.list_songs() == []


def test_job_reports_engine_failure(monkeypatch):
    monkeypatch.setattr(music, "engine_status", lambda: {"online": True, "ready": True, "detail": "ready"})
    monkeypatch.setattr(music, "_comfy_post", lambda path, payload, timeout=30.0: {"prompt_id": "p2"})
    history = {"p2": {"status": {"status_str": "error", "messages": [["execution_error", {"exception_message": "out of memory"}]]}}}
    monkeypatch.setattr(music, "_comfy_get", lambda path, timeout=5.0: history)
    job = music.create_job(music.normalize_request(title=None, style="folk", lyrics="la", instrumental=False,
                                                   duration=30, seed=1, quality="V0"))
    done = _wait_job(job["id"])
    assert done["status"] == "error" and "out of memory" in done["message"]


def test_engine_status_offline(monkeypatch):
    def boom(*a, **k):
        raise OSError("refused")
    monkeypatch.setattr(music, "_comfy_get", boom)
    st = music.engine_status()
    assert st["online"] is False and st["ready"] is False and "offline" in st["detail"]


# --- API ----------------------------------------------------------------------------

def test_api_status_lists_yue2_first_and_elevenlabs_optional(client, monkeypatch):
    monkeypatch.setattr(music, "engine_status", lambda: {"online": True, "ready": True, "detail": "ready"})
    data = client.get("/api/music/status").json()
    assert data["default_provider"] == "yue2"
    assert [p["id"] for p in data["providers"]] == ["yue2", "elevenlabs"]
    assert data["providers"][0]["available"] is True
    assert data["limits"]["max_seconds"] == music.MAX_SECONDS


def test_api_generate_validation(client):
    assert client.post("/api/music/generate", json={"style": "folk"}).status_code == 422
    assert client.post("/api/music/generate", json={"style": "", "lyrics": "x"}).status_code == 422
    assert client.post("/api/music/generate", json={"style": "folk", "lyrics": "x", "duration": 5}).status_code == 422
    assert client.post("/api/music/generate", json={"style": "folk", "lyrics": "x", "quality": "wav"}).status_code == 422


def test_api_generate_queues_a_job(client, monkeypatch):
    seen = {}

    def fake_create(params):
        seen.update(params)
        return {"id": "abc123abc123", "status": "queued"}
    monkeypatch.setattr(music, "create_job", fake_create)
    resp = client.post("/api/music/generate", json={"style": "lofi", "instrumental": True, "duration": 40})
    assert resp.status_code == 202 and resp.json()["id"] == "abc123abc123"
    assert seen["instrumental"] is True and seen["lyrics"] == ""


def test_api_library_audio_patch_delete(client):
    song = _seed_song(title="Keep Me")
    sid = song["id"]
    listing = client.get("/api/music/songs").json()
    assert listing[0]["id"] == sid and listing[0]["audio_url"].endswith(f"/{sid}/audio")
    audio = client.get(f"/api/music/songs/{sid}/audio")
    assert audio.status_code == 200 and audio.headers["content-type"] == "audio/mpeg"
    assert audio.content == b"ID3fakeaudio"
    patched = client.patch(f"/api/music/songs/{sid}", json={"favorite": True, "title": "Fav"}).json()
    assert patched["favorite"] is True and patched["title"] == "Fav"
    assert client.delete(f"/api/music/songs/{sid}").status_code == 204
    assert client.get(f"/api/music/songs/{sid}").status_code == 404


def test_api_unknown_ids_are_404(client):
    assert client.get("/api/music/songs/nonexistent1").status_code == 404
    assert client.get("/api/music/songs/..%2F..%2Fsecret").status_code in (404, 422)
    assert client.get("/api/music/jobs/doesnotexist").status_code == 404


# --- sharing the GPU with the main image/video engine ------------------------------------------

class _Reply:
    def __init__(self, body=b"{}"):
        self.body = body

    def read(self):
        return self.body

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_main_engine(monkeypatch, queue=None, free_fails=False, offline=False):
    """Replace the network with a pretend main ComfyUI; returns the list of calls it received."""
    import json
    calls = []

    def urlopen(target, timeout=None):
        url = target if isinstance(target, str) else target.full_url
        calls.append(url.rsplit(":", 1)[-1].split("/", 1)[-1] if "/" in url.rsplit(":", 1)[-1] else url)
        if offline:
            raise music.urllib.error.URLError("refused")
        if url.endswith("/queue"):
            return _Reply(json.dumps(queue if queue is not None else {"queue_running": [], "queue_pending": []}).encode())
        if free_fails:
            raise music.urllib.error.URLError("free failed")
        calls.append(("free-body", json.loads(target.data)))
        return _Reply()

    monkeypatch.setattr(music.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(music.time, "sleep", lambda s: None)
    return calls


@pytest.fixture()
def real_release(monkeypatch):
    monkeypatch.undo()  # drop the autouse no-op so the real function is exercised
    monkeypatch.setattr(config, "COMFYUI_BASE_URL", "http://127.0.0.1:8001")


def test_main_engine_is_told_to_drop_its_models_before_a_song(monkeypatch, real_release):
    calls = _fake_main_engine(monkeypatch)
    music._release_main_engine()
    assert ("free-body", {"unload_models": True, "free_memory": True}) in calls
    assert any(isinstance(c, str) and c.endswith("queue") for c in calls) and any(isinstance(c, str) and c.endswith("free") for c in calls)


def test_a_busy_or_absent_main_engine_is_handled_without_hurting_the_render(monkeypatch, real_release):
    for busy in ({"queue_running": [["job"]], "queue_pending": []}, {"queue_running": [], "queue_pending": [["job"]]}, ["unexpected"]):
        calls = _fake_main_engine(monkeypatch, queue=busy)
        with pytest.raises(music.MusicError, match="busy rendering"):
            music._release_main_engine()
        assert not any(isinstance(c, tuple) for c in calls)  # nothing was unloaded from under the render
    calls = _fake_main_engine(monkeypatch, offline=True)
    music._release_main_engine()  # not running: nothing to free, no error
    assert not any(isinstance(c, tuple) for c in calls)
    _fake_main_engine(monkeypatch, free_fails=True)
    music._release_main_engine()  # the unload is best effort


def test_the_song_job_frees_the_main_engine_before_it_queues_the_song(monkeypatch):
    order = []
    monkeypatch.setattr(music, "_release_main_engine", lambda: order.append("release"))
    monkeypatch.setattr(music, "engine_status", lambda: {"online": True, "ready": True, "detail": "ready"})
    monkeypatch.setattr(music, "_comfy_post", lambda path, payload, timeout=30.0: order.append("queue") or {"prompt_id": "p9"})
    history = {"p9": {"status": {"status_str": "success"}, "outputs": {"8": {"audio": [{"filename": "a.mp3", "subfolder": "audio", "type": "output"}]}}}}
    monkeypatch.setattr(music, "_comfy_get", lambda path, timeout=5.0: history)
    monkeypatch.setattr(music.urllib.request, "urlopen", lambda url, timeout=60: _Resp(b"ID3-song-bytes"))
    job = music.create_job(music.normalize_request(title="T", style="calm piano", lyrics=None, instrumental=True, duration=20, seed=1, quality="V0"))
    assert _wait_job(job["id"])["status"] == "done" and order == ["release", "queue"]

    def busy():
        raise music.MusicError("The image and video engine is busy rendering. Wait for it to finish, then make the song again.")

    order.clear()
    monkeypatch.setattr(music, "_release_main_engine", busy)
    job = music.create_job(music.normalize_request(title="T", style="calm piano", lyrics=None, instrumental=True, duration=20, seed=1, quality="V0"))
    finished = _wait_job(job["id"])
    assert finished["status"] == "error" and "busy rendering" in finished["error"] and order == []


# --- Timeout scaling and engine cancel (2026-10-09) -----------------------------------

def test_job_timeout_scales_with_song_length_and_is_capped():
    assert music.job_timeout(30) == music.JOB_TIMEOUT          # short songs keep the 25 minute floor
    assert music.job_timeout(60) == music.JOB_TIMEOUT
    assert music.job_timeout(210) == 210 * music.JOB_TIMEOUT_PER_SONG_SECOND
    assert music.job_timeout(210) > 57 * 60                    # the 3:30 song that really took 57 min must fit
    assert music.job_timeout(10_000) == music.JOB_TIMEOUT_MAX


def test_timeout_cancels_the_engine_job_and_says_so(monkeypatch):
    posts = []
    monkeypatch.setattr(music, "_comfy_get", lambda path, timeout=5.0: {})
    monkeypatch.setattr(music, "_comfy_post", lambda path, payload, timeout=30.0: posts.append((path, payload)) or {})
    with pytest.raises(music.MusicError) as err:
        music._await_output("p-stuck", time.time() - 120, timeout=60)
    assert ("/interrupt", {"prompt_id": "p-stuck"}) in posts
    assert ("/queue", {"delete": ["p-stuck"]}) in posts
    assert "graphics card was freed" in str(err.value)
    assert "not ready after 1 minute," in str(err.value)


def test_cancel_is_best_effort_when_the_engine_is_gone(monkeypatch):
    def boom(path, payload, timeout=30.0):
        raise OSError("engine offline")
    monkeypatch.setattr(music, "_comfy_post", boom)
    music._cancel_engine_job("p-gone")  # must not raise


def test_limits_expose_honest_time_estimates():
    client = TestClient(app)
    res = client.get("/api/music/status")
    assert res.status_code in (200, 401)
    if res.status_code == 200:
        limits = res.json()["limits"]
        assert limits["typical_minutes_per_song_minute"] == music.TYPICAL_MIN_PER_SONG_MIN
        assert limits["slow_minutes_per_song_minute"] == music.SLOW_MIN_PER_SONG_MIN
