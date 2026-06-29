"""Local sandbox / test top-up sandbox.

NOT real payment processing — no cards, no external providers, no billing. A
completed top-up grants credits through the existing credit ledger
(transaction_type=sandbox_topup) so there is a single source of truth for credits.
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..models import CreditTransaction, SandboxTopup, User
from ..schemas import SandboxTopupCreate, SandboxTopupOut, TopupPackageOut

_CURRENCY = "CAD"
_SANDBOX_NOTE = "SANDBOX/TEST MODE — no real money was processed."

# Fixed local packages. Amounts are fake/illustrative (minor units, CAD).
_PACKAGES: dict[str, dict] = {
    "starter": {"name": "Starter", "credits": 50, "amount_cents": 500},
    "creative": {"name": "Creative", "credits": 200, "amount_cents": 1500},
    "video_test": {"name": "Video Test", "credits": 500, "amount_cents": 3000},
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _money(cents: int, currency: str = _CURRENCY) -> str:
    return f"${cents / 100:.2f} {currency}"


def _require_user(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Family user not found")
    return user


def _out(db: Session, topup: SandboxTopup) -> SandboxTopupOut:
    user = db.get(User, topup.user_id)
    return SandboxTopupOut(
        id=topup.id,
        user_id=topup.user_id,
        user_name=user.name if user else "Unknown",
        package_id=topup.package_id,
        package_name=topup.package_name,
        credits=topup.credits,
        amount_cents=topup.amount_cents,
        amount_display=_money(topup.amount_cents, topup.currency),
        currency=topup.currency,
        status=topup.status,
        note=topup.note,
        credit_transaction_id=topup.credit_transaction_id,
        created_at=topup.created_at,
        completed_at=topup.completed_at,
    )


def list_packages() -> list[TopupPackageOut]:
    return [
        TopupPackageOut(
            id=pid,
            name=p["name"],
            credits=p["credits"],
            amount_cents=p["amount_cents"],
            currency=_CURRENCY,
            price_display=_money(p["amount_cents"]),
        )
        for pid, p in _PACKAGES.items()
    ]


def list_topups(db: Session, limit: int = 50) -> list[SandboxTopupOut]:
    rows = db.scalars(
        select(SandboxTopup)
        .order_by(desc(SandboxTopup.created_at))
        .limit(min(max(limit, 1), 200))
    ).all()
    return [_out(db, t) for t in rows]


def create_topup(db: Session, payload: SandboxTopupCreate) -> SandboxTopupOut:
    pkg = _PACKAGES.get(payload.package_id)
    if pkg is None:
        raise HTTPException(status_code=400, detail="Unknown credit package")
    user = _require_user(db, payload.user_id)
    topup = SandboxTopup(
        user_id=user.id,
        package_id=payload.package_id,
        package_name=pkg["name"],
        credits=pkg["credits"],
        amount_cents=pkg["amount_cents"],
        currency=_CURRENCY,
        status="pending",
        note=payload.note,
    )
    db.add(topup)
    db.commit()
    db.refresh(topup)
    return _out(db, topup)


def complete_topup(db: Session, topup_id: str) -> SandboxTopupOut:
    topup = db.get(SandboxTopup, topup_id)
    if topup is None:
        raise HTTPException(status_code=404, detail="Top-up not found")
    # Idempotency / double-completion guard: only a pending top-up grants credits.
    if topup.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Top-up is {topup.status}; only pending top-ups can be completed",
        )
    user = _require_user(db, topup.user_id)
    user.credits += topup.credits
    user.updated_at = _now()
    tx = CreditTransaction(
        user_id=user.id,
        amount=topup.credits,
        reason=f"Sandbox top-up: {topup.package_name}",
        transaction_type="sandbox_topup",
        related_feature="sandbox_topup",
        related_id=topup.id,
        status="completed",
        note=f"{_SANDBOX_NOTE} {topup.note or ''}".strip(),
        balance_after=user.credits,
        generation_id=None,
    )
    db.add(tx)
    db.flush()
    topup.status = "completed"
    topup.completed_at = _now()
    topup.credit_transaction_id = tx.id
    db.commit()
    db.refresh(topup)
    return _out(db, topup)


def cancel_topup(db: Session, topup_id: str) -> SandboxTopupOut:
    topup = db.get(SandboxTopup, topup_id)
    if topup is None:
        raise HTTPException(status_code=404, detail="Top-up not found")
    if topup.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Top-up is {topup.status}; only pending top-ups can be cancelled",
        )
    topup.status = "cancelled"
    db.commit()
    db.refresh(topup)
    return _out(db, topup)
