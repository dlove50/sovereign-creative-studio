"""Local video transcription jobs.

The real adapter is faster-whisper, but this install may not have ffmpeg or the
Python packages yet. In that case jobs fail with a clear local dependency error.
Tests use the mock adapter so CI stays offline and fast.
"""
from __future__ import annotations

import importlib.util
import logging
import queue
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import (
    CREDITS_PER_TRANSCRIPTION,
    CREDITS_PER_TRANSCRIPTION_SUMMARY,
    FFMPEG_PATH,
    STORAGE_DIR,
    TRANSCRIPTION_BACKEND,
    TRANSCRIPTION_COMPUTE_TYPE,
    TRANSCRIPTION_DEVICE,
    TRANSCRIPTION_MODEL_DIR,
    TRANSCRIPTION_MODEL_NAME,
)
from ..copy_generators import get_copy_generator
from ..database import SessionLocal
from ..models import CreditTransaction, TranscriptionJob, User


@dataclass
class TranscriptionResult:
    transcript_text: str
    detected_language: str | None = None
    duration_seconds: float | None = None


class MockTranscriptionAdapter:
    def transcribe(self, *, source_path: Path, model_name: str) -> TranscriptionResult:
        return TranscriptionResult(
            transcript_text=f"Mock local transcript for {source_path.name}.",
            detected_language="en",
            duration_seconds=3.0,
        )


class FasterWhisperAdapter:
    def transcribe(self, *, source_path: Path, model_name: str) -> TranscriptionResult:
        ffmpeg_path = _ffmpeg_path()
        if ffmpeg_path is None:
            raise RuntimeError(
                "Local transcription requires ffmpeg on PATH. Install ffmpeg and retry."
            )
        if importlib.util.find_spec("faster_whisper") is None:
            raise RuntimeError(
                "Local transcription requires faster-whisper. Install it in the backend venv and retry."
            )
        from faster_whisper import WhisperModel  # type: ignore

        TRANSCRIPTION_MODEL_DIR.mkdir(parents=True, exist_ok=True)
        model = WhisperModel(
            model_name,
            device=TRANSCRIPTION_DEVICE,
            compute_type=TRANSCRIPTION_COMPUTE_TYPE,
            download_root=str(TRANSCRIPTION_MODEL_DIR),
        )
        try:
            segments, info = model.transcribe(str(source_path), beam_size=1)
            # faster-whisper decodes audio lazily while iterating segments; a video
            # with no audio stream raises a low-level decode error here.
            parts = [segment.text.strip() for segment in segments if segment.text.strip()]
        except RuntimeError:
            raise
        except Exception as exc:  # noqa: BLE001 - opaque decode errors -> clear message
            raise RuntimeError(
                "This video has no audio. Transcription requires audio."
            ) from exc
        if not parts:
            raise RuntimeError(
                "This video has no audio. Transcription requires audio."
            )
        return TranscriptionResult(
            transcript_text="\n".join(parts).strip(),
            detected_language=getattr(info, "language", None),
            duration_seconds=getattr(info, "duration", None),
        )


def get_transcription_adapter():
    if TRANSCRIPTION_BACKEND == "mock":
        return MockTranscriptionAdapter()
    return FasterWhisperAdapter()


def transcription_readiness() -> dict[str, object]:
    ffmpeg_path = _ffmpeg_path()
    faster_whisper_available = importlib.util.find_spec("faster_whisper") is not None
    real_backend = TRANSCRIPTION_BACKEND != "mock"
    available = (not real_backend) or (bool(ffmpeg_path) and faster_whisper_available)
    missing: list[str] = []
    if real_backend and not ffmpeg_path:
        missing.append("ffmpeg")
    if real_backend and not faster_whisper_available:
        missing.append("faster-whisper")
    return {
        "backend": TRANSCRIPTION_BACKEND,
        "available": available,
        "ffmpeg_available": bool(ffmpeg_path),
        "ffmpeg_path": ffmpeg_path,
        "faster_whisper_available": faster_whisper_available,
        "model_name": TRANSCRIPTION_MODEL_NAME,
        "model_dir": str(TRANSCRIPTION_MODEL_DIR),
        "device": TRANSCRIPTION_DEVICE,
        "compute_type": TRANSCRIPTION_COMPUTE_TYPE,
        "missing": missing,
        "message": (
            "Transcription is using the mock fallback."
            if TRANSCRIPTION_BACKEND == "mock"
            else (
                "Real local transcription is ready."
                if available
                else "ffmpeg and faster-whisper are required for real local transcription."
            )
        ),
    }


def _ffmpeg_path() -> str | None:
    if FFMPEG_PATH:
        configured = Path(FFMPEG_PATH)
        try:
            if configured.is_file():
                return str(configured)
        except OSError:
            # WinGet package directories can be inaccessible to sandboxed tools
            # even though the real local launcher can execute the binary. If an
            # admin explicitly configured ffmpeg.exe, keep the readiness check
            # non-crashing and let the runtime attempt surface any real issue.
            if configured.name.lower() == "ffmpeg.exe":
                return str(configured)
        if configured.name.lower() == "ffmpeg.exe":
            return str(configured)
    return shutil.which("ffmpeg")


_queue: "queue.Queue[str | None]" = queue.Queue()
logger = logging.getLogger("sovereign.transcription")

_worker_lock = threading.Lock()
_worker: threading.Thread | None = None


def enqueue_transcription(job_id: str) -> None:
    _ensure_worker()
    _queue.put(job_id)


def _ensure_worker() -> None:
    global _worker
    with _worker_lock:
        if _worker and _worker.is_alive():
            return
        _worker = threading.Thread(
            target=_worker_loop, name="transcription-worker", daemon=True
        )
        _worker.start()


def _worker_loop() -> None:
    while True:
        job_id = _queue.get()
        if job_id is None:
            _queue.task_done()
            break
        try:
            _run(job_id)
        except Exception:  # noqa: BLE001 - one bad job must not kill the worker
            logger.exception("Unhandled error in transcription job %s", job_id)
        finally:
            _queue.task_done()


def _run(job_id: str) -> None:
    with SessionLocal() as db:
        job = db.get(TranscriptionJob, job_id)
        if job is None or job.status not in {"queued", "running"}:
            return
        job.status = "running"
        job.error_message = None
        db.commit()
        db.refresh(job)

        try:
            source = resolve_storage_url(job.source_video_url)
            result = get_transcription_adapter().transcribe(
                source_path=source, model_name=job.model_name
            )
        except Exception as exc:  # noqa: BLE001 - safe persisted failure
            db.refresh(job)
            if job.status == "cancelled":
                return
            job.status = "failed"
            job.error_message = str(exc)[:500]
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
            return

        db.refresh(job)
        if job.status == "cancelled":
            return
        job.status = "completed"
        job.transcript_text = result.transcript_text
        job.detected_language = result.detected_language
        job.duration_seconds = result.duration_seconds
        job.error_message = None
        job.completed_at = datetime.now(timezone.utc)
        _charge(db, job)
        db.commit()


def _charge(db: Session, job: TranscriptionJob) -> None:
    already = db.scalar(
        select(CreditTransaction).where(
            CreditTransaction.related_id == job.id,
            CreditTransaction.transaction_type == "generation_charge",
            CreditTransaction.related_feature == "video_transcription",
        )
    )
    if already is not None:
        return
    user = db.get(User, job.user_id)
    if user is None:
        return
    cost = job.credits_cost if job.credits_cost is not None else CREDITS_PER_TRANSCRIPTION
    user.credits -= cost
    db.add(
        CreditTransaction(
            user_id=user.id,
            amount=-cost,
            reason="video transcription",
            transaction_type="generation_charge",
            related_feature="video_transcription",
            related_id=job.id,
            status="completed",
            note=f"Video transcription completed (provider={job.provider}, model={job.model_name}).",
            balance_after=user.credits,
            generation_id=None,
        )
    )


def resolve_storage_url(file_url: str) -> Path:
    prefix = "/storage/"
    if not file_url.startswith(prefix):
        raise RuntimeError("Transcription source must be a local /storage video.")
    relative = file_url[len(prefix):]
    candidate = (STORAGE_DIR / relative).resolve()
    try:
        candidate.relative_to(STORAGE_DIR.resolve())
    except ValueError as exc:
        raise RuntimeError("Invalid transcription source path.") from exc
    if not candidate.is_file():
        raise RuntimeError("Transcription source video was not found.")
    return candidate


async def summarize_transcript(job: TranscriptionJob, summary_type: str) -> str:
    if not job.transcript_text:
        raise RuntimeError("Transcript is not available yet.")
    prompt = (
        "Summarize this video transcript for a private local creator studio.\n"
        f"Summary type: {summary_type.replace('_', ' ')}.\n\n"
        f"Transcript:\n{job.transcript_text[:12000]}"
    )
    result = await get_copy_generator().generate(
        copy_id=job.id,
        prompt=prompt,
        copy_type="summary",
        tone="clear",
        audience="creator",
    )
    return result.result_text


def charge_summary(db: Session, job: TranscriptionJob) -> None:
    already = db.scalar(
        select(CreditTransaction).where(
            CreditTransaction.related_id == job.id,
            CreditTransaction.transaction_type == "generation_charge",
            CreditTransaction.related_feature == "video_transcription_summary",
        )
    )
    if already is not None:
        return
    user = db.get(User, job.user_id)
    if user is None:
        return
    user.credits -= CREDITS_PER_TRANSCRIPTION_SUMMARY
    db.add(
        CreditTransaction(
            user_id=user.id,
            amount=-CREDITS_PER_TRANSCRIPTION_SUMMARY,
            reason="video transcript summary",
            transaction_type="generation_charge",
            related_feature="video_transcription_summary",
            related_id=job.id,
            status="completed",
            note="Video transcript summary generated.",
            balance_after=user.credits,
            generation_id=None,
        )
    )


def default_model_name() -> str:
    return TRANSCRIPTION_MODEL_NAME
