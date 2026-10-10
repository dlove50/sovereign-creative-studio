"""Music Lab part 2: lyric writing, one-call create, speaker playback and display data.

The lyric model, the audio engine and the speakers are all faked.
"""
import json
import os
import subprocess
import tempfile
import time

_TMP = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(_TMP, 'test.db')}")
os.environ.setdefault("STORAGE_DIR", os.path.join(_TMP, "storage"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config  # noqa: E402
from app.main import app  # noqa: E402
from app.services import music, music_compose, music_playback  # noqa: E402


class FakePlayer:
    """Stands in for the ffplay process: runs until terminated or `finish()` is called."""

    def __init__(self):
        self.done = False

    def poll(self):
        return 0 if self.done else None

    def terminate(self):
        self.done = True

    def kill(self):
        self.done = True

    def wait(self, timeout=None):
        return 0

    def finish(self):
        self.done = True


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MUSIC_DIR", tmp_path / "music")
    music._jobs.clear()
    players = []

    def spawn(path, start=0.0):
        p = FakePlayer()
        p.start = start
        players.append(p)
        return p
    monkeypatch.setattr(music_playback, "_spawn_player", spawn)
    monkeypatch.setattr(music_playback, "audio_duration", lambda path: 42.0)
    music_playback.stop_playback()
    yield players
    music_playback.stop_playback()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _song(**over):
    params = dict(title="Island Morning", style="reggae, warm vocal", lyrics="[verse]\nla", instrumental=False,
                  duration=30.0, seed=1, quality="V0")
    params.update(over)
    return music._save_song(b"ID3audio", params, 1.0)


def _fake_llm(payload):
    return lambda messages, schema, timeout=240.0: json.dumps(payload)


GOOD = {"title": "Sunrise Over the Bay", "style": "warm vocal, offbeat guitar, relaxed tempo",
        "lyrics": "[verse]\nSun comes up over the bay\nFishing boats are on their way\n[chorus]\nOne love rising with the day\nLet the worries drift away"}


# --- songwriting --------------------------------------------------------------

def test_compose_adds_genre_and_keeps_section_tags(monkeypatch):
    monkeypatch.setattr(music_compose, "_ollama_chat", _fake_llm(GOOD))
    song = music_compose.compose_song("a reggae song about a sunrise at the bay")
    assert song["title"] == "Sunrise Over the Bay"
    assert song["style"].startswith("reggae")
    assert "[chorus]" in song["lyrics"]


def test_compose_detects_genre_from_the_idea():
    assert music_compose.detect_genre("make me a Reggae tune about my dog") == "reggae"
    assert music_compose.detect_genre("something about the rain") is None


def test_compose_adds_a_section_tag_if_missing(monkeypatch):
    bare = dict(GOOD, lyrics="line one here\nline two here\nline three here\nline four here")
    monkeypatch.setattr(music_compose, "_ollama_chat", _fake_llm(bare))
    assert music_compose.compose_song("a folk song")["lyrics"].startswith("[verse]")


def test_compose_rejects_unusable_output(monkeypatch):
    monkeypatch.setattr(music_compose, "_ollama_chat", lambda *a, **k: "not json at all")
    with pytest.raises(music.MusicError):
        music_compose.compose_song("a song")
    monkeypatch.setattr(music_compose, "_ollama_chat", _fake_llm(dict(GOOD, lyrics="one line")))
    with pytest.raises(music.MusicError):
        music_compose.compose_song("a song")
    with pytest.raises(music.MusicError):
        music_compose.compose_song("   ")


def test_normalize_idea_validation():
    ok = dict(genre=None, instrumental=False, duration=60, seed=None, quality="V0", auto_play=True)
    assert music.normalize_idea(idea="a reggae song", **ok)["compose"]["idea"] == "a reggae song"
    with pytest.raises(music.MusicError):
        music.normalize_idea(idea="", **ok)
    with pytest.raises(music.MusicError):
        music.normalize_idea(idea="x" * 601, **ok)
    with pytest.raises(music.MusicError):
        music.normalize_idea(idea="ok", **{**ok, "duration": 5})


# --- full pipeline: idea -> lyrics -> song -> playing --------------------------------

class _Resp:
    def __init__(self, data):
        self._d = data

    def read(self):
        return self._d

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _wait(job_id, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        job = music.get_job(job_id)
        if job["status"] in ("done", "error"):
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def _fake_engine(monkeypatch):
    monkeypatch.setattr(music, "engine_status", lambda: {"online": True, "ready": True, "detail": "ready"})
    monkeypatch.setattr(music, "_comfy_post", lambda path, payload, timeout=30.0: {"prompt_id": "p1"})
    history = {"p1": {"status": {"status_str": "success"}, "outputs": {"8": {"audio": [
        {"filename": "x.mp3", "subfolder": "audio", "type": "output"}]}}}}
    monkeypatch.setattr(music, "_comfy_get", lambda path, timeout=5.0: history)
    monkeypatch.setattr(music.urllib.request, "urlopen", lambda url, timeout=60: _Resp(b"ID3-from-engine"))


def test_idea_job_writes_lyrics_composes_and_plays(monkeypatch, isolated):
    _fake_engine(monkeypatch)
    monkeypatch.setattr(music_compose, "_ollama_chat", _fake_llm(GOOD))
    params = music.normalize_idea(idea="a reggae song about a sunrise", genre=None, instrumental=False,
                                  duration=30, seed=5, quality="V0", auto_play=True)
    job = music.create_job(params)
    done = _wait(job["id"])
    assert done["status"] == "done", done
    song = music.get_song(done["song_id"])
    assert song["title"] == "Sunrise Over the Bay" and "reggae" in song["style"]
    assert "[chorus]" in song["lyrics"]
    state = music_playback.now_playing()
    assert state["playing"] is True and state["song"]["id"] == song["id"]
    assert "playing" in done["message"]
    assert len(isolated) == 1


def test_idea_job_without_autoplay_does_not_play(monkeypatch, isolated):
    _fake_engine(monkeypatch)
    monkeypatch.setattr(music_compose, "_ollama_chat", _fake_llm(GOOD))
    params = music.normalize_idea(idea="a folk song", genre="folk", instrumental=False, duration=30, seed=5,
                                  quality="V0", auto_play=False)
    done = _wait(music.create_job(params)["id"])
    assert done["status"] == "done"
    assert music_playback.now_playing()["playing"] is False and isolated == []


def test_idea_job_reports_lyric_writer_failure(monkeypatch):
    def down(*a, **k):
        raise music.MusicError("The lyric writer (x) is not available: refused")
    monkeypatch.setattr(music_compose, "_ollama_chat", down)
    params = music.normalize_idea(idea="a song", genre=None, instrumental=False, duration=30, seed=1,
                                  quality="V0", auto_play=True)
    done = _wait(music.create_job(params)["id"])
    assert done["status"] == "error" and "lyric writer" in done["message"]


# --- playback --------------------------------------------------------------------------

def test_play_tracks_state_and_stop(isolated):
    song = _song()
    state = music_playback.play_song(song["id"])
    assert state["playing"] and state["duration"] == 42.0 and state["song"]["id"] == song["id"]
    assert 0.0 <= state["position"] <= 42.0
    assert music_playback.stop_playback() == {"stopped": True}
    assert music_playback.now_playing()["playing"] is False
    assert music_playback.stop_playback() == {"stopped": False}


def test_starting_a_second_song_stops_the_first(isolated):
    a, b = _song(title="A"), _song(title="B")
    music_playback.play_song(a["id"])
    music_playback.play_song(b["id"])
    assert isolated[0].done is True and isolated[1].done is False
    assert music_playback.now_playing()["song"]["id"] == b["id"]


def test_now_playing_clears_when_the_song_ends(isolated):
    song = _song()
    music_playback.play_song(song["id"])
    isolated[0].finish()
    assert music_playback.now_playing()["playing"] is False


def test_play_unknown_song_errors():
    with pytest.raises(music.MusicError):
        music_playback.play_song("0123456789ab")


# --- display data --------------------------------------------------------------------------

def test_visual_data_from_real_audio(tmp_path):
    ffmpeg = music_playback.find_ffmpeg_tool("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg not installed")
    wav = tmp_path / "tone.mp3"
    subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(wav)], check=True)
    song = music._save_song(wav.read_bytes(), dict(title="Tone", style="x", lyrics="", instrumental=True,
                                                   duration=2.0, seed=1, quality="V0"), 0.1)
    data = music_playback.visual_data(song["id"])
    import base64
    raw = base64.b64decode(data["data"])
    assert data["bands"] == music_playback.VIZ_BANDS and data["fps"] == music_playback.VIZ_FPS
    assert len(raw) == data["frames"] * data["bands"]
    assert 38 <= data["frames"] <= 42 and 1.9 < data["duration"] < 2.2
    assert max(raw) > 100, "a loud tone must produce strong band energy"
    assert music_playback._viz_path(song["id"]).exists()
    assert music_playback.visual_data(song["id"]) == data


# --- API ---------------------------------------------------------------------------------------

def test_api_create_validates_and_queues(client, monkeypatch):
    assert client.post("/api/music/create", json={"idea": ""}).status_code == 422
    assert client.post("/api/music/create", json={"idea": "ok", "duration": 3}).status_code == 422
    seen = {}

    def fake_create(params):
        seen.update(params)
        return {"id": "aaaaaaaaaaaa", "status": "queued"}
    monkeypatch.setattr(music, "create_job", fake_create)
    resp = client.post("/api/music/create", json={"idea": "a reggae song about my dog"})
    assert resp.status_code == 202
    assert seen["compose"]["idea"] == "a reggae song about my dog" and seen["auto_play"] is True


def test_api_play_stop_now_playing_and_viz(client):
    song = _song(title="Via API")
    sid = song["id"]
    assert client.get("/api/music/now-playing").json()["playing"] is False
    playing = client.post(f"/api/music/play/{sid}").json()
    assert playing["playing"] is True and playing["song"]["audio_url"].endswith(f"/{sid}/audio")
    assert client.get("/api/music/now-playing").json()["song"]["id"] == sid
    assert client.post("/api/music/stop").json() == {"stopped": True}
    assert client.post("/api/music/play/0123456789ab").status_code == 404
    assert client.get("/api/music/songs/0123456789ab/viz").status_code == 404


def test_pause_resume_and_seek_keep_position(client, isolated):
    song = _song()
    music_playback.play_song(song["id"])
    paused = client.post("/api/music/pause").json()
    assert paused["paused"] is True and paused["playing"] is False
    assert paused["song"]["id"] == song["id"]
    assert isolated[0].done, "pausing stops the player process"
    seeked = client.post("/api/music/seek", json={"position": 20}).json()
    assert seeked["paused"] is True and seeked["position"] == 20
    resumed = client.post("/api/music/resume").json()
    assert resumed["playing"] is True and resumed["paused"] is False
    assert isolated[-1].start == 20, "resume continues from the seek position"
    jumped = client.post("/api/music/seek", json={"position": 5}).json()
    assert jumped["playing"] is True and isolated[-1].start == 5
    client.post("/api/music/stop")
    assert client.post("/api/music/seek", json={"position": 1}).status_code == 409
