"""Scene-by-scene movies: drafts, ownership, render checks, worker, join, recovery."""
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from app import config
from app.database import SessionLocal
from app.main import _recover_interrupted_jobs, app
from app.models import AvatarJob, Movie, User
from app.services import avatar_comfyui, avatar_jobs, movies

PNG = b"\x89PNG\r\n\x1a\nfakeimage"
FFMPEG = avatar_comfyui._ffmpeg()


@pytest.fixture(scope="module", autouse=True)
def _app_ready():
    with TestClient(app):
        yield


def _client(username: str) -> TestClient:
    c = TestClient(app)
    assert c.post("/api/auth/signup", json={"username": username, "password": "moviepass1", "name": username}).status_code == 201
    return c


def _give_credits(username: str, amount: int = 500) -> None:
    with SessionLocal() as db:
        db.query(User).filter(User.username == username).one().credits = amount
        db.commit()


def _avatar(c) -> str:
    return c.post("/api/avatars/photo", data={"name": "Me"}, files={"file": ("p.png", PNG, "image/png")}).json()["id"]


def test_new_movie_is_a_draft_with_one_empty_scene_and_edits_save():
    c = _client("movie_draft")
    m = c.post("/api/movies", json={"title": "Launch"}).json()
    assert m["status"] == "draft" and m["orientation"] == "portrait" and len(m["scenes"]) == 1
    avatar_id = _avatar(c)
    scenes = [{"avatar_id": avatar_id, "script": "Hello there."}, {"avatar_id": avatar_id, "script": "Goodbye."}]
    r = c.put(f"/api/movies/{m['id']}", json={"orientation": "landscape", "scenes": scenes})
    assert r.status_code == 200
    body = r.json()
    assert body["orientation"] == "landscape" and [s["script"] for s in body["scenes"]] == ["Hello there.", "Goodbye."]
    assert body["credits_estimate"] == 2 * (config.CREDITS_PER_VOICE_GENERATION + config.CREDITS_PER_AVATAR_VIDEO)
    assert any(x["id"] == m["id"] for x in c.get("/api/movies").json())


def test_other_users_cannot_see_edit_or_render_my_movie():
    owner = _client("movie_owner")
    other = _client("movie_other")
    m = owner.post("/api/movies", json={}).json()
    assert other.get(f"/api/movies/{m['id']}").status_code == 404
    assert other.put(f"/api/movies/{m['id']}", json={"title": "x"}).status_code == 404
    assert other.post(f"/api/movies/{m['id']}/render").status_code == 404


def test_render_requires_scripts_and_looks():
    c = _client("movie_checks")
    m = c.post("/api/movies", json={}).json()
    assert c.post(f"/api/movies/{m['id']}/render").status_code == 400  # no script
    c.put(f"/api/movies/{m['id']}", json={"scenes": [{"script": "Hi there."}]})
    r = c.post(f"/api/movies/{m['id']}/render")
    assert r.status_code == 400 and "avatar look" in r.json()["detail"]
    c.put(f"/api/movies/{m['id']}", json={"scenes": [{"avatar_id": _avatar(c), "script": "Hi there."}] * 2})
    r = c.post(f"/api/movies/{m['id']}/render")  # 20 signup credits < 2 scenes
    assert r.status_code == 402 and "Not enough credits" in r.json()["detail"]


@pytest.mark.skipif(not FFMPEG, reason="FFmpeg not installed")
def test_worker_renders_each_scene_and_joins_them(monkeypatch, tmp_path):
    c = _client("movie_render")
    _give_credits("movie_render")
    avatar_id = _avatar(c)
    m = c.post("/api/movies", json={"scenes": [{"avatar_id": avatar_id, "script": "One."}, {"avatar_id": avatar_id, "script": "Two."}]}).json()

    def fake_speech(text, out_path, voice_id=None):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "sine=duration=1", str(out_path)], check=True)

    def fake_run(job_id):  # stands in for the GPU render: a 1-second clip with sound
        with SessionLocal() as db:
            job = db.get(AvatarJob, job_id)
            out = config.STORAGE_DIR / "avatar_videos" / f"{job_id}.mp4"
            out.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=25",
                            "-f", "lavfi", "-i", "sine=duration=1", "-t", "1", "-pix_fmt", "yuv420p", "-shortest", str(out)], check=True)
            job.status, job.output_video_path = "completed", f"/storage/avatar_videos/{out.name}"
            db.commit()

    monkeypatch.setattr(movies.voice_provider, "generate_speech", fake_speech)
    monkeypatch.setattr(avatar_jobs, "_run_avatar_video", fake_run)
    monkeypatch.setattr(movies, "enqueue", lambda movie_id: None)  # run inline below

    assert c.post(f"/api/movies/{m['id']}/render").json()["status"] == "rendering"
    assert c.put(f"/api/movies/{m['id']}", json={"title": "x"}).status_code == 409  # locked while rendering
    movies.render_movie(m["id"])

    done = c.get(f"/api/movies/{m['id']}").json()
    assert done["status"] == "completed", done["error_message"]
    assert [s["status"] for s in done["scenes"]] == ["completed", "completed"]
    out = config.STORAGE_DIR / "avatar_videos" / done["output_video_path"].rsplit("/", 1)[1]
    probe = shutil.which("ffprobe") or FFMPEG.replace("ffmpeg", "ffprobe")
    seconds = float(subprocess.run([probe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
                                   capture_output=True, text=True, check=True).stdout)
    assert 1.8 < seconds < 2.4  # two 1-second scenes joined


def test_scene_failure_stops_the_movie_with_a_clear_error(monkeypatch):
    c = _client("movie_fail")
    _give_credits("movie_fail")
    avatar_id = _avatar(c)
    m = c.post("/api/movies", json={"scenes": [{"avatar_id": avatar_id, "script": "One."}]}).json()

    def boom(text, out_path, voice_id=None):
        raise RuntimeError("VibeVoice is not reachable")

    monkeypatch.setattr(movies.voice_provider, "generate_speech", boom)
    monkeypatch.setattr(movies, "enqueue", lambda movie_id: None)
    c.post(f"/api/movies/{m['id']}/render")
    movies.render_movie(m["id"])
    done = c.get(f"/api/movies/{m['id']}").json()
    assert done["status"] == "failed" and "Scene 1 failed" in done["error_message"]
    assert done["scenes"][0]["status"] == "failed"


def test_restart_recovers_stuck_movies_and_avatar_jobs():
    c = _client("movie_recover")
    m = c.post("/api/movies", json={}).json()
    with SessionLocal() as db:
        db.get(Movie, m["id"]).status = "rendering"
        user_id = db.get(Movie, m["id"]).user_id
        job = AvatarJob(user_id=user_id, job_type="avatar_talking", status="queued", provider="x", credits_cost=0)
        db.add(job)
        db.commit()
        job_id = job.id
        _recover_interrupted_jobs(db)
        assert db.get(Movie, m["id"]).status == "failed"
        assert db.get(AvatarJob, job_id).status == "failed"
