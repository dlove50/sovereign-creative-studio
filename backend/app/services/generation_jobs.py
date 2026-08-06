"""In-process generation job runner.

This is intentionally lightweight for Phase 3. Jobs are queued in memory and
processed by one daemon worker thread, while durable status/result data stays in
SQLite so the existing API can poll generations by id.
"""
import asyncio
import queue
import threading

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import CREDITS_PER_GENERATION
from ..database import SessionLocal
from ..generators import get_generator
from ..models import CreditTransaction, Generation, User

_job_queue: "queue.Queue[str | None]" = queue.Queue()
_worker_lock = threading.Lock()
_worker: threading.Thread | None = None


def enqueue_generation(generation_id: str) -> None:
    _ensure_worker()
    _job_queue.put(generation_id)


def _ensure_worker() -> None:
    global _worker
    with _worker_lock:
        if _worker and _worker.is_alive():
            return
        _worker = threading.Thread(
            target=_worker_loop, name="generation-worker", daemon=True
        )
        _worker.start()


def _worker_loop() -> None:
    while True:
        generation_id = _job_queue.get()
        if generation_id is None:
            _job_queue.task_done()
            break
        try:
            _run_generation_job(generation_id)
        finally:
            _job_queue.task_done()


def _run_generation_job(generation_id: str) -> None:
    with SessionLocal() as db:
        gen = db.get(Generation, generation_id)
        if gen is None or gen.status not in {"queued", "running"}:
            return

        gen.status = "running"
        gen.error = None
        db.commit()
        db.refresh(gen)

        try:
            result = asyncio.run(
                get_generator(gen.provider, quality_preset=gen.provider_model).generate(
                    generation_id=gen.id,
                    prompt=gen.prompt,
                    media_type=gen.media_type,
                    mode="image_edit" if gen.source_image_url else "text_to_image",
                    source_image_url=gen.source_image_url,
                )
            )
        except Exception as exc:  # noqa: BLE001 - persist backend failure details
            db.refresh(gen)
            if gen.status == "cancelled":
                return
            gen.status = "failed"
            gen.error = str(exc)
            db.commit()
            return

        db.refresh(gen)
        if gen.status == "cancelled":
            return
        _complete_generation(db, gen, result.file_url)


def _complete_generation(db: Session, gen: Generation, file_url: str) -> None:
    user = db.get(User, gen.user_id)
    if user is None:
        gen.status = "failed"
        gen.error = "Generation owner not found"
        db.commit()
        return

    gen.status = "completed"
    gen.file_url = file_url
    gen.error = None

    already = db.scalar(
        select(CreditTransaction).where(
            CreditTransaction.related_id == gen.id,
            CreditTransaction.transaction_type == "generation_charge",
        )
    )
    if already is None:
        cost = gen.credits_cost or CREDITS_PER_GENERATION
        gen.credits_cost = cost
        user.credits -= cost
        related_feature = (
            "image_openai" if gen.provider == "openai_image_api" else "base_generation"
        )
        db.add(
            CreditTransaction(
                user_id=user.id,
                amount=-cost,
                reason="generation",
                transaction_type="generation_charge",
                related_feature=related_feature,
                related_id=gen.id,
                status="completed",
                note=(
                    "Image generation completed successfully "
                    f"(provider={gen.provider}, model={gen.provider_model or 'local'})."
                ),
                balance_after=user.credits,
                generation_id=gen.id,
            )
        )

    db.commit()
