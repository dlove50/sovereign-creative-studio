"""Avatar & Voice foundation (Phase 16A).

Users manage their own avatar/voice assets and greeting jobs; admins can list all
with ?scope=all. No talking-avatar model is wired yet, so greeting jobs resolve to
setup_required (never charged, never faked). Local-first: no cloud provider is
required for this foundation.
"""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..database import get_db
from ..deps import ADMIN_ROLE, get_current_user
from ..models import AvatarAsset, AvatarJob, User, VoiceAsset
from ..schemas import (
    AvatarAssetOut,
    AvatarJobOut,
    AvatarVoiceReadinessOut,
    GreetingJobIn,
    ProviderReadinessOut,
    VoiceAssetOut,
    VoiceCreateIn,
)
from ..services import avatar as avatar_provider
from ..services import avatar_presets
from ..services import avatar_jobs, voice as voice_provider
from ..services.transcription import resolve_storage_url

router = APIRouter(prefix="/api", tags=["avatars"])

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
_VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}
_CONSENT_NOTE = "Only use images/videos you have the rights to. Outputs are AI-generated."


def _is_admin_all(user: User, scope: str | None) -> bool:
    return scope == "all" and user.role == ADMIN_ROLE


def _store_avatar_upload(file: UploadFile, allowed: set[str], kind: str) -> tuple[str, str]:
    original = Path(file.filename or f"source{next(iter(allowed))}").name
    suffix = Path(original).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail=f"Upload must be a {kind} file ({', '.join(sorted(allowed))})")
    out_dir = config.STORAGE_DIR / "avatars" / "uploads"
    out_dir.mkdir(parents=True, exist_ok=True)
    stored = f"{uuid.uuid4().hex}{suffix}"  # uuid name => no path traversal
    dest = out_dir / stored
    max_bytes = config.AVATAR_MAX_UPLOAD_MB * 1024 * 1024
    total = 0
    with dest.open("wb") as out:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"Upload exceeds {config.AVATAR_MAX_UPLOAD_MB} MB")
            out.write(chunk)
    if total == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    return f"/storage/avatars/uploads/{stored}", original


def _create_avatar(db, user, *, avatar_type, allowed, kind, name, file, source_url):
    if file is not None and source_url:
        raise HTTPException(status_code=400, detail="Provide either an upload or an existing source, not both")
    if file is not None:
        stored_url, original = _store_avatar_upload(file, allowed, kind)
    elif source_url:
        suffix = Path(source_url).suffix.lower()
        if suffix not in allowed:
            raise HTTPException(status_code=400, detail=f"Source must be a {kind} file")
        try:
            resolve_storage_url(source_url)  # path-traversal-safe
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        stored_url, original = source_url, Path(source_url).name
    else:
        raise HTTPException(status_code=400, detail=f"Provide a {kind} upload or an existing /storage source")
    asset = AvatarAsset(
        user_id=user.id,
        name=(name or original).strip()[:160],
        avatar_type=avatar_type,
        source_file_path=stored_url,
        thumbnail_path=stored_url if avatar_type == "photo_avatar" else None,
        status="ready",
        provider="local",
        notes=_CONSENT_NOTE,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


# --- avatars -----------------------------------------------------------------
@router.get("/avatars", response_model=list[AvatarAssetOut])
def list_avatars(scope: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(AvatarAsset).where(AvatarAsset.deleted_at.is_(None))
    if not _is_admin_all(user, scope):
        stmt = stmt.where(AvatarAsset.user_id == user.id)
    return db.scalars(stmt.order_by(AvatarAsset.created_at.desc())).all()


@router.post("/avatars/photo", response_model=AvatarAssetOut, status_code=201)
def create_photo_avatar(
    name: str | None = Form(default=None),
    source_url: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _create_avatar(db, user, avatar_type="photo_avatar", allowed=_IMAGE_EXTS, kind="image", name=name, file=file, source_url=source_url)


@router.post("/avatars/video", response_model=AvatarAssetOut, status_code=201)
def create_video_avatar(
    name: str | None = Form(default=None),
    source_url: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _create_avatar(db, user, avatar_type="video_avatar", allowed=_VIDEO_EXTS, kind="video", name=name, file=file, source_url=source_url)


# --- voices ------------------------------------------------------------------
@router.get("/voices", response_model=list[VoiceAssetOut])
def list_voices(scope: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(VoiceAsset).where(VoiceAsset.deleted_at.is_(None))
    if not _is_admin_all(user, scope):
        stmt = stmt.where(VoiceAsset.user_id == user.id)
    return db.scalars(stmt.order_by(VoiceAsset.created_at.desc())).all()


@router.post("/voices", response_model=VoiceAssetOut, status_code=201)
def create_voice(payload: VoiceCreateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.voice_type == "preset":
        provider, status = "placeholder", "ready"
    elif payload.voice_type == "local_tts":
        ready = voice_provider.voice_ready()
        provider, status = ("piper" if config.VOICE_BACKEND == "piper" else "placeholder"), ("ready" if ready else "setup_required")
    else:  # uploaded_sample — voice cloning deferred (consent required) in this phase
        provider, status = "placeholder", "setup_required"
    voice = VoiceAsset(user_id=user.id, name=payload.name.strip()[:160], voice_type=payload.voice_type, provider=provider, status=status)
    db.add(voice)
    db.commit()
    db.refresh(voice)
    return voice


@router.post("/voices/greeting", response_model=VoiceAssetOut, status_code=201)
def generate_voice_greeting(payload: GreetingJobIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Generate the preset greeting as real local audio (Piper). Charged only on
    success; setup-required reports 409 and charges nothing; no faked audio."""
    text = (payload.script_text or config.GREETING_TEXT).strip()
    readiness = voice_provider.voice_readiness()
    if not readiness["ready"]:
        raise HTTPException(status_code=409, detail=readiness["detail"])
    if user.credits < config.CREDITS_PER_VOICE_GENERATION:
        raise HTTPException(status_code=402, detail="Insufficient credits")

    out_name = f"{uuid.uuid4().hex}.wav"
    out_path = config.STORAGE_DIR / "voices" / out_name
    try:
        voice_provider.generate_speech(text, out_path)
    except Exception as exc:  # noqa: BLE001 - never charge on failure.
        raise HTTPException(status_code=502, detail=f"Voice generation failed: {exc}") from exc

    voice = VoiceAsset(
        user_id=user.id,
        name="Voice greeting",
        voice_type="local_tts",
        provider="piper",
        sample_file_path=f"/storage/voices/{out_name}",
        status="ready",
    )
    db.add(voice)
    db.flush()  # need voice.id for the ledger related_id
    avatar_jobs.charge_for_voice(db, user, related_id=voice.id, provider=f"piper:{voice_provider.model_label()}")
    db.commit()
    db.refresh(voice)
    return voice


# --- avatar jobs -------------------------------------------------------------
@router.post("/avatar-jobs/greeting", response_model=AvatarJobOut, status_code=201)
def create_greeting(payload: GreetingJobIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    for asset_id, model in ((payload.avatar_id, AvatarAsset), (payload.voice_id, VoiceAsset)):
        if asset_id:
            owned = db.get(model, asset_id)
            if owned is None or (owned.user_id != user.id and user.role != ADMIN_ROLE):
                raise HTTPException(status_code=404, detail="Referenced asset not found")
    return avatar_jobs.create_greeting_job(
        db, user, avatar_id=payload.avatar_id, voice_id=payload.voice_id, script_text=payload.script_text
    )


@router.post("/avatar-jobs/talking", response_model=AvatarJobOut, status_code=201)
def create_talking_avatar(payload: GreetingJobIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Create a talking-avatar video from a photo avatar + generated voice audio.
    Charged only on a successful MP4; setup-required charges nothing and is queued
    only when the avatar backend is fully ready."""
    avatar = db.get(AvatarAsset, payload.avatar_id) if payload.avatar_id else None
    if avatar is None or (avatar.user_id != user.id and user.role != ADMIN_ROLE):
        raise HTTPException(status_code=404, detail="Avatar not found")
    voice = db.get(VoiceAsset, payload.voice_id) if payload.voice_id else None
    if voice is None or (voice.user_id != user.id and user.role != ADMIN_ROLE):
        raise HTTPException(status_code=404, detail="Voice not found")
    if not voice.sample_file_path:
        raise HTTPException(status_code=400, detail="Selected voice has no generated audio yet")

    text = (payload.script_text or config.GREETING_TEXT).strip()
    readiness = avatar_provider.avatar_readiness()
    preset = avatar_presets.resolve_preset(payload.avatar_preset)
    job = AvatarJob(
        user_id=user.id,
        avatar_id=avatar.id,
        voice_id=voice.id,
        job_type="avatar_talking",
        script_text=text,
        provider=readiness["backend"],
        avatar_preset=preset.id,
        avatar_width=preset.width,
        avatar_height=preset.height,
        avatar_frames=preset.frames,
        avatar_steps=preset.steps,
        avatar_cfg=preset.cfg,
        credits_cost=0,
    )
    if not readiness["ready"]:
        job.status = "setup_required"
        job.error_message = readiness["detail"]
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    if user.credits < config.CREDITS_PER_AVATAR_VIDEO:
        raise HTTPException(status_code=402, detail="Insufficient credits")
    job.status = "queued"
    db.add(job)
    db.commit()
    db.refresh(job)
    avatar_jobs.enqueue_avatar_video(job.id)
    return job


@router.get("/avatar-jobs", response_model=list[AvatarJobOut])
def list_avatar_jobs(scope: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(AvatarJob).where(AvatarJob.deleted_at.is_(None))
    if not _is_admin_all(user, scope):
        stmt = stmt.where(AvatarJob.user_id == user.id)
    return db.scalars(stmt.order_by(AvatarJob.created_at.desc())).all()


@router.get("/avatar-jobs/{job_id}", response_model=AvatarJobOut)
def get_avatar_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = db.get(AvatarJob, job_id)
    if job is None or (job.user_id != user.id and user.role != ADMIN_ROLE):
        raise HTTPException(status_code=404, detail="Avatar job not found")
    return job


# --- readiness (drives the /avatars UI badges) -------------------------------
@router.get("/avatars/readiness", response_model=AvatarVoiceReadinessOut)
def avatar_voice_readiness():
    return AvatarVoiceReadinessOut(
        avatar=ProviderReadinessOut(**avatar_provider.avatar_readiness()),
        voice=ProviderReadinessOut(**voice_provider.voice_readiness()),
        greeting_text=config.GREETING_TEXT,
        avatar_enabled=config.AVATAR_ENABLED,
        voice_enabled=config.VOICE_ENABLED,
        credits_per_avatar_video=config.CREDITS_PER_AVATAR_VIDEO,
        credits_per_voice_generation=config.CREDITS_PER_VOICE_GENERATION,
        default_avatar_preset=avatar_presets.default_preset_id(),
        avatar_presets=avatar_presets.public_presets(),
    )
