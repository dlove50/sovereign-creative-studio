"""Private/local admin dashboard aggregation.

This is intentionally a thin read-only layer over existing tables plus a safe
workflow reset action. It does not introduce public auth, payments, or a second
user system.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from .. import config
from ..models import (
    CopyGeneration,
    CreditTransaction,
    Generation,
    ProductSceneGeneration,
    User,
    VideoGeneration,
)
from ..schemas import (
    AdminCreditAdjustmentIn,
    AdminCreditTransactionOut,
    AdminDashboardOut,
    FamilyUserCreate,
    FamilyUserOut,
    FamilyUserUpdate,
    AdminJobSummaryOut,
    AdminSafeResetOut,
    AdminUsageSummaryOut,
    AdminUserSummaryOut,
)
from . import model_manager, workflow_manager


SAFE_WORKFLOW_CONFIG = {
    "image_model": "flux-kontext",
    "video_backend": "mock",
}
VALID_ROLES = {"owner_admin", "family_user", "guest"}
VALID_STATUSES = {"active", "disabled"}


def build_dashboard(db: Session) -> AdminDashboardOut:
    users = db.scalars(select(User).order_by(User.created_at)).all()
    recent_jobs = _recent_jobs(db, limit=12)
    failed_jobs = [job for job in _recent_jobs(db, limit=50) if job.status == "failed"][:12]

    return AdminDashboardOut(
        title="Private Family Studio Admin",
        mode="local/private family studio",
        service_health=_status_summary(),
        model_status=model_manager.build_model_manager_status(),
        workflow_status=workflow_manager.get_status(),
        workflow_config=_workflow_config(),
        family_users=[_user_summary(db, user) for user in users],
        recent_jobs=recent_jobs,
        failed_jobs=failed_jobs,
        recent_credit_transactions=_credit_transactions(db),
        recent_usage=_recent_usage(db),
    )


def reset_safe_workflow_config() -> AdminSafeResetOut:
    result = workflow_manager.update_config(SAFE_WORKFLOW_CONFIG)
    return AdminSafeResetOut(**result)


def list_family_users(db: Session) -> list[FamilyUserOut]:
    users = db.scalars(select(User).order_by(User.created_at)).all()
    return [_family_user_out(db, user) for user in users]


def create_family_user(db: Session, payload: FamilyUserCreate) -> FamilyUserOut:
    email = (payload.email or _local_email(payload.display_name)).strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="A family user with this email already exists")

    user = User(
        email=email,
        name=payload.display_name.strip(),
        role=payload.role,
        status=payload.status,
        notes=payload.notes,
        credits=payload.initial_credits,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _family_user_out(db, user)


def update_family_user(
    db: Session, user_id: str, payload: FamilyUserUpdate
) -> FamilyUserOut:
    user = _get_family_user(db, user_id)
    if payload.display_name is not None:
        user.name = payload.display_name.strip()
    if payload.role is not None:
        user.role = payload.role
    if payload.status is not None:
        user.status = payload.status
    if "notes" in payload.model_fields_set:
        user.notes = payload.notes
    user.updated_at = _now()
    db.commit()
    db.refresh(user)
    return _family_user_out(db, user)


def set_family_user_status(db: Session, user_id: str, status: str) -> FamilyUserOut:
    if status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid family user status")
    user = _get_family_user(db, user_id)
    user.status = status
    user.updated_at = _now()
    db.commit()
    db.refresh(user)
    return _family_user_out(db, user)


def list_credit_transactions(
    db: Session,
    *,
    user_id: str | None = None,
    transaction_type: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[AdminCreditTransactionOut]:
    stmt = select(CreditTransaction).order_by(desc(CreditTransaction.created_at))
    if user_id:
        stmt = stmt.where(CreditTransaction.user_id == user_id)
    if transaction_type:
        stmt = stmt.where(CreditTransaction.transaction_type == transaction_type)
    if status:
        stmt = stmt.where(CreditTransaction.status == status)
    rows = db.scalars(stmt.limit(min(max(limit, 1), 500))).all()
    return _credit_transaction_out(db, rows)


def add_credits(db: Session, payload: AdminCreditAdjustmentIn) -> FamilyUserOut:
    return _manual_adjustment(
        db,
        payload=payload,
        amount=payload.amount,
        transaction_type="manual_add",
        reason="manual credit add",
    )


def remove_credits(db: Session, payload: AdminCreditAdjustmentIn) -> FamilyUserOut:
    user = _get_family_user(db, payload.user_id)
    if user.credits < payload.amount:
        raise HTTPException(
            status_code=400,
            detail="Cannot remove more credits than the user currently has",
        )
    return _manual_adjustment(
        db,
        payload=payload,
        amount=-payload.amount,
        transaction_type="manual_remove",
        reason="manual credit remove",
        user=user,
    )


def refund_credit_transaction(
    db: Session, transaction_id: str, note: str | None = None
) -> AdminCreditTransactionOut:
    tx = db.get(CreditTransaction, transaction_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="Credit transaction not found")
    if tx.amount >= 0:
        raise HTTPException(status_code=400, detail="Only credit charges can be refunded")
    if tx.status == "refunded":
        raise HTTPException(status_code=400, detail="Credit transaction already refunded")

    user = _get_family_user(db, tx.user_id)
    refund_amount = abs(tx.amount)
    user.credits += refund_amount
    user.updated_at = _now()
    tx.status = "refunded"
    refund = CreditTransaction(
        user_id=user.id,
        amount=refund_amount,
        reason="refund",
        transaction_type="refund",
        related_feature=tx.related_feature,
        related_id=tx.related_id or tx.generation_id,
        status="refunded",
        note=note or f"Refunded transaction {tx.id}",
        balance_after=user.credits,
        generation_id=tx.generation_id,
    )
    db.add(refund)
    db.commit()
    db.refresh(refund)
    return _credit_transaction_out(db, [refund])[0]


def _status_summary():
    # Import inside the function so tests/Workflow Manager runtime patches remain visible.
    from ..routers.status import status as build_status

    return build_status()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _local_email(display_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", display_name.lower()).strip("-") or "family-user"
    return f"{slug}-{uuid.uuid4().hex[:8]}@family.local"


def _get_family_user(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Family user not found")
    return user


def _manual_adjustment(
    db: Session,
    *,
    payload: AdminCreditAdjustmentIn,
    amount: int,
    transaction_type: str,
    reason: str,
    user: User | None = None,
) -> FamilyUserOut:
    user = user or _get_family_user(db, payload.user_id)
    user.credits += amount
    user.updated_at = _now()
    db.add(
        CreditTransaction(
            user_id=user.id,
            amount=amount,
            reason=reason,
            transaction_type=transaction_type,
            related_feature="admin_adjustment",
            related_id=None,
            status="manual",
            note=payload.note,
            balance_after=user.credits,
            generation_id=None,
        )
    )
    db.commit()
    db.refresh(user)
    return _family_user_out(db, user)


def _workflow_config() -> dict[str, str]:
    path = config.STORAGE_DIR / "workflow_config.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - admin display should not fail on bad JSON.
        return {"error": "workflow_config.json could not be read"}
    return {str(key): str(value) for key, value in data.items()}


def _user_summary(db: Session, user: User) -> AdminUserSummaryOut:
    activity_candidates = [
        _latest(db, Generation, user.id),
        _latest(db, ProductSceneGeneration, user.id),
        _latest(db, CopyGeneration, user.id),
        _latest(db, VideoGeneration, user.id),
        _latest(db, CreditTransaction, user.id),
    ]
    last_activity = max(
        (activity for activity in activity_candidates if activity is not None),
        default=None,
    )
    return AdminUserSummaryOut(
        id=user.id,
        display_name=user.name,
        email=user.email,
        role=user.role,
        status=user.status,
        notes=user.notes,
        credit_balance=user.credits,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_activity_at=last_activity,
    )


def _family_user_out(db: Session, user: User) -> FamilyUserOut:
    summary = _user_summary(db, user)
    return FamilyUserOut(
        id=summary.id,
        display_name=summary.display_name,
        email=summary.email,
        role=summary.role,
        status=summary.status,
        notes=summary.notes,
        credit_balance=summary.credit_balance,
        created_at=summary.created_at,
        updated_at=summary.updated_at,
        last_activity_at=summary.last_activity_at,
    )


def _latest(db: Session, model, user_id: str):
    column = getattr(model, "created_at")
    return db.scalar(select(func.max(column)).where(model.user_id == user_id))


def _recent_jobs(db: Session, limit: int) -> list[AdminJobSummaryOut]:
    jobs: list[AdminJobSummaryOut] = []
    jobs.extend(_generic_generation_jobs(db, limit))
    jobs.extend(_scene_jobs(db, limit))
    jobs.extend(_copy_jobs(db, limit))
    jobs.extend(_video_jobs(db, limit))
    jobs.sort(key=lambda job: job.created_at, reverse=True)
    return jobs[:limit]


def _generic_generation_jobs(db: Session, limit: int) -> list[AdminJobSummaryOut]:
    rows = db.scalars(select(Generation).order_by(desc(Generation.created_at)).limit(limit)).all()
    return [
        AdminJobSummaryOut(
            id=row.id,
            type="base_generation",
            label=f"{row.media_type} generation",
            status=row.status,
            project_id=row.project_id,
            prompt=row.prompt,
            error=row.error,
            result_url=row.file_url,
            created_at=row.created_at,
            completed_at=row.updated_at if row.status == "completed" else None,
        )
        for row in rows
    ]


def _scene_jobs(db: Session, limit: int) -> list[AdminJobSummaryOut]:
    rows = db.scalars(
        select(ProductSceneGeneration)
        .order_by(desc(ProductSceneGeneration.created_at))
        .limit(limit)
    ).all()
    return [
        AdminJobSummaryOut(
            id=row.id,
            type="product_scene",
            label=f"{row.preset} scene",
            status=row.status,
            project_id=row.project_id,
            prompt=row.prompt,
            error=row.error,
            result_url=row.result_url,
            created_at=row.created_at,
            completed_at=row.completed_at,
        )
        for row in rows
    ]


def _copy_jobs(db: Session, limit: int) -> list[AdminJobSummaryOut]:
    rows = db.scalars(select(CopyGeneration).order_by(desc(CopyGeneration.created_at)).limit(limit)).all()
    return [
        AdminJobSummaryOut(
            id=row.id,
            type="copy",
            label=row.copy_type,
            status=row.status,
            project_id=row.project_id,
            prompt=row.prompt,
            error=row.error,
            result_url=None,
            created_at=row.created_at,
            completed_at=row.completed_at,
        )
        for row in rows
    ]


def _video_jobs(db: Session, limit: int) -> list[AdminJobSummaryOut]:
    rows = db.scalars(select(VideoGeneration).order_by(desc(VideoGeneration.created_at)).limit(limit)).all()
    return [
        AdminJobSummaryOut(
            id=row.id,
            type="video",
            label=f"{row.motion_preset} video",
            status=row.status,
            project_id=row.project_id,
            prompt=row.prompt,
            error=row.error,
            result_url=row.result_url,
            created_at=row.created_at,
            completed_at=row.completed_at,
        )
        for row in rows
    ]


def _credit_transactions(db: Session) -> list[AdminCreditTransactionOut]:
    rows = db.scalars(
        select(CreditTransaction)
        .order_by(desc(CreditTransaction.created_at))
        .limit(20)
    ).all()
    return _credit_transaction_out(db, rows)


def _credit_transaction_out(
    db: Session, rows: list[CreditTransaction]
) -> list[AdminCreditTransactionOut]:
    users = {user.id: user.name for user in db.scalars(select(User)).all()}
    return [
        AdminCreditTransactionOut(
            id=row.id,
            user_id=row.user_id,
            user_name=users.get(row.user_id, "Unknown user"),
            transaction_type=row.transaction_type,
            amount=row.amount,
            related_feature=row.related_feature,
            related_id=row.related_id,
            status=row.status,
            reason=row.reason,
            note=row.note,
            balance_after=row.balance_after,
            generation_id=row.generation_id,
            created_at=row.created_at,
        )
        for row in rows
    ]


def _recent_usage(db: Session, limit: int = 20) -> list[AdminUsageSummaryOut]:
    users = {user.id: user.name for user in db.scalars(select(User)).all()}
    transactions = db.scalars(select(CreditTransaction)).all()
    by_related = {
        (tx.related_feature, tx.related_id or tx.generation_id): tx
        for tx in transactions
        if tx.related_id or tx.generation_id
    }
    by_generation = {tx.generation_id: tx for tx in transactions if tx.generation_id}
    usage: list[AdminUsageSummaryOut] = []

    for row in db.scalars(
        select(Generation).order_by(desc(Generation.created_at)).limit(limit)
    ).all():
        tx = by_generation.get(row.id) or by_related.get(("base_generation", row.id))
        usage.append(
            _usage_out(
                users,
                row.id,
                row.user_id,
                "base_generation",
                f"{row.media_type} generation",
                row.status,
                row.credits_cost,
                tx,
                row.created_at,
                row.updated_at if row.status in {"completed", "failed"} else None,
            )
        )

    for row in db.scalars(
        select(ProductSceneGeneration)
        .order_by(desc(ProductSceneGeneration.created_at))
        .limit(limit)
    ).all():
        tx = by_related.get(("product_scene", row.id))
        usage.append(
            _usage_out(
                users,
                row.id,
                row.user_id,
                "product_scene",
                f"{row.preset} scene",
                row.status,
                0,
                tx,
                row.created_at,
                row.completed_at,
            )
        )

    for row in db.scalars(
        select(CopyGeneration).order_by(desc(CopyGeneration.created_at)).limit(limit)
    ).all():
        tx = by_related.get(("copy", row.id))
        usage.append(
            _usage_out(
                users,
                row.id,
                row.user_id,
                "copy",
                row.copy_type,
                row.status,
                0,
                tx,
                row.created_at,
                row.completed_at,
            )
        )

    for row in db.scalars(
        select(VideoGeneration).order_by(desc(VideoGeneration.created_at)).limit(limit)
    ).all():
        tx = by_related.get(("video", row.id))
        # Video charges live in the ledger (no credits_cost column); reflect the
        # actual debited amount so completed video jobs show their real cost.
        video_charged = abs(tx.amount) if tx is not None and tx.amount < 0 else 0
        usage.append(
            _usage_out(
                users,
                row.id,
                row.user_id,
                "video",
                f"{row.motion_preset} video",
                row.status,
                video_charged,
                tx,
                row.created_at,
                row.completed_at,
            )
        )

    usage.sort(key=lambda item: item.created_at, reverse=True)
    return usage[:limit]


def _usage_out(
    users: dict[str, str],
    item_id: str,
    user_id: str,
    feature: str,
    label: str,
    status: str,
    credits_charged: int,
    tx: CreditTransaction | None,
    created_at,
    completed_at,
) -> AdminUsageSummaryOut:
    if tx is None:
        ledger_status = "not_charged" if credits_charged == 0 else "missing_ledger"
        related_transaction_id = None
    elif tx.status == "refunded":
        ledger_status = "refunded"
        related_transaction_id = tx.id
    elif tx.amount < 0:
        ledger_status = "charged"
        related_transaction_id = tx.id
    else:
        ledger_status = tx.status
        related_transaction_id = tx.id
    if status == "failed" and tx is None:
        ledger_status = "failed_not_charged"
    return AdminUsageSummaryOut(
        id=item_id,
        user_id=user_id,
        user_name=users.get(user_id, "Unknown user"),
        feature=feature,
        label=label,
        status=status,
        credits_charged=credits_charged,
        ledger_status=ledger_status,
        related_transaction_id=related_transaction_id,
        created_at=created_at,
        completed_at=completed_at,
    )
