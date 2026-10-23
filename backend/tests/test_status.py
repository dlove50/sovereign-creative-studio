"""Status endpoint + startup-check tests."""
import os
import tempfile

_TMP = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(_TMP, 'test.db')}")
os.environ.setdefault("STORAGE_DIR", os.path.join(_TMP, "storage"))
os.environ.setdefault("GENERATOR_BACKEND", "mock")
os.environ.setdefault("PRODUCT_SCENE_BACKEND", "mock")
os.environ.setdefault("COPY_BACKEND", "mock")
os.environ.setdefault("VIDEO_BACKEND", "mock")
os.environ.setdefault("TRANSCRIPTION_BACKEND", "mock")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.routers.status as status_router  # noqa: E402
import app.startup as startup  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _secrets_outside_the_public_mount(tmp_path, monkeypatch):
    """Point SECRETS_DIR outside STORAGE_DIR for the tests in this file.

    SECRETS_DIR defaults to STORAGE_DIR/secrets, and STORAGE_DIR is mounted at
    /storage, so the default layout serves the session signing key and the
    provider API keys over HTTP. run_startup_checks() reports that, which is
    correct and which would otherwise make every "no warnings" assertion here
    fail for a reason that has nothing to do with what it is testing.

    test_startup_warns_when_secrets_are_inside_the_public_mount covers the
    default layout deliberately.
    """
    from app import config
    from app.services import backups

    safe = tmp_path / "private" / "secrets"
    safe.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "SECRETS_DIR", safe)
    # Backups default to STORAGE_DIR/backups and are served the same way, with
    # the database inside them. Same reasoning as the secrets folder above.
    safe_backups = tmp_path / "private" / "backups"
    safe_backups.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(backups, "BACKUP_DIR", safe_backups)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_status_endpoint_reports_config(client):
    resp = client.get("/api/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["generator_backend"] == "mock"
    assert body["product_scene_backend"] == "mock"
    assert body["product_scene_model"]
    assert body["product_scene_mode"]
    assert body["copy_backend"] == "mock"
    assert body["video_backend"] == "mock"
    assert body["video_engine"]
    assert body["transcription_backend"]
    assert "transcription_available" in body
    assert "transcription_ffmpeg_available" in body
    assert "transcription_faster_whisper_available" in body
    assert body["comfyui_configured"] is False
    assert body["openai_configured"] is False
    assert body["storage_writable"] is True
    assert body["comfyui_base_url"]
    assert body["storage_path"]


def test_status_reports_comfyui_video_mode_reachability(client, monkeypatch):
    class _FakeResponse:
        def raise_for_status(self):
            return None

    def _fake_get(url, timeout):
        assert url.endswith("/system_stats")
        assert timeout == 2.0
        return _FakeResponse()

    monkeypatch.setattr(status_router, "VIDEO_BACKEND", "comfyui")
    monkeypatch.setattr(status_router, "GENERATOR_BACKEND", "mock")
    monkeypatch.setattr(status_router, "PRODUCT_SCENE_BACKEND", "mock")
    monkeypatch.setattr(status_router.httpx, "get", _fake_get)

    resp = client.get("/api/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["video_backend"] == "comfyui"
    assert body["comfyui_configured"] is True
    assert body["comfyui_reachable"] is True
    assert body["comfyui_error"] is None


def test_status_reports_transcription_readiness(client, monkeypatch):
    monkeypatch.setattr(
        status_router,
        "transcription_readiness",
        lambda: {
            "backend": "local_whisper",
            "available": False,
            "ffmpeg_available": False,
            "faster_whisper_available": True,
            "model_name": "base",
            "model_dir": "models/whisper",
            "device": "cpu",
            "compute_type": "int8",
            "message": "ffmpeg is required for real local transcription.",
        },
    )

    resp = client.get("/api/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["transcription_backend"] == "local_whisper"
    assert body["transcription_available"] is False
    assert body["transcription_ffmpeg_available"] is False
    assert body["transcription_faster_whisper_available"] is True
    assert body["transcription_model_name"] == "base"


def test_status_can_report_local_ltx_default(client, monkeypatch):
    monkeypatch.setattr(status_router, "VIDEO_BACKEND", "comfyui")
    monkeypatch.setattr(status_router.config, "COMFYUI_VIDEO_ENGINE", "ltx")
    monkeypatch.setattr(status_router, "GENERATOR_BACKEND", "mock")
    monkeypatch.setattr(status_router, "PRODUCT_SCENE_BACKEND", "mock")

    class _FakeResponse:
        def raise_for_status(self):
            return None

    monkeypatch.setattr(status_router.httpx, "get", lambda *_args, **_kwargs: _FakeResponse())

    body = client.get("/api/status").json()
    assert body["video_backend"] == "comfyui"
    assert body["video_engine"] == "ltx"


def test_startup_warns_when_openai_key_missing(monkeypatch):
    monkeypatch.setattr(startup, "COPY_BACKEND", "openai")
    monkeypatch.setattr(startup, "OPENAI_API_KEY", "")
    warnings = startup.run_startup_checks()
    assert any("OPENAI_API_KEY" in w for w in warnings)


def test_startup_warns_on_unknown_backend(monkeypatch):
    monkeypatch.setattr(startup, "GENERATOR_BACKEND", "banana")
    warnings = startup.run_startup_checks()
    assert any("GENERATOR_BACKEND" in w for w in warnings)


def test_startup_warns_on_unknown_video_backend(monkeypatch):
    monkeypatch.setattr(startup, "VIDEO_BACKEND", "banana")
    warnings = startup.run_startup_checks()
    assert any("VIDEO_BACKEND" in w for w in warnings)


def test_startup_warns_when_real_transcription_dependencies_missing(monkeypatch):
    monkeypatch.setattr(startup, "TRANSCRIPTION_BACKEND", "local_whisper")
    monkeypatch.setattr(
        startup,
        "transcription_readiness",
        lambda: {"available": False},
    )
    warnings = startup.run_startup_checks()
    assert any("ffmpeg" in w and "faster-whisper" in w for w in warnings)


def test_startup_allows_mock_transcription_without_dependency_warning(monkeypatch):
    monkeypatch.setattr(startup, "TRANSCRIPTION_BACKEND", "mock")
    monkeypatch.setattr(startup, "COPY_BACKEND", "mock")
    monkeypatch.setattr(startup, "GENERATOR_BACKEND", "mock")
    monkeypatch.setattr(startup, "PRODUCT_SCENE_BACKEND", "mock")
    monkeypatch.setattr(startup, "VIDEO_BACKEND", "mock")
    assert startup.run_startup_checks() == []


def test_startup_clean_with_defaults(monkeypatch):
    monkeypatch.setattr(startup, "COPY_BACKEND", "mock")
    monkeypatch.setattr(startup, "GENERATOR_BACKEND", "mock")
    monkeypatch.setattr(startup, "PRODUCT_SCENE_BACKEND", "mock")
    monkeypatch.setattr(startup, "VIDEO_BACKEND", "mock")
    assert startup.run_startup_checks() == []


def test_startup_warns_when_secrets_are_inside_the_public_mount(monkeypatch, tmp_path):
    """The shipped default. GET /storage/secrets/session_secret returns the key
    that signs every session cookie; integrations.json returns the API keys.
    Verified by request against the running app before this test existed."""
    from app import config

    storage = tmp_path / "storage"
    secrets = storage / "secrets"
    secrets.mkdir(parents=True)
    monkeypatch.setattr(config, "STORAGE_DIR", storage)
    monkeypatch.setattr(config, "SECRETS_DIR", secrets)
    for name in ("COPY_BACKEND", "GENERATOR_BACKEND", "PRODUCT_SCENE_BACKEND",
                 "VIDEO_BACKEND", "TRANSCRIPTION_BACKEND"):
        monkeypatch.setattr(startup, name, "mock")

    warnings = startup.run_startup_checks()
    assert any("/storage" in w and "session_secret" in w for w in warnings), (
        f"the default secrets layout was not reported: {warnings}")


def test_startup_warns_when_backups_are_inside_the_public_mount(monkeypatch, tmp_path):
    """A backup zip holds the database. Its name is a timestamp, not a UUID, so
    it can be guessed rather than having to leak. amd-sync's PublicStorage does
    not block this folder, so merging that branch does not fix it."""
    from app import config
    from app.services import backups

    storage = tmp_path / "storage"
    backup_dir = storage / "backups"
    backup_dir.mkdir(parents=True)
    monkeypatch.setattr(config, "STORAGE_DIR", storage)
    monkeypatch.setattr(backups, "BACKUP_DIR", backup_dir)
    for name in ("COPY_BACKEND", "GENERATOR_BACKEND", "PRODUCT_SCENE_BACKEND",
                 "VIDEO_BACKEND", "TRANSCRIPTION_BACKEND"):
        monkeypatch.setattr(startup, name, "mock")

    warnings = startup.run_startup_checks()
    assert any("backups" in w and "password hash" in w for w in warnings), (
        f"the default backup layout was not reported: {warnings}")
