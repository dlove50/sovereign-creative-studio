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


def test_batch_creates_one_single_scene_movie_per_row_as_drafts():
    c = _client("batch_draft")
    avatar_id = _avatar(c)
    rows = [{"title": "Welcome", "script": "Hi one."}, {"script": "Hi two."}, {"title": "Bye", "script": "Hi three."}]
    r = c.post("/api/movies/batch", json={"avatar_id": avatar_id, "orientation": "landscape", "rows": rows})
    assert r.status_code == 201, r.text
    made = r.json()
    assert [m["title"] for m in made] == ["Welcome", "Batch video 2", "Bye"]
    assert all(m["status"] == "draft" and m["orientation"] == "landscape" and len(m["scenes"]) == 1 for m in made)
    assert made[1]["scenes"][0]["script"] == "Hi two." and made[1]["scenes"][0]["avatar_id"] == avatar_id


def test_batch_render_is_all_or_nothing_on_credits_and_checks_the_avatar(monkeypatch):
    c = _client("batch_credits")  # 20 signup credits: one video costs 17, three cost 51
    avatar_id = _avatar(c)
    before = len(c.get("/api/movies").json())
    rows = [{"script": "One."}, {"script": "Two."}, {"script": "Three."}]
    r = c.post("/api/movies/batch", json={"avatar_id": avatar_id, "rows": rows, "render": True})
    assert r.status_code == 402 and "need 51" in r.json()["detail"]
    assert len(c.get("/api/movies").json()) == before  # nothing was created
    assert c.post("/api/movies/batch", json={"avatar_id": "nope", "rows": rows}).status_code == 404

    queued = []
    monkeypatch.setattr(movies, "enqueue", lambda movie_id: queued.append(movie_id))
    _give_credits("batch_credits")
    ok = c.post("/api/movies/batch", json={"avatar_id": avatar_id, "rows": rows, "render": True})
    assert ok.status_code == 201 and [m["status"] for m in ok.json()] == ["rendering"] * 3
    assert queued == [m["id"] for m in ok.json()]


def test_batch_is_limited_to_50_rows():
    c = _client("batch_limit")
    avatar_id = _avatar(c)
    rows = [{"script": "x"}] * 51
    assert c.post("/api/movies/batch", json={"avatar_id": avatar_id, "rows": rows}).status_code == 422


def test_batch_variants_select_each_rows_avatar_and_voice_atomically():
    c = _client("batch_variants")
    avatar_a, avatar_b = _avatar(c), _avatar(c)
    request = {"avatar_id": avatar_a, "tts_voice_id": "batch_voice", "rows": [
        {"title": "Default", "script": "One."},
        {"title": "Variant", "script": "Two.", "avatar_id": avatar_b, "tts_voice_id": "other_voice"},
    ]}
    r = c.post("/api/movies/batch", json=request)
    assert r.status_code == 201, r.text
    scenes = [m["scenes"][0] for m in r.json()]
    assert [(s["avatar_id"], s["tts_voice_id"]) for s in scenes] == [(avatar_a, "batch_voice"), (avatar_b, "other_voice")]
    before = len(c.get("/api/movies").json())
    other = _client("batch_variant_other")
    request["rows"][1]["avatar_id"] = _avatar(other)
    assert c.post("/api/movies/batch", json=request).status_code == 404
    assert len(c.get("/api/movies").json()) == before
    request["rows"] = [{"script": "   "}]
    assert c.post("/api/movies/batch", json=request).status_code == 422


def test_batch_cross_product_makes_every_script_with_each_presenter_and_voice():
    c = _client("batch_cross")
    avatar_a, avatar_b = [
        c.post("/api/avatars/photo", data={"name": name}, files={"file": ("p.png", PNG, "image/png")}).json()["id"]
        for name in ("Ada", "Ben")
    ]
    request = {"avatar_id": avatar_a, "avatar_ids": [avatar_a, avatar_b, avatar_a], "tts_voice_ids": ["v1", "v2"],
               "rows": [{"title": "Intro", "script": "One."}, {"script": "Two."}]}
    r = c.post("/api/movies/batch", json=request)
    assert r.status_code == 201, r.text
    made = r.json()
    assert len(made) == 2 * 2 * 2  # 2 scripts x 2 distinct presenters x 2 voices; the duplicate presenter is ignored
    combos = {(m["scenes"][0]["script"], m["scenes"][0]["avatar_id"], m["scenes"][0]["tts_voice_id"]) for m in made}
    assert combos == {(s, a, v) for s in ("One.", "Two.") for a in (avatar_a, avatar_b) for v in ("v1", "v2")}
    assert len({m["title"] for m in made}) == 8  # every video is told apart by script, presenter and voice
    assert all(m["title"].startswith(("Intro", "Batch video 2")) and m["status"] == "draft" for m in made)
    assert any("Ada" in m["title"] for m in made) and any("Ben" in m["title"] for m in made)


def test_batch_cross_product_respects_row_overrides_and_old_requests_are_unchanged():
    c = _client("batch_cross_override")
    avatar_a, avatar_b = _avatar(c), _avatar(c)
    request = {"avatar_id": avatar_a, "avatar_ids": [avatar_a, avatar_b], "rows": [
        {"script": "Fans out."}, {"script": "Pinned.", "avatar_id": avatar_b}]}
    made = c.post("/api/movies/batch", json=request).json()
    assert [m["scenes"][0]["avatar_id"] for m in made] == [avatar_a, avatar_b, avatar_b]
    plain = c.post("/api/movies/batch", json={"avatar_id": avatar_a, "rows": [{"script": "Solo."}]}).json()
    assert [m["title"] for m in plain] == ["Batch video 1"] and plain[0]["scenes"][0]["avatar_id"] == avatar_a


def test_batch_cross_product_is_capped_checked_and_priced_on_the_expanded_total(monkeypatch):
    c = _client("batch_cross_limits")
    avatars = [_avatar(c) for _ in range(3)]
    rows = [{"script": f"Script {i}."} for i in range(17)]  # 17 x 3 = 51 videos
    too_many = c.post("/api/movies/batch", json={"avatar_id": avatars[0], "avatar_ids": avatars, "rows": rows})
    assert too_many.status_code == 422 and "51" in too_many.json()["detail"]
    other = _client("batch_cross_stranger")
    foreign = c.post("/api/movies/batch", json={"avatar_id": avatars[0], "avatar_ids": [avatars[0], _avatar(other)],
                                                "rows": rows[:2]})
    assert foreign.status_code == 404
    before = len(c.get("/api/movies").json())
    poor = c.post("/api/movies/batch", json={"avatar_id": avatars[0], "avatar_ids": avatars, "rows": rows[:2], "render": True})
    assert poor.status_code == 402 and "6 videos need 102" in poor.json()["detail"]  # 2 scripts x 3 presenters x 17 credits
    assert len(c.get("/api/movies").json()) == before
    assert c.post("/api/movies/batch", json={"avatar_id": avatars[0], "avatar_ids": [""], "rows": rows[:1]}).status_code == 422


def test_retry_reuses_completed_scene_after_later_scene_fails(monkeypatch):
    c = _client("movie_resume")
    _give_credits("movie_resume")
    avatar_id = _avatar(c)
    m = c.post("/api/movies", json={"scenes": [
        {"avatar_id": avatar_id, "script": "One."},
        {"avatar_id": avatar_id, "script": "Two."},
    ]}).json()
    spoken, rendered = [], []
    fail_second = True

    def speech(text, out_path, voice_id=None):
        spoken.append(text)
        if text == "Two." and fail_second:
            raise RuntimeError("Temporary voice outage")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"test audio")

    def render(job_id):
        rendered.append(job_id)
        with SessionLocal() as db:
            job = db.get(AvatarJob, job_id)
            path = config.STORAGE_DIR / "avatar_videos" / f"{job_id}.mp4"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"completed scene")
            job.status, job.output_video_path = "completed", f"/storage/avatar_videos/{path.name}"
            db.commit()

    joined = []
    def join(clips, out):
        joined.extend(clips)
        out.write_bytes(b"assembled movie")

    monkeypatch.setattr(movies.voice_provider, "generate_speech", speech)
    monkeypatch.setattr(avatar_jobs, "_run_avatar_video", render)
    monkeypatch.setattr(movies, "join_clips", join)
    monkeypatch.setattr(movies, "enqueue", lambda _: None)
    c.post(f"/api/movies/{m['id']}/render")
    movies.render_movie(m["id"])
    failed = c.get(f"/api/movies/{m['id']}").json()
    assert failed["status"] == "failed"
    first_job = failed["scenes"][0]["avatar_job_id"]
    # Enough for only the remaining scene: the route must not demand two scenes.
    _give_credits("movie_resume", config.CREDITS_PER_VOICE_GENERATION + config.CREDITS_PER_AVATAR_VIDEO)
    fail_second = False
    assert c.post(f"/api/movies/{m['id']}/render").status_code == 200
    movies.render_movie(m["id"])
    done = c.get(f"/api/movies/{m['id']}").json()
    assert done["status"] == "completed"
    assert spoken == ["One.", "Two.", "Two."]
    assert len(rendered) == 2 and rendered[0] == first_job
    assert len(joined) == 2 and joined[0].stem == first_job
    with SessionLocal() as db:
        movie = db.get(Movie, m["id"])
        scene = movies.load_scenes(movie)[0]
        assert movies.completed_scene_clip(db, movie, scene) is not None
        scene["script"] = "Changed words."
        assert movies.completed_scene_clip(db, movie, scene) is None
        scene = movies.load_scenes(movie)[0]
        movie.orientation = "landscape"
        assert movies.completed_scene_clip(db, movie, scene) is None
        movie.orientation = "portrait"
        joined[0].unlink()  # This fixture owns the temporary test file.
        assert movies.completed_scene_clip(db, movie, scene) is None
