"""Director: templates, orchestration (planner/clip engine mocked, real ffmpeg), series and mixing."""
import json
import subprocess
import time
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import director, director_templates as tpl
from app.services.music_playback import audio_duration, find_ffmpeg_tool

FFMPEG = find_ffmpeg_tool("ffmpeg")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(director, "STORAGE_DIR", tmp_path / "storage")
    director._active.clear()
    director._cancelled.clear()
    yield


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _clip(path, seconds=3.0, size="320x180", audio=True, color="red"):
    args = [FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={color}:s={size}:d={seconds}:r=24"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=f=440:d={seconds}"]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p"] + (["-c:a", "aac", "-shortest"] if audio else []) + [str(path)]
    subprocess.run(args, check=True)
    return path


def _wav(path, seconds=1.2, freq=300):
    t = np.arange(int(22050 * seconds)) / 22050
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes((0.3 * np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16).tobytes())
    return path


def _plan_for(seconds, shots=3, narration=True):
    each = seconds // shots
    durations = [each] * (shots - 1) + [seconds - each * (shots - 1)]
    return {
        "title": "Test Film", "synopsis": "A courier crosses a flooded city.", "model": "fake",
        "characters": [{"id": "ada", "name": "Ada", "description": "a courier in a yellow coat"}],
        "locations": [{"id": "city", "name": "Flooded city", "description": "streets under knee-deep water"}],
        "shots": [{"id": f"s{i}", "duration_seconds": d, "description": f"shot {i}", "narration": f"Line {i}." if narration else "",
                   "video_prompt": f"video {i}", "image_prompt": f"image {i}"} for i, d in enumerate(durations)],
    }


def _wait(project_id, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        project = director.get_project(project_id)
        if project["status"] in ("done", "error", "cancelled"):
            return project
        time.sleep(0.3)
    raise AssertionError("project did not finish")


def _patch_engine(monkeypatch, tmp_path, *, narration=True, music=True, fail_plan=False):
    calls = {"shoot": [], "plan_prompts": []}

    def fake_plan(prompt, seconds, planner="fast"):
        calls["plan_prompts"].append(prompt)
        if fail_plan:
            raise director.DirectorError("The story planner did not answer.")
        return _plan_for(seconds, narration=narration)

    def fake_shoot(project_id, project, shot, index):
        calls["shoot"].append(index)
        size = "180x320" if project["orientation"] == "portrait" else "320x180"
        director._update_shot(project_id, index, status="done", clip_url=f"/storage/clips/{index}.mp4")
        return _clip(tmp_path / f"clip{index}.mp4", shot["duration"], size, audio=index != 1)

    monkeypatch.setattr(director, "_plan", fake_plan)
    monkeypatch.setattr(director, "_shoot", fake_shoot)
    monkeypatch.setattr(director, "_narrate", lambda shots, lengths, voice_id, work: [(_wav(work / "n0.wav"), 0.2), (_wav(work / "n1.wav"), lengths[0] + 0.2)])
    monkeypatch.setattr(director, "_score", lambda template, brief, seconds: _wav(tmp_path / "music.wav", seconds=6, freq=220))
    return calls


# --- Templates -----------------------------------------------------------------------

def test_there_are_twelve_templates_with_art_and_sane_limits():
    ids = [t["id"] for t in tpl.TEMPLATES]
    assert len(ids) == 12 and len(set(ids)) == 12
    for t in tpl.TEMPLATES:
        low, default, high = t["seconds"]["min"], t["seconds"]["default"], t["seconds"]["max"]
        assert 10 <= low <= default <= high <= 180, t["id"]
        assert t["orientation"] in ("portrait", "landscape") and t["fields"] and t["structure"]
        assert any(f["required"] for f in t["fields"]), t["id"]
    assert tpl.get_template("micro-drama")["series"] and tpl.get_template("micro-drama")["orientation"] == "portrait"


def test_brief_is_cleaned_and_required_fields_enforced():
    t = tpl.get_template("product-ads")
    brief = tpl.clean_brief(t, {"product": "  Amber   sunglasses ", "benefit": "x" * 900, "evil": "ignored"})
    assert brief["product"] == "Amber sunglasses" and len(brief["benefit"]) == tpl.MAX_FIELD_CHARS and "evil" not in brief
    with pytest.raises(tpl.TemplateError, match="Product"):
        tpl.clean_brief(t, {"benefit": "good"})
    with pytest.raises(tpl.TemplateError):
        tpl.get_template("nope")


def test_prompt_mentions_shape_narration_and_series():
    t = tpl.get_template("micro-drama")
    prompt = tpl.compose_prompt(t, {"premise": "A nurse meets her neighbour."}, "Episode 2 of a series.")
    assert "vertical" in prompt and "A nurse meets her neighbour." in prompt and "Episode 2" in prompt and "no narration" in prompt.lower()
    assert "narration line" in tpl.compose_prompt(tpl.get_template("explainer"), {"topic": "tides"})


def test_music_style_follows_the_brief_for_music_videos():
    mv = tpl.get_template("music-video")
    assert "reggae" in tpl.music_style(mv, {"genre": "reggae"}) and tpl.music_style(tpl.get_template("short-film"), {})


# --- API --------------------------------------------------------------------------------

def test_templates_endpoint_hides_internal_structure(client):
    data = client.get("/api/director/templates").json()
    assert len(data["templates"]) == 12 and data["credits_per_clip"] > 0
    assert all("structure" not in t for t in data["templates"])


def test_bad_requests_are_refused(client):
    assert client.post("/api/director/projects", json={"template": "nope", "brief": {}, "seconds": 30}).status_code == 400
    assert client.post("/api/director/projects", json={"template": "product-ads", "brief": {}, "seconds": 20}).status_code == 400
    r = client.post("/api/director/projects", json={"template": "product-ads", "brief": {"product": "p", "benefit": "b"}, "seconds": 90})
    assert r.status_code == 400 and "10 to 45" in r.json()["detail"] or "runs" in r.json()["detail"]
    assert client.get("/api/director/projects/doesnotexist").status_code == 404


# --- Orchestration ------------------------------------------------------------------------

def test_full_film_is_planned_shot_joined_narrated_scored_and_mixed(client, monkeypatch, tmp_path):
    calls = _patch_engine(monkeypatch, tmp_path)
    r = client.post("/api/director/projects", json={
        "template": "explainer", "brief": {"topic": "How tides work", "audience": "kids"}, "seconds": 30, "music": True, "narration": True})
    assert r.status_code == 202, r.text
    body = r.json()
    assert "prompt" not in body and "user_id" not in body and body["credits_estimate"]["total_high"] > 0
    done = _wait(body["id"])
    assert done["status"] == "done", done
    assert calls["shoot"] == [0, 1, 2] and done["title"] == "Test Film" and len(done["shots"]) == 3
    assert not done["notes"], done["notes"]
    final = tmp_path / "storage" / "videos" / f"director-{body['id']}.mp4"
    assert final.is_file() and done["result_url"] == f"/storage/videos/{final.name}"
    info = director._probe(final)
    assert info["audio"] and info["seconds"] == pytest.approx(30, abs=1.0)
    listed = client.get("/api/director/projects").json()
    assert body["id"] in [p["id"] for p in listed]
    assert client.delete(f"/api/director/projects/{body['id']}").status_code == 204
    assert not final.exists() and client.get(f"/api/director/projects/{body['id']}").status_code == 404


def test_music_and_narration_failures_do_not_lose_the_film(client, monkeypatch, tmp_path):
    _patch_engine(monkeypatch, tmp_path)
    monkeypatch.setattr(director, "_narrate", lambda *a, **k: (_ for _ in ()).throw(director.DirectorError("No local voice is ready.")))
    monkeypatch.setattr(director, "_score", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("engine offline")))
    r = client.post("/api/director/projects", json={"template": "promo-video", "brief": {"offer": "Opening day"}, "seconds": 30})
    done = _wait(r.json()["id"])
    assert done["status"] == "done"
    assert any("Narration skipped" in n for n in done["notes"]) and any("Soundtrack skipped" in n for n in done["notes"])


def test_planner_failure_ends_in_a_clear_error(client, monkeypatch, tmp_path):
    _patch_engine(monkeypatch, tmp_path, fail_plan=True)
    r = client.post("/api/director/projects", json={"template": "short-film", "brief": {"story": "A quiet night."}, "seconds": 30})
    done = _wait(r.json()["id"])
    assert done["status"] == "error" and "planner" in done["error"]


def test_cancel_stops_before_the_next_shot(client, monkeypatch, tmp_path):
    calls = _patch_engine(monkeypatch, tmp_path)
    real_shoot = director._shoot

    def slow_shoot(project_id, project, shot, index):
        if index == 0:
            director.cancel(project_id)
        return real_shoot(project_id, project, shot, index)

    monkeypatch.setattr(director, "_shoot", slow_shoot)
    r = client.post("/api/director/projects", json={"template": "short-film", "brief": {"story": "A quiet night."}, "seconds": 30})
    done = _wait(r.json()["id"])
    assert done["status"] == "cancelled" and calls["shoot"] == [0]


def test_micro_drama_continues_with_the_same_characters(client, monkeypatch, tmp_path):
    calls = _patch_engine(monkeypatch, tmp_path, narration=False)
    first = client.post("/api/director/projects", json={"template": "micro-drama", "brief": {"premise": "A nurse meets her neighbour."},
                                                        "seconds": 45, "music": False, "narration": False}).json()
    done = _wait(first["id"])
    assert done["status"] == "done" and done["episode"] == 1 and done["series_id"]
    series = client.get(f"/api/director/series/{done['series_id']}").json()
    assert series["characters"][0]["name"] == "Ada" and series["episodes"][0]["synopsis"].startswith("A courier")
    nxt = client.post(f"/api/director/series/{series['id']}/next", json={"direction": "Ada finds the letter.", "music": False})
    assert nxt.status_code == 202 and nxt.json()["episode"] == 2
    _wait(nxt.json()["id"])
    prompt = calls["plan_prompts"][-1]
    assert "episode 2" in prompt.lower() and "Ada: a courier in a yellow coat" in prompt and "Ada finds the letter" in prompt
    assert "cliffhanger" in prompt
    # an unfinished series cannot be continued twice at once
    assert client.post("/api/director/series/zzzz/next", json={}).status_code == 400


# --- Real ffmpeg helpers ---------------------------------------------------------------------

def test_concat_normalises_mixed_sizes_and_missing_audio(tmp_path):
    clips = [_clip(tmp_path / "a.mp4", 2, "320x180"), _clip(tmp_path / "b.mp4", 2, "640x360", audio=False, color="blue"),
             _clip(tmp_path / "c.mp4", 2, "160x90", color="green")]
    dest = tmp_path / "out.mp4"
    lengths = director.concat_clips(clips, dest)
    info = director._probe(dest)
    assert (info["width"], info["height"]) == (320, 180) and info["audio"]
    assert info["seconds"] == pytest.approx(sum(lengths), abs=0.4)


def test_mix_adds_narration_and_looped_music_under_the_picture(tmp_path):
    joined = _clip(tmp_path / "joined.mp4", 8)  # the joined film always carries an audio track
    dest = tmp_path / "mixed.mp4"
    director.mix_audio(joined, dest, [(_wav(tmp_path / "n.wav", 1.5), 1.0)], _wav(tmp_path / "m.wav", 3, 220), 8.0)
    info = director._probe(dest)
    assert info["audio"] and info["seconds"] == pytest.approx(8, abs=0.5)
    assert audio_duration(dest) == pytest.approx(8, abs=0.5)


def test_estimate_is_a_range_from_the_shot_length_limits():
    ten, sixty = director.estimate_credits(10), director.estimate_credits(60)
    assert (ten["clips_low"], ten["clips_high"]) == (2, 3) and (sixty["clips_low"], sixty["clips_high"]) == (8, 20)
    assert sixty["total_high"] == 20 * sixty["per_clip"] and sixty["total_low"] < sixty["total_high"]


@pytest.mark.parametrize("durations,target", [([4, 4, 4, 4, 4], 30), ([2, 2, 2, 2, 2], 10), ([10, 10], 12), ([6, 6, 6, 6], 20), ([5, 5, 5], 15)])
def test_fit_durations_always_hits_the_target_within_clip_limits(durations, target):
    plan = _plan_for(sum(durations), shots=len(durations))
    for shot, d in zip(plan["shots"], durations):
        shot["duration_seconds"] = d
    fitted = director.fit_durations(plan, target)
    lengths = [s["duration_seconds"] for s in fitted["shots"]]
    assert sum(lengths) == target and all(director.MIN_CLIP <= n <= director.MAX_CLIP for n in lengths), lengths


def test_fit_durations_refuses_the_impossible():
    plan = _plan_for(30, shots=2)
    with pytest.raises(director.DirectorError):
        director.fit_durations(plan, 100)


def test_prompt_asks_for_a_sensible_number_of_shots():
    prompt = tpl.compose_prompt(tpl.get_template("short-film"), {"story": "x"}, None, 60)
    assert "between 8 and 20 shots" in prompt


def test_shoot_makes_a_keyframe_for_vertical_videos_and_retries_once(monkeypatch, tmp_path):
    events = []
    project = {"user_id": "u1", "orientation": "portrait"}
    shot = {"id": "s0", "duration": 4, "video_prompt": "v", "image_prompt": "i"}
    director._write({"id": "abc123", "status": "running", "shots": [dict(shot, status="queued", video_id=None, clip_url=None, keyframe_url=None, error=None)]})
    director._active.add("abc123")
    monkeypatch.setattr(director, "_video_choice", lambda portrait: ("local_h3", "image_to_video"))
    monkeypatch.setattr(director, "_render_keyframe", lambda prompt, size, dest: (events.append(("frame", size)), dest.write_bytes(b"png")))
    created = []
    monkeypatch.setattr(director, "_create_clip_job", lambda uid, s, provider, mode, src: (created.append((provider, mode, src)), f"vid{len(created)}")[1])
    outcomes = iter([{"status": "failed", "url": None, "error": "gpu hiccup"}, {"status": "completed", "url": "/storage/clips/x.mp4", "error": None}])
    monkeypatch.setattr(director, "_wait_clip", lambda pid, vid: next(outcomes))
    path = director._shoot("abc123", project, shot, 0)
    assert events == [("frame", director.PORTRAIT_SIZE)] and len(created) == 2
    assert created[0][1] == "image_to_video" and created[0][2] == "/storage/director/abc123/shot-01.png"
    assert str(path).endswith("clips\\x.mp4") or str(path).endswith("clips/x.mp4")
    saved = json.loads(director._file("abc123").read_text(encoding="utf-8"))
    assert saved["shots"][0]["status"] == "done" and saved["shots"][0]["keyframe_url"].endswith("shot-01.png")


def test_a_cancelled_or_failed_episode_does_not_count_in_the_series(client, monkeypatch, tmp_path):
    calls = _patch_engine(monkeypatch, tmp_path, narration=False)
    first = client.post("/api/director/projects", json={"template": "micro-drama", "brief": {"premise": "A nurse meets her neighbour."},
                                                        "seconds": 45, "music": False, "narration": False}).json()
    done = _wait(first["id"])
    series_id = done["series_id"]
    real_shoot = director._shoot
    monkeypatch.setattr(director, "_shoot", lambda *a, **k: (_ for _ in ()).throw(director.DirectorError("GPU out of memory")))
    bad = client.post(f"/api/director/series/{series_id}/next", json={"music": False}).json()
    assert _wait(bad["id"])["status"] == "error"
    assert [e["number"] for e in client.get(f"/api/director/series/{series_id}").json()["episodes"]] == [1]
    monkeypatch.setattr(director, "_shoot", real_shoot)
    again = client.post(f"/api/director/series/{series_id}/next", json={"music": False}).json()
    assert again["episode"] == 2 and _wait(again["id"])["status"] == "done"
    assert client.delete(f"/api/director/projects/{again['id']}").status_code == 204
    assert [e["number"] for e in client.get(f"/api/director/series/{series_id}").json()["episodes"]] == [1]
