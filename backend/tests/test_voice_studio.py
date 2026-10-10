"""Voice Studio (VibeVoice inside Sovereign): mapping, storage and validation, engine mocked."""
import wave

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.services import voice_studio


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    app_dir = tmp_path / "vibevoice-app"
    (app_dir / ".venv" / "Scripts").mkdir(parents=True)
    (app_dir / ".venv" / "Scripts" / "python.exe").write_text("", encoding="utf-8")
    (app_dir / "backend").mkdir()
    (app_dir / "backend" / "app.py").write_text("", encoding="utf-8")
    (app_dir / "outputs").mkdir()
    monkeypatch.setattr(config, "VIBEVOICE_APP_DIR", app_dir)
    monkeypatch.setattr(config, "STORAGE_DIR", tmp_path / "storage")
    voice_studio._pending.clear()
    yield app_dir


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _wav(path, seconds=1.0):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x00\x00" * int(24000 * seconds))


class FakeEngine:
    """Stands in for the VibeVoice service's HTTP API."""

    def __init__(self):
        self.calls = []
        self.job = {"id": "aaaaaaaaaaaa", "status": "queued", "error": None, "model": "VibeVoice-1.5B", "voices": ["en-Alice_woman"],
                    "audioSeconds": None, "elapsedSeconds": None, "createdAt": 1_700_000_000.0, "log": ["Queued"]}

    def json(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if path == "/api/status":
            return {"modelState": "ready", "loadedModel": "VibeVoice-1.5B", "queueDepth": 0}
        if path == "/api/jobs" and method == "GET":
            return {"jobs": []}
        if path == "/api/voices" and method == "GET":
            return {"voices": [{"name": "en-Alice_woman", "preset": True}, {"name": "David", "preset": False}]}
        if path == "/api/models":
            return {"models": [{"name": "VibeVoice-7B", "label": "7B", "note": "", "present": True},
                               {"name": "VibeVoice-1.5B", "label": "1.5B", "note": "", "present": True},
                               {"name": "VibeVoice-Missing", "label": "x", "note": "", "present": False}], "loaded": "VibeVoice-1.5B"}
        if path == "/api/generate":
            return {"id": "aaaaaaaaaaaa", "status": "queued"}
        if path.startswith("/api/jobs/") and method == "GET":
            return self.job
        if path.startswith("/api/jobs/") and path.endswith("/cancel"):
            if self.job["status"] != "queued":
                raise voice_studio.VoiceStudioError("Only queued renders can be cancelled.", 409)
            return self.job
        if path.startswith("/api/models/"):
            return {"switching": path.split("/")[3]}
        raise AssertionError(f"unexpected call {method} {path}")


@pytest.fixture
def engine(monkeypatch):
    fake = FakeEngine()
    monkeypatch.setattr(voice_studio, "_json", fake.json)
    monkeypatch.setattr(voice_studio, "is_online", lambda: True)
    return fake


def test_status_reports_offline_without_the_engine(isolated, monkeypatch):
    monkeypatch.setattr(voice_studio, "is_online", lambda: False)
    st = voice_studio.status()
    assert st["installed"] is True and st["online"] is False and st["ready"] is False and st["model"] is None


def test_status_reports_not_installed_when_the_app_is_missing(isolated, monkeypatch):
    monkeypatch.setattr(config, "VIBEVOICE_APP_DIR", isolated / "nowhere")
    assert voice_studio.status()["installed"] is False


def test_status_maps_the_engine_state(engine):
    st = voice_studio.status()
    assert st == {"installed": True, "online": True, "ready": True, "loading": None, "model": "VibeVoice-1.5B",
                  "kind": "full", "generating": False, "voices": 2}


def test_models_voices_and_model_switch(engine):
    models = voice_studio.models()
    assert [m["label"] for m in models["models"]] == ["VibeVoice-7B", "VibeVoice-1.5B"] and models["current"] == "VibeVoice-1.5B"
    voices = voice_studio.voices()
    assert voices["voices"][0] == {"name": "en-Alice_woman", "file": "en-Alice_woman.wav", "preset": True} and voices["realtime"] == []
    assert voice_studio.switch_model("VibeVoice-7B")["current"] == "VibeVoice-7B"
    with pytest.raises(voice_studio.VoiceStudioError):
        voice_studio.switch_model("../../evil")


def test_generate_maps_the_request_and_the_clip_is_kept(engine, isolated):
    out = voice_studio.generate("Speaker 1: Hi.\nSpeaker 2: Hello.", 2, ["en-Alice_woman", "David", "x y"], 1.5, 8, 7, True)
    assert out == {"id": "aaaaaaaaaaaa"}
    sent = next(c for c in engine.calls if c[1] == "/api/generate")[2]["json"]
    assert sent["voices"] == ["en-Alice_woman", "David"] and sent["cloneVoices"] is False and sent["cfgScale"] == 1.5
    running = voice_studio.job("aaaaaaaaaaaa")
    assert running["status"] == "running" and running["has_audio"] is False and "clip" not in running
    engine.job.update(status="done", audioSeconds=3.4, elapsedSeconds=6.1, log=["Queued", "Done"])
    _wav(isolated / "outputs" / "aaaaaaaaaaaa.wav", 3.4)
    done = voice_studio.job("aaaaaaaaaaaa")
    assert done["status"] == "done" and done["clip"]["script"].startswith("Speaker 1") and done["clip"]["seed"] == 7
    assert done["clip"]["speakers"] == ["en-Alice_woman", "David"]
    assert voice_studio.clip_audio_path("aaaaaaaaaaaa").is_file()
    assert [c["id"] for c in voice_studio.clips()] == ["aaaaaaaaaaaa"]
    assert voice_studio.clips()[0]["audio_url"] == "/api/voice-studio/clips/aaaaaaaaaaaa/audio"


def test_generate_rejects_empty_script_and_unsafe_voice_names(engine):
    with pytest.raises(voice_studio.VoiceStudioError):
        voice_studio.generate("   ", 1, ["en-Alice_woman"], 1.3, 5, 1, False)
    with pytest.raises(voice_studio.VoiceStudioError):
        voice_studio.generate("Speaker 1: Hi.", 1, ["../etc/passwd"], 1.3, 5, 1, False)


def test_job_states_map_to_the_studio_vocabulary(engine):
    for engine_state, expected in (("queued", "running"), ("running", "running"), ("failed", "error"), ("cancelled", "stopped")):
        engine.job["status"] = engine_state
        engine.job["error"] = "boom" if engine_state == "failed" else None
        assert voice_studio.job("aaaaaaaaaaaa")["status"] == expected


def test_earlier_standalone_renders_are_imported_once_and_deleting_sticks(engine, isolated):
    _wav(isolated / "outputs" / "bbbbbbbbbbbb.wav", 2.0)
    first = voice_studio.clips()
    assert [c["id"] for c in first] == ["bbbbbbbbbbbb"] and first[0]["duration_seconds"] == 2.0
    assert voice_studio.delete_clip("bbbbbbbbbbbb") is True
    assert voice_studio.clips() == [], "a deleted clip must not be re-imported from the standalone app's folder"
    assert (isolated / "outputs" / "bbbbbbbbbbbb.wav").exists(), "the standalone app's own files are left alone"


def test_stopping_a_started_render_explains_why_it_cannot(engine):
    engine.job["status"] = "running"
    with pytest.raises(voice_studio.VoiceStudioError, match="cannot be interrupted"):
        voice_studio.stop_job("aaaaaaaaaaaa")
    engine.job["status"] = "queued"
    assert voice_studio.stop_job("aaaaaaaaaaaa") == {"stopping": True}


def test_chunks_are_empty_for_the_full_models(engine):
    out = voice_studio.chunks("aaaaaaaaaaaa", 0)
    assert out["chunks"] == [] and out["sample_rate"] == 24000 and out["next"] == 0


def test_api_routes_explain_missing_realtime_and_reject_bad_ids(client, engine):
    r = client.post("/api/voice-studio/realtime", json={"text": "hello", "voice": "en-Alice_woman"})
    assert r.status_code == 409 and "Realtime" in r.json()["detail"]
    assert client.get("/api/voice-studio/jobs/not-an-id").status_code == 404
    assert client.get("/api/voice-studio/clips/zzzzzzzzzzzz/audio").status_code == 404
    assert client.get("/api/voice-studio/voices/..%2F..%2Fx/audio").status_code in (404, 422)
    assert client.post("/api/voice-studio/generate", json={"script": "", "speakers": []}).status_code == 422


# --- helpers the rest of Sovereign uses (voice list, voice cloning, songs freeing the card) ---------

def _voices(app_dir):
    (app_dir / "voices" / "custom").mkdir(parents=True)
    _wav(app_dir / "voices" / "en-Alice_woman.wav")
    _wav(app_dir / "voices" / "custom" / "david.wav")


def test_voice_names_and_files_come_from_the_app_folders_while_the_engine_sleeps(isolated):
    _voices(isolated)
    assert voice_studio.list_voice_names() == [("en-Alice_woman", True), ("david", False)]
    assert voice_studio.voice_file("david") == isolated / "voices" / "custom" / "david.wav"
    assert voice_studio.voice_file("en-Alice_woman") == isolated / "voices" / "en-Alice_woman.wav"
    assert voice_studio.voice_file("nobody") is None


def test_voice_helpers_are_empty_when_the_app_is_missing(isolated, monkeypatch):
    monkeypatch.setattr(config, "VIBEVOICE_APP_DIR", isolated / "nowhere")
    assert voice_studio.list_voice_names() == []
    assert voice_studio.voice_file("david") is None


def test_removing_a_clone_moves_it_aside_and_presets_stay(isolated):
    _voices(isolated)
    assert voice_studio.remove_voice_file("david") is True
    assert (isolated / "voices" / "custom" / "_removed" / "david.wav").is_file()
    assert voice_studio.voice_file("david") is None
    assert voice_studio.remove_voice_file("en-Alice_woman") is False
    assert voice_studio.remove_voice_file("nobody") is False


def test_adding_a_clone_converts_into_the_custom_folder_and_refuses_duplicates(isolated, tmp_path, monkeypatch):
    _voices(isolated)
    sample = tmp_path / "sample.mp3"
    sample.write_bytes(b"x")
    commands = []

    def fake_run(cmd, **_kw):
        commands.append(cmd)
        _wav(cmd[-1])

    monkeypatch.setattr(voice_studio.subprocess, "run", fake_run)
    assert voice_studio.add_voice_file("Grandma Rose!", sample) == "Grandma-Rose"
    assert (isolated / "voices" / "custom" / "Grandma-Rose.wav").is_file()
    assert commands[0][0] == "ffmpeg" and "24000" in commands[0]
    with pytest.raises(voice_studio.VoiceStudioError):
        voice_studio.add_voice_file("david", sample)
    with pytest.raises(voice_studio.VoiceStudioError):
        voice_studio.add_voice_file("!!!", sample)


def test_ensure_ready_starts_the_engine_and_waits_for_the_model(monkeypatch):
    states = iter([{"online": False, "ready": False}, {"online": True, "ready": False}, {"online": True, "ready": True}])
    started = []
    monkeypatch.setattr(voice_studio, "status", lambda: next(states))
    monkeypatch.setattr(voice_studio, "start", lambda model=None: started.append(model) or {})
    monkeypatch.setattr(voice_studio.time, "sleep", lambda _s: None)
    voice_studio.ensure_ready()
    assert started == [None]


def test_ensure_ready_gives_up_with_a_clear_error(monkeypatch):
    monkeypatch.setattr(voice_studio, "status", lambda: {"online": True, "ready": False})
    monkeypatch.setattr(voice_studio.time, "sleep", lambda _s: None)
    with pytest.raises(voice_studio.VoiceStudioError, match="did not finish loading"):
        voice_studio.ensure_ready(timeout=0)


def test_stop_if_running_only_stops_a_live_engine(monkeypatch):
    stopped = []
    monkeypatch.setattr(voice_studio, "stop", lambda: stopped.append(True) or {"stopped": True})
    monkeypatch.setattr(voice_studio, "is_online", lambda: False)
    voice_studio.stop_if_running()
    assert stopped == []
    monkeypatch.setattr(voice_studio, "is_online", lambda: True)
    voice_studio.stop_if_running()
    assert stopped == [True]
