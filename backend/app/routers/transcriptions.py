import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import (
    CREDITS_PER_TRANSCRIPTION,
    CREDITS_PER_TRANSCRIPTION_SUMMARY,
    STORAGE_DIR,
    TRANSCRIPTION_BACKEND,
    TRANSCRIPTION_MAX_UPLOAD_MB,
)
from ..database import get_db
from ..deps import get_current_user
from ..models import Project, TranscriptionJob, User
from ..schemas import TranscriptionOut, TranscriptionSummaryIn
from ..services.transcription import (
    charge_summary,
    default_model_name,
    enqueue_transcription,
    resolve_storage_url,
    summarize_transcript,
)

router = APIRouter(prefix="/api/transcriptions", tags=["transcriptions"])

_ALLOWED_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}


@router.get("", response_model=list[TranscriptionOut])
def list_transcriptions(
    project_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(TranscriptionJob).where(TranscriptionJob.user_id == user.id)
    if project_id:
        stmt = stmt.where(TranscriptionJob.project_id == project_id)
    stmt = stmt.order_by(TranscriptionJob.created_at.desc())
    return db.scalars(stmt).all()


@router.get("/{job_id}", response_model=TranscriptionOut)
def get_transcription(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.get(TranscriptionJob, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transcription not found")
    return job


@router.post("", response_model=TranscriptionOut, status_code=201)
def create_transcription(
    project_id: str | None = Form(default=None),
    source_video_url: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if file is not None and source_video_url:
        raise HTTPException(
            status_code=400,
            detail="Provide either an uploaded video or an existing source URL, not both",
        )
    if file is None and not source_video_url:
        raise HTTPException(
            status_code=400,
            detail="Provide an uploaded video or an existing local /storage video URL",
        )
    if project_id:
        project = db.get(Project, project_id)
        if project is None or project.user_id != user.id:
            raise HTTPException(status_code=404, detail="Project not found")

    _ensure_credit_available(db, user)

    if file is not None:
        source_url, filename = _store_upload(file)
    else:
        source_url = (source_video_url or "").strip()
        _validate_source_url(source_url)
        filename = Path(source_url).name

    job = TranscriptionJob(
        user_id=user.id,
        project_id=project_id,
        source_video_url=source_url,
        source_filename=filename,
        status="queued",
        provider="mock" if TRANSCRIPTION_BACKEND == "mock" else "local_whisper",
        model_name=default_model_name(),
        credits_cost=CREDITS_PER_TRANSCRIPTION,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    enqueue_transcription(job.id)
    return job


@router.post("/{job_id}/summarize", response_model=TranscriptionOut)
async def summarize_transcription(
    job_id: str,
    payload: TranscriptionSummaryIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.get(TranscriptionJob, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transcription not found")
    if job.status != "completed" or not job.transcript_text:
        raise HTTPException(
            status_code=409, detail="Transcript must be completed before summary"
        )
    if user.credits < CREDITS_PER_TRANSCRIPTION_SUMMARY:
        raise HTTPException(status_code=402, detail="Insufficient credits")
    try:
        job.summary_text = await summarize_transcript(job, payload.summary_type)
    except Exception as exc:  # noqa: BLE001 - summarize is optional/dependency-backed.
        raise HTTPException(
            status_code=409,
            detail=f"Summary unavailable from the configured local copy provider: {exc}",
        ) from exc
    charge_summary(db, job)
    db.commit()
    db.refresh(job)
    return job


@router.get("/{job_id}/download")
def download_transcription(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.get(TranscriptionJob, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transcription not found")
    if job.status != "completed" or not job.transcript_text:
        raise HTTPException(status_code=404, detail="Transcript text not available")
    text = job.transcript_text
    if job.summary_text:
        text += f"\n\nSummary:\n{job.summary_text}"
    return PlainTextResponse(
        text,
        headers={
            "Content-Disposition": f'attachment; filename="transcript-{job.id}.txt"'
        },
    )


def _ensure_credit_available(db: Session, user: User) -> None:
    reserved = db.scalar(
        select(func.coalesce(func.sum(TranscriptionJob.credits_cost), 0)).where(
            TranscriptionJob.user_id == user.id,
            TranscriptionJob.status.in_(["queued", "running"]),
        )
    )
    if user.credits - int(reserved or 0) < CREDITS_PER_TRANSCRIPTION:
        raise HTTPException(status_code=402, detail="Insufficient credits")


def _store_upload(file: UploadFile) -> tuple[str, str]:
    original_name = Path(file.filename or "video.mp4").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Upload must be a video file")
    upload_dir = STORAGE_DIR / "transcriptions" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    destination = upload_dir / stored_name
    max_bytes = TRANSCRIPTION_MAX_UPLOAD_MB * 1024 * 1024
    total = 0
    with destination.open("wb") as out:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                out.close()
                destination.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"Video upload exceeds {TRANSCRIPTION_MAX_UPLOAD_MB} MB",
                )
            out.write(chunk)
    if total == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded video is empty")
    return f"/storage/transcriptions/uploads/{stored_name}", original_name


def _validate_source_url(source_url: str) -> None:
    suffix = Path(source_url).suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Source must be a video file")
    try:
        resolve_storage_url(source_url)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
