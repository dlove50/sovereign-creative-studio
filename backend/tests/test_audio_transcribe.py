"""Tests for POST /api/audio/transcribe (Whisper Flow prompt input).

No credits are charged and no DB record is created — these tests
verify the soft-error contract and format rejection only.
"""
import os
import tempfile

_TMP = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(_TMP, 'test.db')}")
os.environ.setdefault("STORAGE_DIR", os.path.join(_TMP, "storage"))
os.environ.setdefault("TRANSCRIPTION_BACKEND", "mock")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_valid_webm_returns_transcript(client):
    resp = client.post(
        "/api/audio/transcribe",
        files={"file": ("voice.webm", b"fake webm bytes", "audio/webm")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert "Mock local transcript" in body["text"]
    assert isinstance(body["duration_seconds"], float)


def test_valid_wav_returns_transcript(client):
    resp = client.post(
        "/api/audio/transcribe",
        files={"file": ("voice.wav", b"fake wav bytes", "audio/wav")},
    )
    assert resp.status_code == 200
    assert resp.json()["error"] is None


def test_valid_mp3_returns_transcript(client):
    resp = client.post(
        "/api/audio/transcribe",
        files={"file": ("voice.mp3", b"fake mp3 bytes", "audio/mpeg")},
    )
    assert resp.status_code == 200
    assert resp.json()["error"] is None


def test_unsupported_extension_rejected(client):
    resp = client.post(
        "/api/audio/transcribe",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400
    assert "Unsupported" in resp.json()["detail"]


def test_empty_file_rejected(client):
    resp = client.post(
        "/api/audio/transcribe",
        files={"file": ("empty.webm", b"", "audio/webm")},
    )
    assert resp.status_code == 400
    assert "Empty" in resp.json()["detail"]


def test_oversized_file_rejected(client):
    big_data = b"x" * (10 * 1024 * 1024 + 1)  # 10 MB + 1 byte
    resp = client.post(
        "/api/audio/transcribe",
        files={"file": ("big.webm", big_data, "audio/webm")},
    )
    assert resp.status_code == 413


def test_broken_adapter_returns_soft_error(client, monkeypatch):
    """When the transcription backend fails, return soft error instead of 500."""
    from app.routers import audio_transcribe as audio_router

    class BrokenAdapter:
        def transcribe(self, *, source_path, model_name):
            raise RuntimeError("faster-whisper not installed")

    monkeypatch.setattr(audio_router, "get_transcription_adapter", lambda: BrokenAdapter())
    resp = client.post(
        "/api/audio/transcribe",
        files={"file": ("voice.webm", b"fake webm", "audio/webm")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["text"] == ""
    assert "faster-whisper not installed" in body["error"]


def test_no_db_record_created(client):
    """Audio transcription for prompt input must never create a TranscriptionJob."""
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models import TranscriptionJob

    with SessionLocal() as db:
        before = db.scalar(select(TranscriptionJob).limit(1))

    client.post(
        "/api/audio/transcribe",
        files={"file": ("voice.webm", b"fake audio", "audio/webm")},
    )

    with SessionLocal() as db:
        after_count = db.query(TranscriptionJob).count()

    before_count = 0 if before is None else 1
    # Count should be unchanged (no new job created)
    assert after_count == before_count
