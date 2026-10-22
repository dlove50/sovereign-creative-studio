"""In-process product asset processing jobs."""
import logging
import queue
import threading
from pathlib import Path

from ..background_removal import get_background_removal_adapter
from ..config import STORAGE_DIR
from ..database import SessionLocal
from ..models import ProductAsset

_asset_queue: "queue.Queue[str | None]" = queue.Queue()
logger = logging.getLogger("sovereign.asset_jobs")

_worker_lock = threading.Lock()
_worker: threading.Thread | None = None


def enqueue_background_removal(asset_id: str) -> None:
    _ensure_worker()
    _asset_queue.put(asset_id)


def _ensure_worker() -> None:
    global _worker
    with _worker_lock:
        if _worker and _worker.is_alive():
            return
        _worker = threading.Thread(
            target=_worker_loop, name="asset-processing-worker", daemon=True
        )
        _worker.start()


def _worker_loop() -> None:
    while True:
        asset_id = _asset_queue.get()
        if asset_id is None:
            _asset_queue.task_done()
            break
        try:
            _run_background_removal(asset_id)
        except Exception:  # noqa: BLE001 - one bad job must not kill the worker
            logger.exception("Unhandled error in asset processing job %s", asset_id)
        finally:
            _asset_queue.task_done()


def _run_background_removal(asset_id: str) -> None:
    with SessionLocal() as db:
        asset = db.get(ProductAsset, asset_id)
        if asset is None or asset.status not in {"uploaded", "processing"}:
            return

        asset.status = "processing"
        asset.error = None
        db.commit()
        db.refresh(asset)

        try:
            original_path = _storage_path_from_url(asset.original_url)
            suffix = Path(asset.filename).suffix or ".png"
            processed_path = STORAGE_DIR / "processed" / f"{asset.id}{suffix}"
            result = get_background_removal_adapter().remove_background(
                asset_id=asset.id,
                original_path=original_path,
                output_path=processed_path,
            )
        except Exception as exc:  # noqa: BLE001 - persist processing failure
            asset.status = "failed"
            asset.error = str(exc)
            db.commit()
            return

        asset.status = "completed"
        asset.processed_url = _url_from_storage_path(result.processed_path)
        asset.error = None
        db.commit()


def _storage_path_from_url(url: str) -> Path:
    prefix = "/storage/"
    if not url.startswith(prefix):
        raise ValueError("Asset URL is not in local storage")
    relative = Path(url[len(prefix) :])
    # See services/exports.storage_path_for: block traversal and absolute
    # components without resolve(), so junctioned folders keep working.
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Asset URL is not in local storage")
    return STORAGE_DIR / relative


def _url_from_storage_path(path: Path) -> str:
    relative = path.relative_to(STORAGE_DIR).as_posix()
    return f"/storage/{relative}"
