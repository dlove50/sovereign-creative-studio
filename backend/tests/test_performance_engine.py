"""Multi-Performer Director engine: per-performer vocal ownership, states, drive audio, camera."""
import numpy as np
import pytest

from app.services import performance_engine as pe

RATE = pe.DRIVE_RATE


def _sung(seconds: float, start: float, end: float, *, freq: float = 220.0, decay: bool = False) -> np.ndarray:
    """A vocal-like stem: a vibrato tone between start and end, quiet room noise elsewhere."""
    t = np.arange(int(seconds * RATE)) / RATE
    rng = np.random.default_rng(int(freq))
    out = rng.normal(0, 0.0005, t.size).astype(np.float32)
    on = (t >= start) & (t < end)
    vibrato = np.sin(2 * np.pi * freq * t + 3 * np.sin(2 * np.pi * 5.5 * t))
    level = 0.4 * np.exp(-1.2 * (t - start)) + 0.06 if decay else 0.4
    out[on] += (vibrato * level)[on].astype(np.float32)
    return out


@pytest.fixture()
def duet(tmp_path):
    a = _sung(12, 0, 4) + _sung(12, 8, 10)            # verse 1 + chorus
    b = _sung(12, 4, 8, freq=330) + _sung(12, 8, 10, freq=330)  # verse 2 + chorus harmony
    a_path, b_path = pe.write_wav(tmp_path / "a.wav", a), pe.write_wav(tmp_path / "b.wav", b)
    master = pe.write_wav(tmp_path / "master.wav", (a + b) / 2)
    project = pe.create("user-1", "Two singers", ["Singer A", "Singer B"], "alternating")
    project["master_audio"] = str(master)
    pe.set_duration_from(project, master)
    project["performers"][0]["stem"], project["performers"][1]["stem"] = str(a_path), str(b_path)
    pe.analyze_stems(project)
    pe.save(project)
    return project


def _ids(project):
    return [p["id"] for p in project["performers"]]


def test_each_performer_follows_only_their_own_stem(duet):
    a, b = duet["performers"]
    spans_a = [(round(r["start"]), round(r["end"])) for r in a["regions"]]
    spans_b = [(round(r["start"]), round(r["end"])) for r in b["regions"]]
    assert spans_a == [(0, 4), (8, 10)]
    assert spans_b == [(4, 8), (8, 10)] or spans_b == [(4, 10)]


def test_states_listening_and_idle_are_resolved(duet):
    a, b = _ids(duet)
    assert (pe.state_at(duet, a, 1.0), pe.state_at(duet, b, 1.0)) == ("SINGING", "LISTENING")
    assert (pe.state_at(duet, a, 6.0), pe.state_at(duet, b, 6.0)) == ("LISTENING", "SINGING")
    assert (pe.state_at(duet, a, 9.0), pe.state_at(duet, b, 9.0)) == ("SINGING", "SINGING")
    assert (pe.state_at(duet, a, 11.0), pe.state_at(duet, b, 11.0)) == ("IDLE", "IDLE")


def test_drive_audio_is_silent_when_the_performer_is_not_voiced(duet):
    a, b = _ids(duet)
    path_b = pe.build_drive_audio(duet, b)
    drive_b = pe.decode(path_b)
    assert np.max(np.abs(drive_b[: int(3.8 * RATE)])) == 0.0          # B is silent through verse 1
    assert np.max(np.abs(drive_b[int(5 * RATE): int(7 * RATE)])) > 0.1  # and sings verse 2
    drive_a = pe.decode(pe.build_drive_audio(duet, a))
    assert np.max(np.abs(drive_a[int(4.3 * RATE): int(7.7 * RATE)])) == 0.0  # A stops during verse 2
    assert np.max(np.abs(drive_a[int(10.5 * RATE):])) == 0.0


def test_sustained_decaying_note_is_one_region(tmp_path):
    stem = pe.write_wav(tmp_path / "held.wav", _sung(8, 1, 6, decay=True))
    regions = pe.detect_voice(pe.decode(stem))
    assert len(regions) == 1 and regions[0]["start"] < 1.1 and regions[0]["end"] > 5.5


def test_director_sheet_and_camera_follow_the_voices(duet):
    sheet = pe.director_sheet(duet)
    first = sheet[0]
    assert first["performers"] == {"Singer A": "SINGING", "Singer B": "LISTENING"}
    assert first["camera"] == "close up on Singer A"
    chorus = next(r for r in sheet if r["start"] <= 9 < r["end"])
    assert chorus["performers"] == {"Singer A": "SINGING", "Singer B": "SINGING"}
    assert chorus["camera"] == "two shot"


def test_lead_background_mode_relabels_the_second_singer(duet):
    a, b = _ids(duet)
    pe.apply_mode(duet, "lead_background")
    assert pe.state_at(duet, b, 6.0) == "BACKGROUND_VOCAL"
    assert pe.state_at(duet, a, 1.0) == "SINGING"
    chorus = next(s for s in duet["camera"] if s["start"] <= 9 < s["end"])
    assert chorus["shot"] == "close_up" and chorus["focus"] == a  # the lead stays the focus


def test_listener_cues_look_at_the_singer(duet):
    a, b = _ids(duet)
    cue = next(c for c in pe.motion_cues(duet, b) if c["start"] <= 1 < c["end"])
    assert cue["state"] == "LISTENING" and cue["look_at"] == a and "mouth closed" in cue["direction"]


def test_manual_edits_survive_reanalysis_and_overlaps_are_rejected(duet):
    a, _ = _ids(duet)
    pe.set_regions(duet, a, [{"start": 0.0, "end": 2.0, "state": "SINGING"},
                             {"start": 2.0, "end": 3.0, "state": "MOVING"}])
    pe.analyze_stems(duet)
    performer = pe.performer(duet, a)
    assert any(r["state"] == "MOVING" and r["manual"] for r in performer["regions"])
    pe.set_regions(duet, a, [{"start": 0.0, "end": 2.0, "state": "SINGING"},
                             {"start": 1.0, "end": 3.0, "state": "SINGING"}])
    with pytest.raises(pe.PerformanceError, match="overlap"):
        pe.validate(duet)


def test_voiced_region_without_any_vocal_is_rejected():
    project = pe.create("user-1", "x", ["Solo"])
    project["duration"] = 10
    pe.set_regions(project, project["performers"][0]["id"], [{"start": 0, "end": 2, "state": "SINGING"}])
    with pytest.raises(pe.PerformanceError, match="vocal stem"):
        pe.validate(project)


def test_handoffs_split_a_shared_vocal(tmp_path):
    vocal = pe.write_wav(tmp_path / "vocal.wav", _sung(10, 0, 9))
    project = pe.create("user-1", "One vocal, two singers", ["A", "B"], "call_response")
    project["shared_vocal"] = str(vocal)
    pe.set_duration_from(project, vocal)
    a, b = _ids(project)
    pe.assign_handoffs(project, [{"start": 0, "end": 3, "performers": [a]},
                                 {"start": 3, "end": 6, "performers": [b]},
                                 {"start": 6, "end": 10, "performers": [a, b]}])
    pe.validate(project)
    assert pe.state_at(project, a, 1) == "SINGING" and pe.state_at(project, b, 1) == "LISTENING"
    assert pe.state_at(project, a, 4) == "LISTENING" and pe.state_at(project, b, 4) == "SINGING"
    assert pe.state_at(project, a, 7) == pe.state_at(project, b, 7) == "SINGING"


def test_performers_never_share_motion_and_render_plan_reports_gaps(duet):
    a, b = duet["performers"]
    assert a["motion"]["seed"] != b["motion"]["seed"] and a["motion"]["phase"] != b["motion"]["phase"]
    plan = pe.render_plan(duet)
    assert plan["strategy"] == "multi_person_single_pass"
    assert not plan["ready"] and "Singer A: identity picture" in plan["missing"]


def test_api_full_duet_flow(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app

    a = _sung(10, 0, 4) + _sung(10, 7, 9)
    b = _sung(10, 4, 7, freq=330) + _sung(10, 7, 9, freq=330)
    files = {n: pe.write_wav(tmp_path / f"{n}.wav", s) for n, s in (("a", a), ("b", b), ("m", (a + b) / 2))}
    with TestClient(app) as client:
        r = client.post("/api/performances", json={"title": "Duet", "performers": ["Ava", "Ben"], "mode": "alternating"})
        assert r.status_code == 201, r.text
        project = r.json()
        pid, (ava, ben) = project["id"], [p["id"] for p in project["performers"]]
        assert "user_id" not in project
        base = f"/api/performances/{pid}"
        assert client.post(f"{base}/master", files={"file": ("m.wav", files["m"].read_bytes())}).status_code == 200
        for perf, key in ((ava, "a"), (ben, "b")):
            r = client.post(f"{base}/performers/{perf}/stem", files={"file": (f"{key}.wav", files[key].read_bytes())})
            assert r.status_code == 200, r.text
        bad = client.post(f"{base}/performers/{ava}/stem", files={"file": ("x.exe", b"MZ")})
        assert bad.status_code == 400
        r = client.post(f"{base}/analyze")
        assert r.status_code == 200, r.text
        sheet = r.json()["sheet"]
        assert sheet[0]["performers"] == {"Ava": "SINGING", "Ben": "LISTENING"}
        r = client.post(f"{base}/drive-audio")
        assert r.status_code == 200, r.text
        drive_url = next(p for p in r.json()["performers"] if p["id"] == ben)["drive_audio_url"]
        assert client.get(drive_url).status_code == 200
        assert client.get(f"{base}/files/..%2F{pid}.json").status_code == 404
        r = client.patch(base, json={"mode": "lead_background"})
        assert r.status_code == 200 and r.json()["mode"] == "lead_background"
        plan = client.get(f"{base}/render-plan").json()
        assert plan["passes"][1]["voiced_seconds"] > 3 and "Ava: identity picture" in plan["missing"]
        assert client.delete(base).status_code == 204
        assert client.get(base).status_code == 404
