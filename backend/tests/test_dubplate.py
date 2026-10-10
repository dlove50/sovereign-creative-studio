"""Dub plate studio: analysis, cues, validation and renders (real ffmpeg, synthetic track)."""
import json
import subprocess
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.services import dubplate, music, music_playback, stems, voice

BPM = 100.0
RATE = 22050
SECONDS = 24


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MUSIC_DIR", tmp_path / "music")
    yield


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _click_track(tmp_path) -> dict:
    """A 100 BPM kick pattern with a bass note, saved into the library as an MP3."""
    t = np.arange(RATE * SECONDS) / RATE
    audio = 0.05 * np.sin(2 * np.pi * 110 * t)
    beat = 60.0 / BPM
    for k in range(int(SECONDS / beat)):
        start = int((0.2 + k * beat) * RATE)
        n = int(0.12 * RATE)
        env = np.exp(-np.arange(n) / (0.025 * RATE))
        audio[start:start + n] += 0.9 * np.sin(2 * np.pi * 60 * np.arange(n) / RATE) * env
    wav_path = tmp_path / "click.wav"
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
    music._music_dir()
    song_id = "abcdef012345"
    ffmpeg = music_playback.find_ffmpeg_tool("ffmpeg")
    subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(wav_path), "-b:a", "128k", str(music.audio_path(song_id))], check=True)
    song = {"id": song_id, "title": "Click", "style": "test, reggae", "lyrics": "", "instrumental": True,
            "duration_requested": SECONDS, "seed": 1, "quality": "128k", "provider": "yue2", "favorite": False,
            "size_bytes": 1, "generation_seconds": 0, "created_at": "2026-01-01T00:00:00+00:00"}
    music._meta_path(song_id).write_text(json.dumps(song), encoding="utf-8")
    return song


def test_tempo_detection_finds_the_bpm(tmp_path):
    song = _click_track(tmp_path)
    a = dubplate.analyze(song["id"])
    assert a["duration"] == pytest.approx(SECONDS, abs=0.3)
    detected = a["bpm"]
    # The detector may land on the beat, its half or its double; the UI offers x2 and /2.
    assert any(detected == pytest.approx(BPM * f, abs=2.0) for f in (1.0, 0.5, 2.0)), detected
    assert len(__import__("base64").b64decode(a["peaks"])) == dubplate.PEAK_POINTS


def test_cues_loops_are_clamped_and_saved(tmp_path, client):
    song = _click_track(tmp_path)
    r = client.put(f"/api/music/songs/{song['id']}/dub/state", json={
        "cues": [{"slot": 0, "time": 3.5, "label": "drop"}, {"slot": 0, "time": 9, "label": "dupe"},
                 {"slot": 2, "time": 999, "label": "x" * 24}],
        "loops": [{"start": 4, "end": 8}, {"start": 5, "end": 5.01}], "bpm": 98.4, "beat_offset": 0.25})
    assert r.status_code == 200
    state = r.json()
    assert [c["slot"] for c in state["cues"]] == [0, 2], "duplicate slots are dropped"
    assert state["cues"][1]["time"] <= SECONDS, "times are clamped to the song"
    assert len(state["loops"]) == 1, "loops shorter than 0.1s are dropped"
    again = client.get(f"/api/music/songs/{song['id']}/dub").json()
    assert again["state"]["bpm"] == 98.4 and again["state"]["cues"][0]["label"] == "drop"
    assert client.put("/api/music/songs/zzzzzzzzzzzz/dub/state", json={}).status_code == 404


@pytest.mark.parametrize("bad", [
    {"start": 30}, {"start": 5, "end": 6}, {"filter_mode": "bandpass"}, {"echo_division": "1/7"},
    {"special_placement": "intro"}, {"special_placement": "sideways", "special_text": "hi"},
])
def test_render_rejects_bad_settings(tmp_path, client, bad):
    song = _click_track(tmp_path)
    r = client.post(f"/api/music/songs/{song['id']}/dub/preview", json=bad)
    assert r.status_code in (400, 422), (bad, r.text)


def test_filter_graph_builds_drops_echo_and_special():
    p = dubplate.normalize_params({"echo": True, "echo_division": "1/2", "reverb": 0.5, "drops": [{"at": 8, "beats": 4}],
                                   "tempo_pct": 5, "pitch": 1, "eq_low": 4, "filter_mode": "highpass", "filter_hz": 200,
                                   "special_text": "Big up the sound", "special_placement": "both"}, 120.0, 100.0)
    graph, uses_special = dubplate.build_filter_graph(p, 3.0)
    assert uses_special
    for part in ("rubberband=tempo=1.0500", "highpass=f=200", "aecho=", "volume=enable='between(t,", "adelay=", "loudnorm", "[out]"):
        assert part in graph, part
    plain, no_special = dubplate.build_filter_graph(dubplate.normalize_params({}, 120.0, 100.0), None)
    assert not no_special and "[1:a]" not in plain and "rubberband" not in plain


def test_preview_and_final_render_produce_audio_and_a_library_song(tmp_path, client, monkeypatch):
    song = _click_track(tmp_path)

    def fake_speech(text, out_path, voice_id=None):
        t = np.arange(int(RATE * 1.5)) / RATE
        with wave.open(str(out_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes((0.3 * np.sin(2 * np.pi * 300 * t) * 32767).astype(np.int16).tobytes())

    monkeypatch.setattr(voice, "generate_speech", fake_speech)
    monkeypatch.setattr(voice, "voice_ready", lambda: True)
    body = {"start": 2, "end": 18, "tempo_pct": 4, "pitch": 0, "eq_low": 3, "echo": True, "echo_division": "1/4",
            "reverb": 0.3, "drops": [{"at": 8, "beats": 2}], "fade_out": 2, "special_text": "Dubplate for Tin Roof Sound",
            "special_placement": "both", "sound_name": "Tin Roof Sound"}
    pre = client.post(f"/api/music/songs/{song['id']}/dub/preview", json=body)
    assert pre.status_code == 200, pre.text
    audio = client.get(pre.json()["audio_url"])
    assert audio.status_code == 200 and len(audio.content) > 5000
    final = client.post(f"/api/music/songs/{song['id']}/dub/render", json=body)
    assert final.status_code == 201, final.text
    made = final.json()["songs"][0]
    assert made["provider"] == "dubplate" and made["parent_id"] == song["id"] and "Tin Roof Sound" in made["title"]
    expected = (18 - 2) / 1.04
    length = music_playback.audio_duration(music.audio_path(made["id"]))
    assert expected - 0.5 <= length <= expected + 3.5, "the cut plus the echo tail ringing out"
    assert made["duration_requested"] == length
    assert music.get_song(made["id"]) is not None
    assert made["id"] in [s["id"] for s in music.list_songs()]
    assert music.delete_song(made["id"]) is True
    assert not list((config.MUSIC_DIR).glob(f"{made['id']}*"))


def test_unknown_voice_is_refused(tmp_path, client, monkeypatch):
    song = _click_track(tmp_path)
    monkeypatch.setattr(voice, "voice_ready", lambda: True)
    r = client.post(f"/api/music/songs/{song['id']}/dub/preview",
                    json={"special_text": "hello", "special_placement": "intro", "special_voice": "../../etc/passwd"})
    assert r.status_code == 400 and "not installed" in r.json()["detail"]


def _tone_file(path, freqs, seconds=6.0):
    t = np.arange(int(RATE * seconds)) / RATE
    audio = sum(0.2 * np.sin(2 * np.pi * f * t) for f in freqs)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
        w.writeframes(np.repeat(pcm, 2).tobytes())
    return path


def test_key_estimate_follows_transposition():
    t = np.arange(dubplate.ANALYSIS_RATE * 8) / dubplate.ANALYSIS_RATE
    def chord(root_hz):
        return sum(np.sin(2 * np.pi * root_hz * r * t) for r in (1.0, 2 ** (4 / 12), 2 ** (7 / 12)))
    c_major = dubplate.estimate_key(chord(261.63).astype(np.float32))
    d_major = dubplate.estimate_key(chord(261.63 * 2 ** (2 / 12)).astype(np.float32))
    assert c_major == 0 and d_major == 2


@pytest.mark.parametrize("target,source,expected", [(100, 100, 1.0), (100, 50, 1.0), (90, 100, 0.9), (100, 190, 1.0526), (0, 100, 1.0), (100, 0, 1.0), (100, 40, 1.25), (100, 20, 1.0)])
def test_tempo_ratio_allows_half_and_double(target, source, expected):
    assert dubplate._closest_ratio(target, source) == pytest.approx(expected, abs=0.01)


def test_version_side_is_cut_from_the_instrumental_and_paired(tmp_path, client, monkeypatch):
    song = _click_track(tmp_path)
    music._meta_path(song["id"]).write_text(json.dumps({**song, "instrumental": False}), encoding="utf-8")
    song_dir = tmp_path / "fake-stems"
    song_dir.mkdir()
    instrumental = _tone_file(song_dir / "instrumental.wav", [110, 220], 20)
    seen = []
    def fake_stems(song_id, gpu_locked=False):
        seen.append(song_id)
        return {"vocals": instrumental, "instrumental": instrumental}
    monkeypatch.setattr(stems, "ensure_stems", fake_stems)
    r = client.post(f"/api/music/songs/{song['id']}/dub/render", json={"start": 2, "end": 12, "sides": "both", "sound_name": "Tin Roof"})
    assert r.status_code == 201, r.text
    vocal, version = r.json()["songs"]
    assert vocal["side"] == "vocal" and version["side"] == "version"
    assert vocal["pair_id"] == version["id"] and version["pair_id"] == vocal["id"]
    assert version["instrumental"] is True and version["lyrics"] == "" and version["title"].endswith("- Version")
    assert seen == [song["id"]], "only the version side needs the split, once"
    assert music_playback.audio_duration(music.audio_path(version["id"])) == pytest.approx(10, abs=1.5)
    # all or nothing: a failing second side leaves nothing behind
    before = {s["id"] for s in music.list_songs()}
    def boom(song_id, gpu_locked=False):
        raise music.MusicError("no splitter")
    monkeypatch.setattr(stems, "ensure_stems", boom)
    bad = client.post(f"/api/music/songs/{song['id']}/dub/render", json={"start": 2, "end": 12, "sides": "both"})
    assert bad.status_code == 400 and "no splitter" in bad.json()["detail"]
    assert {s["id"] for s in music.list_songs()} == before


def test_instrumental_songs_need_no_split_for_their_version(tmp_path, client, monkeypatch):
    song = _click_track(tmp_path)  # the synthetic track is flagged instrumental
    monkeypatch.setattr(stems, "ensure_stems", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not split")))
    r = client.post(f"/api/music/songs/{song['id']}/dub/preview?side=version", json={"start": 2, "end": 10})
    assert r.status_code == 200, r.text


def test_sung_special_needs_to_be_made_first(tmp_path, client):
    song = _click_track(tmp_path)
    r = client.post(f"/api/music/songs/{song['id']}/dub/preview",
                    json={"special_mode": "sung", "special_placement": "intro", "special_text": "big up"})
    assert r.status_code == 400 and "sung special" in r.json()["detail"]


def test_sung_special_is_fitted_to_the_riddim_and_mixed(tmp_path, client, monkeypatch):
    song = _click_track(tmp_path)
    special_id = "0123456789ab"
    ffmpeg = music_playback.find_ffmpeg_tool("ffmpeg")
    vocal = _tone_file(tmp_path / "vocals.wav", [392, 494, 587], 8)
    subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(vocal), str(music.audio_path(special_id))], check=True)
    music._meta_path(special_id).write_text(json.dumps({**song, "id": special_id, "title": "Special: Tin Roof", "instrumental": False}), encoding="utf-8")
    monkeypatch.setattr(stems, "ensure_stems", lambda sid, gpu_locked=False: {"vocals": vocal, "instrumental": vocal})
    body = {"start": 1, "end": 14, "special_mode": "sung", "special_song_id": special_id, "special_placement": "both",
            "special_text": "Tin Roof, this one is for you", "sound_name": "Tin Roof", "sides": "vocal"}
    r = client.post(f"/api/music/songs/{song['id']}/dub/render", json=body)
    assert r.status_code == 201, r.text
    made = r.json()["songs"][0]
    fit = made["dub"]["special_fit"]
    assert set(fit) == {"tempo_ratio", "key_shift"} and -6 <= fit["key_shift"] <= 6 and 0.7 <= fit["tempo_ratio"] <= 1.4
    assert music_playback.audio_duration(music.audio_path(made["id"])) > 10


def test_make_sung_special_queues_a_job_with_the_riddims_style(tmp_path, client, monkeypatch):
    song = _click_track(tmp_path)
    captured = {}
    monkeypatch.setattr(music, "create_job", lambda params: captured.update(params) or {"id": "job", "status": "queued"})
    r = client.post(f"/api/music/songs/{song['id']}/dub/special", json={"text": "Tin Roof Sound! This one is for you.", "sound_name": "Tin Roof"})
    assert r.status_code == 202
    assert "reggae" in captured["style"] and "dubplate special" in captured["style"]
    assert captured["lyrics"].startswith("[verse]\n") and "[chorus]" in captured["lyrics"]
    assert music.MIN_SECONDS <= captured["duration"] <= music.MAX_SECONDS and captured["title"] == "Special: Tin Roof"
    assert callable(captured["after_save"]) and captured["instrumental"] is False
    assert client.post(f"/api/music/songs/{song['id']}/dub/special", json={"text": ""}).status_code == 422
