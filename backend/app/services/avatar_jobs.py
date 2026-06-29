"""Avatar/voice job orchestration + credit charging.

Charge-on-success only: setup-required and failed jobs never cost credits. In
Phase 16A no local talking-avatar model is wired, so greeting jobs resolve to
`setup_required` (no charge, no faked output). The charge helpers exist so that
when a provider is wired later, billing is already correct and tested.
"""
from __future__ import annotations

import asyncio
import queue
import re
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..database import SessionLocal
from ..models import AvatarAsset, AvatarJob, CreditTransaction, User, VoiceAsset
from . import avatar as avatar_provider
from . import avatar_comfyui
from .avatar_presets import resolve_preset
from .transcription import resolve_storage_url


def _now() -> datetime:
    return datetime.now(timezone.utc)


_PATH_RE = re.compile(r"[A-Za-z]:\\[^\s\"']+|/[^\s\"']*/[^\s\"']+")


def _scrub_paths(message: str) -> str:
    """Keep error messages user-safe: strip absolute local paths so failures never
    leak the machine's directory layout."""
    return _PATH_RE.sub("<path>", message or "").strip() or "Avatar generation failed."


def _charge(db: Session, user: User, amount: int, *, feature: str, related_id: str, provider: str, reason: str) -> None:
    user.credits -= amount
    db.add(
        CreditTransaction(
            user_id=user.id,
            amount=-amount,
            reason=reason,
            transaction_type="generation_charge",
            related_feature=feature,
            related_id=related_id,
            status="completed",
            note=f"{reason} via {provider}",
            balance_after=user.credits,
            generation_id=None,
        )
    )


def charge_for_avatar_job(db: Session, user: User, job: AvatarJob) -> None:
    """Charge for a completed avatar video (call only on real success). Idempotent:
    a second completion will not double-charge."""
    already = db.scalar(
        select(CreditTransaction).where(
            CreditTransaction.related_id == job.id,
            CreditTransaction.transaction_type == "generation_charge",
        )
    )
    if already is not None:
        return
    job.credits_cost = config.CREDITS_PER_AVATAR_VIDEO
    _charge(
        db, user, config.CREDITS_PER_AVATAR_VIDEO,
        feature="avatar_video", related_id=job.id,
        provider=f"{job.provider}:{config.AVATAR_WAN_MODEL_NAME or 'wan'}", reason="avatar video",
    )


def charge_for_voice(db: Session, user: User, *, related_id: str, provider: str) -> None:
    """Charge for a successful local voice generation."""
    _charge(
        db, user, config.CREDITS_PER_VOICE_GENERATION,
        feature="voice_generation", related_id=related_id, provider=provider, reason="voice generation",
    )


def create_greeting_job(
    db: Session,
    user: User,
    *,
    avatar_id: str | None,
    voice_id: str | None,
    script_text: str | None,
) -> AvatarJob:
    text = (script_text or config.GREETING_TEXT).strip()
    readiness = avatar_provider.avatar_readiness()
    job = AvatarJob(
        user_id=user.id,
        avatar_id=avatar_id,
        voice_id=voice_id,
        job_type="avatar_greeting",
        script_text=text,
        provider=readiness["backend"],
        status="setup_required",
        credits_cost=0,
    )
    # Phase 16A: never fake a talking-avatar output. Whether or not a provider is
    # detected, generation is not wired yet, so the job is setup_required and is
    # not charged. (Real generation + charge_for_avatar_job arrive in Phase 16B.)
    if readiness["ready"]:
        job.error_message = "Avatar provider detected; generation wiring arrives in Phase 16B."
    else:
        job.error_message = readiness["detail"]
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


# --- talking-avatar job (Phase 16C) ------------------------------------------
_avatar_queue: "queue.Queue[str | None]" = queue.Queue()
_worker_lock = threading.Lock()
_worker: threading.Thread | None = None


def enqueue_avatar_video(job_id: str) -> None:
    _ensure_worker()
    _avatar_queue.put(job_id)


def _ensure_worker() -> None:
    global _worker
    with _worker_lock:
        if _worker and _worker.is_alive():
            return
        _worker = threading.Thread(target=_worker_loop, name="avatar-worker", daemon=True)
        _worker.start()


def _worker_loop() -> None:
    while True:
        job_id = _avatar_queue.get()
        if job_id is None:
            _avatar_queue.task_done()
            break
        try:
            _run_avatar_video(job_id)
        finally:
            _avatar_queue.task_done()


def _run_avatar_video(job_id: str) -> None:
    with SessionLocal() as db:
        job = db.get(AvatarJob, job_id)
        if job is None or job.status not in {"queued", "running"}:
            return
        job.status = "running"
        job.error_message = None
        started = time.perf_counter()
        db.commit()

        try:
            avatar = db.get(AvatarAsset, job.avatar_id) if job.avatar_id else None
            voice = db.get(VoiceAsset, job.voice_id) if job.voice_id else None
            if avatar is None or not avatar.source_file_path:
                raise RuntimeError("Avatar image is missing")
            if voice is None or not voice.sample_file_path:
                raise RuntimeError("Voice audio is missing")
            image_path = resolve_storage_url(avatar.source_file_path)
            audio_path = resolve_storage_url(voice.sample_file_path)
            out_path = avatar_comfyui.new_output_path()
            preset = resolve_preset(job.avatar_preset)
            job.avatar_preset = preset.id
            job.avatar_width = preset.width
            job.avatar_height = preset.height
            job.avatar_frames = preset.frames
            job.avatar_steps = preset.steps
            job.avatar_cfg = preset.cfg
            db.commit()
            asyncio.run(
                avatar_comfyui.generate_talking_avatar(image_path, audio_path, job.script_text or "", out_path, preset)
            )
        except Exception as exc:  # noqa: BLE001 - persist failure, never charge.
            job.status = "failed"
            job.error_message = _scrub_paths(str(exc))
            job.avatar_runtime_seconds = round(time.perf_counter() - started, 2)
            job.completed_at = _now()
            db.commit()
            return

        job.status = "completed"
        job.output_video_path = f"/storage/avatar_videos/{out_path.name}"
        job.avatar_runtime_seconds = round(time.perf_counter() - started, 2)
        job.completed_at = _now()
        user = db.get(User, job.user_id)
        if user is not None:
            charge_for_avatar_job(db, user, job)
        db.commit()
