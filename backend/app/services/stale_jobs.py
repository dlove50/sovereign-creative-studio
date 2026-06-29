"""Stale job recovery.

Generation jobs run as in-process background tasks; a crash or restart can leave
a row stuck in `queued`/`running` forever (the Videos page then shows it elapsed
for thousands of minutes). This admin tool lists such stale jobs and marks them
`cancelled`/`failed` with a clear note. Credits are charge-on-completion, so a
stale (never-completed) job was never charged; if a charge somehow exists it is
refunded via the existing ledger refund, otherwise we report none.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    CopyGeneration,
    CreditTransaction,
    Generation,
    ProductSceneGeneration,
    Project,
    User,
    VideoGeneration,
)
from ..schemas import MarkStaleResultOut, StaleJobOut, StaleJobRef
from . import admin

_ACTIVE = ("queued", "running")
_STALE_NOTE = "Marked stale by admin after exceeding runtime threshold."

# feature -> (model, completed_at attr or None, title builder)
_TABLES = {
    "base_generation": (Generation, None, lambda r: r.prompt),
    "product_scene": (ProductSceneGeneration, "completed_at", lambda r: r.prompt or f"{r.preset} scene"),
    "copy": (CopyGeneration, "completed_at", lambda r: r.copy_type),
    "video": (VideoGeneration, "completed_at", lambda r: r.prompt),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _elapsed_minutes(created_at: datetime) -> int:
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return int((_now() - created_at).total_seconds() // 60)


def list_stale(db: Session, threshold_minutes: int = 60) -> list[StaleJobOut]:
    users = {u.id: u.name for u in db.scalars(select(User)).all()}
    projects = {p.id: p.name for p in db.scalars(select(Project)).all()}
    out: list[StaleJobOut] = []
    for feature, (model, _completed, title_of) in _TABLES.items():
        rows = db.scalars(select(model).where(model.status.in_(_ACTIVE))).all()
        for row in rows:
            elapsed = _elapsed_minutes(row.created_at)
            if elapsed < threshold_minutes:
                continue
            out.append(
                StaleJobOut(
                    id=row.id,
                    feature=feature,
                    status=row.status,
                    user_id=row.user_id,
                    user_name=users.get(row.user_id),
                    project_id=getattr(row, "project_id", None),
                    title=title_of(row),
                    created_at=row.created_at,
                    elapsed_minutes=elapsed,
                )
            )
    out.sort(key=lambda j: j.elapsed_minutes, reverse=True)
    return out


def dismiss_job(db: Session, feature: str, job_id: str) -> dict:
    """Archive a single job out of the Job Monitor by setting deleted_at (no file
    deletion). Used to clear confusing legacy records (e.g. a /create-page video
    attempt stored as a failed base_generation). Copy has no archive column."""
    if feature not in _TABLES or feature == "copy":
        raise HTTPException(status_code=400, detail=f"Cannot dismiss '{feature}' jobs.")
    model = _TABLES[feature][0]
    row = db.get(model, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if getattr(row, "deleted_at", None) is None:
        row.deleted_at = _now()
        db.commit()
    return {"dismissed": True, "feature": feature, "id": job_id}


def _refund_if_charged(db: Session, job_id: str) -> bool:
    """Refund any non-refunded generation charge tied to this job; return True if
    a refund was issued. Stale jobs are normally uncharged, so this is defensive."""
    tx = db.scalar(
        select(CreditTransaction).where(
            CreditTransaction.transaction_type == "generation_charge",
            (CreditTransaction.related_id == job_id)
            | (CreditTransaction.generation_id == job_id),
            CreditTransaction.amount < 0,
            CreditTransaction.status != "refunded",
        )
    )
    if tx is None:
        return False
    admin.refund_credit_transaction(db, tx.id, note=f"Refund: {_STALE_NOTE}")
    return True


def mark_stale(
    db: Session,
    *,
    action: str,
    threshold_minutes: int = 60,
    ids: list[StaleJobRef] | None = None,
) -> MarkStaleResultOut:
    if action not in {"cancelled", "failed"}:
        raise HTTPException(status_code=400, detail="action must be 'cancelled' or 'failed'")

    targets = list_stale(db, threshold_minutes)
    if ids is not None:
        wanted = {(ref.feature, ref.id) for ref in ids}
        targets = [j for j in targets if (j.feature, j.id) in wanted]

    marked = 0
    refunds = 0
    details: list[str] = []
    for job in targets:
        model, completed_attr, _ = _TABLES[job.feature]
        row = db.get(model, job.id)
        if row is None or row.status not in _ACTIVE:
            continue
        # Refund first (defensive) so balance_after stays consistent, then mark.
        if _refund_if_charged(db, row.id):
            refunds += 1
            details.append(f"{job.feature}:{row.id} refunded prior charge")
        row.status = action
        if hasattr(row, "error"):
            row.error = _STALE_NOTE
        if completed_attr and getattr(row, completed_attr, "missing") is None:
            setattr(row, completed_attr, _now())
        marked += 1
    db.commit()
    return MarkStaleResultOut(
        marked=marked,
        action=action,
        note=_STALE_NOTE,
        refunds=refunds,
        details=details,
    )
