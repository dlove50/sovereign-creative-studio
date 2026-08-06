import json
from types import SimpleNamespace

from app.routers import voice_cloning
from app.deps import ADMIN_ROLE


def test_profile_discovery_reports_active_and_configured(tmp_path, monkeypatch):
    root = tmp_path / "voice-app"
    profile = root / "voice_profiles" / "jarvis"
    profile.mkdir(parents=True)
    (profile / "reference.wav").write_bytes(b"RIFF")
    (profile / "reference.txt").write_text("Hello", encoding="utf-8")
    (profile / "metadata.json").write_text(json.dumps({
        "name": "JARVIS", "source_type": "synthetic"
    }), encoding="utf-8")
    (root / "voice_profiles" / "active.txt").write_text("jarvis", encoding="utf-8")
    monkeypatch.setenv("SOVEREIGN_VOICE_APP_ROOT", str(root))

    assert voice_cloning._profiles() == [{
        "slug": "jarvis", "name": "JARVIS", "source_type": "synthetic",
        "configured": True, "active": True,
    }]


def test_profile_root_is_configurable(tmp_path, monkeypatch):
    monkeypatch.setenv("SOVEREIGN_VOICE_APP_ROOT", str(tmp_path))
    assert voice_cloning._profiles_root() == tmp_path / "voice_profiles"


def test_clone_synthesis_uses_requested_profile_and_text(tmp_path, monkeypatch):
    root = tmp_path / "voice-app"
    profile = root / "voice_profiles" / "jarvis"
    profile.mkdir(parents=True)
    (profile / "reference.wav").write_bytes(b"RIFF")
    (profile / "reference.txt").write_text("Reference words", encoding="utf-8")
    monkeypatch.setenv("SOVEREIGN_VOICE_APP_ROOT", str(root))
    captured = {}

    class Reply:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self): return b"RIFF-cloned-output"

    def fake_open(request, timeout):
        captured.update(json.loads(request.data.decode("utf-8")))
        return Reply()

    monkeypatch.setattr(voice_cloning.urllib.request, "urlopen", fake_open)
    response = voice_cloning.synthesize_clone(
        voice_cloning.CloneSynthesisIn(profile="jarvis", text="Say exactly this"),
        SimpleNamespace(role=ADMIN_ROLE),
    )
    assert response.body == b"RIFF-cloned-output"
    assert captured == {"text": "Say exactly this", "profile": "jarvis"}


def test_video_container_is_accepted_for_audio_extraction():
    assert ".mp4" in voice_cloning._AUDIO_EXTS


def test_delete_active_profile_selects_remaining_profile(tmp_path, monkeypatch):
    root = tmp_path / "voice-app"
    profiles = root / "voice_profiles"
    for slug in ("optimus", "megatron"):
        folder = profiles / slug
        folder.mkdir(parents=True)
        (folder / "reference.wav").write_bytes(b"RIFF")
        (folder / "reference.txt").write_text("Exact words", encoding="utf-8")
    (profiles / "active.txt").write_text("optimus", encoding="utf-8")
    monkeypatch.setenv("SOVEREIGN_VOICE_APP_ROOT", str(root))

    response = voice_cloning.delete_profile("optimus", SimpleNamespace(role=ADMIN_ROLE))
    assert response.status_code == 204
    assert not (profiles / "optimus").exists()
    assert (profiles / "active.txt").read_text(encoding="utf-8") == "megatron"
