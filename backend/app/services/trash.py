"""Selective, recoverable asset trash (soft delete).

Moving an asset to trash sets `deleted_at` on its DB row (so it disappears from
normal listings) and moves the physical file(s) into `storage/trash/<relpath>`
so a recoverable copy is kept — nothing is permanently destroyed by default.
Original uploads and assets referenced by productions/storyboards/shots/campaigns
are protected: trashing them requires an explicit force flag (the UI re-confirms).
`empty_trash` is the only destructive action and requires a confirm phrase.
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..models import (
    CampaignBundle,
    Generation,
    ProductAsset,
    ProductionProject,
    ProductSceneGeneration,
    Shot,
    VideoGeneration,
)
from ..schemas import TrashItemOut, TrashResultOut

EMPTY_TRASH_CONFIRM = "DELETE_TRASH_PERMANENTLY"
_STORAGE_URL_PREFIX = "/storage/"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _trash_dir() -> Path:
    return config.STORAGE_DIR / "trash"


# entity_type -> (model, [url attrs], is_original_upload, title fn)
_ENTITIES = {
    "video": (VideoGeneration, ["result_url"], False, lambda r: r.prompt),
    "scene": (ProductSceneGeneration, ["result_url"], False, lambda r: r.prompt),
    "generation": (Generation, ["file_url"], False, lambda r: r.prompt),
    "upload": (ProductAsset, ["original_url", "processed_url", "mask_url"], True, lambda r: r.filename),
}


def _entity(entity_type: str):
    if entity_type not in _ENTITIES:
        raise HTTPException(status_code=400, detail=f"Unknown entity type '{entity_type}'")
    return _ENTITIES[entity_type]


def _rel(url: str | None) -> str | None:
    if url and url.startswith(_STORAGE_URL_PREFIX):
        return url[len(_STORAGE_URL_PREFIX):]
    return None


def _references(db: Session, entity_type: str, entity_id: str) -> list[str]:
    """Human-readable references that should block a default trash."""
    refs: list[str] = []
    if entity_type == "scene":
        if db.scalar(select(Shot).where(Shot.product_scene_id == entity_id)):
            refs.append("a storyboard shot")
        if db.scalar(
            select(VideoGeneration).where(
                VideoGeneration.product_scene_id == entity_id,
                VideoGeneration.deleted_at.is_(None),
            )
        ):
            refs.append("a video generation")
        for bundle in db.scalars(select(CampaignBundle)).all():
            if entity_id in (bundle.scene_ids or []):
                refs.append("a campaign bundle")
                break
    elif entity_type == "video":
        if db.scalar(select(Shot).where(Shot.video_id == entity_id)):
            refs.append("a storyboard shot")
        for bundle in db.scalars(select(CampaignBundle)).all():
            if entity_id in (bundle.video_ids or []):
                refs.append("a campaign bundle")
                break
        for prod in db.scalars(select(ProductionProject)).all():
            if entity_id in (prod.video_ids or []):
                refs.append("a production")
                break
    elif entity_type == "upload":
        if db.scalar(
            select(ProductSceneGeneration).where(
                ProductSceneGeneration.asset_id == entity_id,
                ProductSceneGeneration.deleted_at.is_(None),
            )
        ):
            refs.append("a product scene")
    return refs


def _move(src_rel: str, *, to_trash: bool) -> str | None:
    """Move a storage-relative file into/out of trash; return the rel path moved."""
    live = config.STORAGE_DIR / src_rel
    trashed = _trash_dir() / src_rel
    source, target = (live, trashed) if to_trash else (trashed, live)
    if not source.is_file():
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    shutil.move(str(source), str(target))
    return src_rel


def move_to_trash(
    db: Session,
    entity_type: str,
    entity_id: str,
    *,
    force_original: bool = False,
    force_referenced: bool = False,
) -> TrashResultOut:
    model, url_attrs, is_original, _title = _entity(entity_type)
    row = db.get(model, entity_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    if getattr(row, "deleted_at", None) is not None:
        return TrashResultOut(
            trashed=True, entity_type=entity_type, entity_id=entity_id,
            moved_files=[], message="Already in trash.",
        )
    if is_original and not force_original:
        raise HTTPException(
            status_code=409,
            detail="This is an original upload. Re-confirm to move it to trash (force_original).",
        )
    refs = _references(db, entity_type, entity_id)
    if refs and not force_referenced:
        raise HTTPException(
            status_code=409,
            detail=f"Referenced by {', '.join(refs)}. Re-confirm to trash anyway (force_referenced).",
        )

    moved: list[str] = []
    for attr in url_attrs:
        rel = _rel(getattr(row, attr, None))
        if rel:
            done = _move(rel, to_trash=True)
            if done:
                moved.append(done)
    row.deleted_at = _now()
    db.commit()
    return TrashResultOut(
        trashed=True, entity_type=entity_type, entity_id=entity_id,
        moved_files=moved, message="Moved to trash. A recoverable copy was kept.",
    )


def restore(db: Session, entity_type: str, entity_id: str) -> TrashResultOut:
    model, url_attrs, _is_original, _title = _entity(entity_type)
    row = db.get(model, entity_id)
    if row is None or getattr(row, "deleted_at", None) is None:
        raise HTTPException(status_code=404, detail="Trashed asset not found")
    moved: list[str] = []
    for attr in url_attrs:
        rel = _rel(getattr(row, attr, None))
        if rel:
            done = _move(rel, to_trash=False)
            if done:
                moved.append(done)
    row.deleted_at = None
    db.commit()
    return TrashResultOut(
        trashed=False, entity_type=entity_type, entity_id=entity_id,
        moved_files=moved, message="Restored from trash.",
    )


def list_trash(db: Session) -> list[TrashItemOut]:
    out: list[TrashItemOut] = []
    for entity_type, (model, url_attrs, _is_original, title_of) in _ENTITIES.items():
        rows = db.scalars(select(model).where(model.deleted_at.is_not(None))).all()
        for row in rows:
            out.append(
                TrashItemOut(
                    entity_type=entity_type,
                    entity_id=row.id,
                    title=title_of(row),
                    file_url=next(
                        (getattr(row, a) for a in url_attrs if getattr(row, a, None)), None
                    ),
                    deleted_at=row.deleted_at,
                )
            )
    out.sort(key=lambda i: i.deleted_at, reverse=True)
    return out


def empty_trash(db: Session, confirm: str) -> dict:
    if confirm != EMPTY_TRASH_CONFIRM:
        raise HTTPException(
            status_code=400,
            detail=f"Confirmation phrase required to empty trash (expected '{EMPTY_TRASH_CONFIRM}').",
        )
    deleted_files = 0
    deleted_rows = 0
    for entity_type, (model, url_attrs, _is_original, _title) in _ENTITIES.items():
        rows = db.scalars(select(model).where(model.deleted_at.is_not(None))).all()
        for row in rows:
            for attr in url_attrs:
                rel = _rel(getattr(row, attr, None))
                if not rel:
                    continue
                target = _trash_dir() / rel
                try:
                    if target.is_file():
                        target.unlink()
                        deleted_files += 1
                except OSError:
                    pass
            db.delete(row)
            deleted_rows += 1
    db.commit()
    return {"deleted_rows": deleted_rows, "deleted_files": deleted_files}
