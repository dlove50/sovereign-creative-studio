"""In-process video generation jobs (same lightweight worker pattern as the
other generators)."""
import asyncio
import inspect
import queue
import threading
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import STORAGE_DIR
from ..database import SessionLocal
from ..models import CreditTransaction, User, VideoGeneration
from ..video_generators import get_video_generator
from .gpu_jobs import GPU_JOB_LOCK

_video_queue: "queue.Queue[str | None]" = queue.Queue()
_worker_lock = threading.Lock()
_worker: threading.Thread | None = None


def enqueue_video(video_id: str) -> None:
    _ensure_worker()
    _video_queue.put(video_id)


def _ensure_worker() -> None:
    global _worker
    with _worker_lock:
        if _worker and _worker.is_alive():
            return
        _worker = threading.Thread(target=_worker_loop, name="video-worker", daemon=True)
        _worker.start()


def _worker_loop() -> None:
    while True:
        video_id = _video_queue.get()
        if video_id is None:
            _video_queue.task_done()
            break
        try:
            with GPU_JOB_LOCK:
                _run_video(video_id)
        finally:
            _video_queue.task_done()


def _run_video(video_id: str) -> None:
    with SessionLocal() as db:
        video = db.get(VideoGeneration, video_id)
        if video is None or video.status not in {"queued", "running"}:
            return

        video.status = "running"
        video.error = None
        db.commit()
        db.refresh(video)

        try:
            generator = get_video_generator(video.provider)
            kwargs = {
                "video_id": video.id,
                "source_image_url": video.source_image_url,
                "prompt": video.prompt,
                "motion_preset": video.motion_preset,
                "duration_seconds": video.duration_seconds,
                "mode": video.mode,
            }
            if "quality_preset" in inspect.signature(generator.generate).parameters:
                kwargs["quality_preset"] = video.quality_preset
            result = asyncio.run(
                generator.generate(**kwargs)
            )
        except Exception as exc:  # noqa: BLE001 - persist generation failure
            db.refresh(video)
            if video.status == "cancelled":
                return
            video.status = "failed"
            video.error = str(exc)
            video.completed_at = datetime.now(timezone.utc)
            db.commit()
            return

        db.refresh(video)
        if video.status == "cancelled":
            return
        video.status = "completed"
        video.result_url = result.result_url
        video.provider_task_id = result.provider_task_id
        video.error = None
        video.completed_at = datetime.now(timezone.utc)
        if result.result_url:
            rel = result.result_url.lstrip("/").removeprefix("storage/")
            file_path = STORAGE_DIR / rel
            if file_path.is_file():
                video.file_size_bytes = file_path.stat().st_size
        _charge_for_video(db, video)
        db.commit()


def _charge_for_video(db: Session, video: VideoGeneration) -> None:
    """Charge the flat video credit cost on success (charge-on-completion, same
    as the image path). Failed jobs never reach here, so they are never charged.
    Idempotent: a second completion would not double-charge."""
    already = db.scalar(
        select(CreditTransaction).where(
            CreditTransaction.related_id == video.id,
            CreditTransaction.transaction_type == "generation_charge",
        )
    )
    if already is not None:
        return
    user = db.get(User, video.user_id)
    if user is None:
        return
    cost = video.credits_cost or 10
    related_feature = "video_seedance" if video.provider == "seedance_api" else "video"
    user.credits -= cost
    db.add(
        CreditTransaction(
            user_id=user.id,
            amount=-cost,
            reason="video generation",
            transaction_type="generation_charge",
            related_feature=related_feature,
            related_id=video.id,
            status="completed",
            note=f"Video generation ({video.mode}, provider={video.provider}) completed successfully.",
            balance_after=user.credits,
            generation_id=None,
        )
    )
