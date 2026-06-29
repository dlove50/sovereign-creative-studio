import os
import tempfile
import time

_TMP = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(_TMP, 'test.db')}")
os.environ.setdefault("STORAGE_DIR", os.path.join(_TMP, "storage"))
os.environ.setdefault("TRANSCRIPTION_BACKEND", "mock")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.config import STORAGE_DIR  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import CreditTransaction, TranscriptionJob, User  # noqa: E402
from app.services import transcription as transcription_service  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _fund_user():
    with SessionLocal() as db:
        for user in db.query(User).all():
            user.credits = 100000
        db.commit()


def _wait(client, job_id, status="completed", timeout=5.0):
    deadline = time.time() + timeout
    latest = None
    while time.time() < deadline:
        latest = client.get(f"/api/transcriptions/{job_id}").json()
        if latest["status"] == status:
            return latest
        time.sleep(0.05)
    raise AssertionError(f"Transcription {job_id} did not reach {status}: {latest}")


def _project(client, name="Transcript Project"):
    return client.post(
        "/api/projects", json={"name": name, "description": None}
    ).json()["id"]


def test_upload_video_transcription_completes_charges_and_downloads(client):
    project_id = _project(client)
    resp = client.post(
        "/api/transcriptions",
        data={"project_id": project_id},
        files={"file": ("clip.mp4", b"fake mp4 bytes", "video/mp4")},
    )
    assert resp.status_code == 201
    created = resp.json()
    assert created["status"] == "queued"
    assert created["source_video_url"].startswith("/storage/transcriptions/uploads/")

    done = _wait(client, created["id"])
    assert done["status"] == "completed"
    assert "Mock local transcript" in done["transcript_text"]
    assert done["credits_cost"] == 5

    download = client.get(f"/api/transcriptions/{created['id']}/download")
    assert download.status_code == 200
    assert "text/plain" in download.headers["content-type"]
    assert "Mock local transcript" in download.text

    with SessionLocal() as db:
        tx = db.scalar(
            select(CreditTransaction).where(
                CreditTransaction.related_id == created["id"],
                CreditTransaction.related_feature == "video_transcription",
            )
        )
        assert tx is not None
        assert tx.amount == -5


def test_existing_storage_video_can_be_transcribed_and_appears_in_library(client):
    video_dir = STORAGE_DIR / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)
    (video_dir / "library-source.mp4").write_bytes(b"mp4")

    resp = client.post(
        "/api/transcriptions",
        data={"source_video_url": "/storage/videos/library-source.mp4"},
    )
    assert resp.status_code == 201
    done = _wait(client, resp.json()["id"])

    library = client.get("/api/library").json()
    transcript_items = [item for item in library if item["type"] == "transcript"]
    assert any(item["source_entity_id"] == done["id"] for item in transcript_items)

    admin_jobs = client.get("/api/admin/jobs?feature=transcription").json()
    assert any(job["id"] == done["id"] for job in admin_jobs["jobs"])


def test_unsupported_upload_extension_is_rejected(client):
    resp = client.post(
        "/api/transcriptions",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400
    assert "video file" in resp.json()["detail"]


def test_source_path_traversal_is_rejected(client):
    resp = client.post(
        "/api/transcriptions",
        data={"source_video_url": "/storage/../sovereign.db.mp4"},
    )
    assert resp.status_code == 400


def test_insufficient_credits_blocks_before_processing(client):
    with SessionLocal() as db:
        user = db.query(User).order_by(User.created_at).first()
        user.credits = 0
        db.commit()

    resp = client.post(
        "/api/transcriptions",
        files={"file": ("clip.mp4", b"fake mp4 bytes", "video/mp4")},
    )
    assert resp.status_code == 402


def test_failed_transcription_does_not_charge(client, monkeypatch):
    class BrokenAdapter:
        def transcribe(self, *, source_path, model_name):
            raise RuntimeError("offline local transcription dependency")

    monkeypatch.setattr(
        transcription_service, "get_transcription_adapter", lambda: BrokenAdapter()
    )
    resp = client.post(
        "/api/transcriptions",
        files={"file": ("broken.mp4", b"fake mp4 bytes", "video/mp4")},
    )
    assert resp.status_code == 201
    failed = _wait(client, resp.json()["id"], status="failed")
    assert "offline local transcription dependency" in failed["error_message"]

    with SessionLocal() as db:
        tx = db.scalar(
            select(CreditTransaction).where(
                CreditTransaction.related_id == failed["id"],
                CreditTransaction.related_feature == "video_transcription",
            )
        )
        assert tx is None


def test_silent_video_fails_with_no_audio_message_and_no_charge(client, monkeypatch):
    """A video with no audio stream must fail cleanly and never charge credits."""

    class SilentVideoAdapter:
        def transcribe(self, *, source_path, model_name):
            raise RuntimeError("This video has no audio. Transcription requires audio.")

    monkeypatch.setattr(
        transcription_service, "get_transcription_adapter", lambda: SilentVideoAdapter()
    )
    resp = client.post(
        "/api/transcriptions",
        files={"file": ("silent.mp4", b"fake silent mp4 bytes", "video/mp4")},
    )
    assert resp.status_code == 201

    failed = _wait(client, resp.json()["id"], status="failed")
    assert failed["status"] == "failed"
    assert "no audio" in failed["error_message"].lower()
    assert "Transcription requires audio" in failed["error_message"]
    assert failed["transcript_text"] is None

    with SessionLocal() as db:
        tx = db.scalar(
            select(CreditTransaction).where(
                CreditTransaction.related_id == failed["id"],
                CreditTransaction.related_feature == "video_transcription",
            )
        )
        assert tx is None, "No credits should be charged for a failed silent-video transcription"


def test_summary_updates_job_and_charges_summary(client):
    resp = client.post(
        "/api/transcriptions",
        files={"file": ("summary.mp4", b"fake mp4 bytes", "video/mp4")},
    )
    assert resp.status_code == 201
    done = _wait(client, resp.json()["id"])

    summary_resp = client.post(
        f"/api/transcriptions/{done['id']}/summarize",
        json={"summary_type": "bullet_summary"},
    )
    assert summary_resp.status_code == 200
    body = summary_resp.json()
    assert body["summary_text"]

    with SessionLocal() as db:
        tx = db.scalar(
            select(CreditTransaction).where(
                CreditTransaction.related_id == done["id"],
                CreditTransaction.related_feature == "video_transcription_summary",
            )
        )
        assert tx is not None
        assert tx.amount == -2


def test_user_isolation_for_transcription_jobs(client):
    first = client.post(
        "/api/admin/family-users",
        json={"display_name": "Transcript A", "initial_credits": 100},
    ).json()
    second = client.post(
        "/api/admin/family-users",
        json={"display_name": "Transcript B", "initial_credits": 100},
    ).json()

    created = client.post(
        "/api/transcriptions",
        headers={"X-SCS-Family-User-Id": first["id"]},
        files={"file": ("owned.mp4", b"fake mp4 bytes", "video/mp4")},
    ).json()

    hidden = client.get(
        f"/api/transcriptions/{created['id']}",
        headers={"X-SCS-Family-User-Id": second["id"]},
    )
    assert hidden.status_code == 404
