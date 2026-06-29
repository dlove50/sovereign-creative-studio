"""In-process copy generation jobs (same lightweight worker pattern as the
generation and product-scene workers)."""
import asyncio
import queue
import threading
from datetime import datetime, timezone

from ..copy_generators import get_copy_generator
from ..database import SessionLocal
from ..models import CopyGeneration, ProductAsset, ProductSceneGeneration

_copy_queue: "queue.Queue[str | None]" = queue.Queue()
_worker_lock = threading.Lock()
_worker: threading.Thread | None = None


def enqueue_copy(copy_id: str) -> None:
    _ensure_worker()
    _copy_queue.put(copy_id)


def _ensure_worker() -> None:
    global _worker
    with _worker_lock:
        if _worker and _worker.is_alive():
            return
        _worker = threading.Thread(target=_worker_loop, name="copy-worker", daemon=True)
        _worker.start()


def _worker_loop() -> None:
    while True:
        copy_id = _copy_queue.get()
        if copy_id is None:
            _copy_queue.task_done()
            break
        try:
            _run_copy(copy_id)
        finally:
            _copy_queue.task_done()


def _build_product_context(db, copy: CopyGeneration) -> str | None:
    parts: list[str] = []
    if copy.product_asset_id:
        asset = db.get(ProductAsset, copy.product_asset_id)
        if asset is not None:
            parts.append(f"Product image: {asset.filename}")
    if copy.product_scene_id:
        scene = db.get(ProductSceneGeneration, copy.product_scene_id)
        if scene is not None:
            parts.append(f"Ad scene: {scene.prompt}")
    return "; ".join(parts) or None


def _run_copy(copy_id: str) -> None:
    with SessionLocal() as db:
        copy = db.get(CopyGeneration, copy_id)
        if copy is None or copy.status not in {"queued", "running"}:
            return

        copy.status = "running"
        copy.error = None
        db.commit()
        db.refresh(copy)

        product_context = _build_product_context(db, copy)
        try:
            result = asyncio.run(
                get_copy_generator().generate(
                    copy_id=copy.id,
                    copy_type=copy.copy_type,
                    tone=copy.tone,
                    audience=copy.audience,
                    prompt=copy.prompt,
                    product_context=product_context,
                )
            )
        except Exception as exc:  # noqa: BLE001 - persist generation failure
            copy.status = "failed"
            copy.error = str(exc)
            copy.completed_at = datetime.now(timezone.utc)
            db.commit()
            return

        copy.status = "completed"
        copy.result_text = result.result_text
        copy.error = None
        copy.completed_at = datetime.now(timezone.utc)
        db.commit()
