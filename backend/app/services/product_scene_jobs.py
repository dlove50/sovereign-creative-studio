"""In-process product-scene generation jobs."""
import asyncio
import logging
import queue
import threading
from datetime import datetime, timezone

from ..database import SessionLocal
from ..models import ProductAsset, ProductSceneGeneration
from ..product_scene_generators import get_product_scene_generator

_scene_queue: "queue.Queue[str | None]" = queue.Queue()
logger = logging.getLogger("sovereign.product_scene_jobs")

_worker_lock = threading.Lock()
_worker: threading.Thread | None = None


def enqueue_product_scene(scene_id: str) -> None:
    _ensure_worker()
    _scene_queue.put(scene_id)


def _ensure_worker() -> None:
    global _worker
    with _worker_lock:
        if _worker and _worker.is_alive():
            return
        _worker = threading.Thread(
            target=_worker_loop, name="product-scene-worker", daemon=True
        )
        _worker.start()


def _worker_loop() -> None:
    while True:
        scene_id = _scene_queue.get()
        if scene_id is None:
            _scene_queue.task_done()
            break
        try:
            _run_product_scene(scene_id)
        except Exception:  # noqa: BLE001 - one bad job must not kill the worker
            logger.exception("Unhandled error in product scene job %s", scene_id)
        finally:
            _scene_queue.task_done()


def _run_product_scene(scene_id: str) -> None:
    with SessionLocal() as db:
        scene = db.get(ProductSceneGeneration, scene_id)
        if scene is None or scene.status not in {"queued", "running"}:
            return

        asset = db.get(ProductAsset, scene.asset_id)
        if asset is None:
            scene.status = "failed"
            scene.error = "Product asset not found"
            scene.completed_at = datetime.now(timezone.utc)
            db.commit()
            return

        scene.status = "running"
        scene.error = None
        db.commit()
        db.refresh(scene)

        product_image_url = asset.processed_url or asset.original_url
        try:
            result = asyncio.run(
                get_product_scene_generator(
                    scene.mode, target_attribute=scene.target_attribute
                ).generate(
                    scene_id=scene.id,
                    prompt=scene.prompt,
                    preset=scene.preset,
                    product_image_url=product_image_url,
                    mask_image_url=asset.mask_url,
                    seg_prompt=scene.target_attribute,
                )
            )
        except Exception as exc:  # noqa: BLE001 - persist generation failure
            scene.status = "failed"
            scene.error = str(exc)
            scene.completed_at = datetime.now(timezone.utc)
            db.commit()
            return

        scene.status = "completed"
        scene.result_url = result.result_url
        scene.error = None
        scene.completed_at = datetime.now(timezone.utc)
        db.commit()
