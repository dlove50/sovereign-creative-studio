"""One place that decides how a credit charge is applied.

Five services charge credits, and each had written the arithmetic itself:
`user.credits -= cost`. Two problems came out of that, both reproduced before
being fixed.

**Nothing floored the balance at zero.** Every charge path subtracts without
checking, so credits go negative and the ledger records impossible
`balance_after` values (-2, -4 ...). The routers do check the balance before
starting work, but that check and the charge are far apart in time: two
requests arriving together both pass it, both render, and both subtract. In
this app a negative balance cannot be settled -- there is no billing and no
collections, it is a local family pool -- so it is a number that can only
confuse someone reading the UI.

**The idempotency guard was per-caller.** `charge_for_avatar_job` checked for
an existing charge on the same `related_id`; `charge_for_voice`, next to it in
the same module, did not. Whether a second completion charges twice depended
on which function you happened to call.

So both decisions live here instead. `apply_charge` returns what it actually
took, which is also what it writes to the ledger, so the ledger stays summable
against the balance rather than drifting from it.

The clamp is a judgement call worth stating plainly: it means a race
under-charges rather than producing a debt that cannot be collected. If the
preference is instead to record the full amount and allow a negative balance,
change `_available` and leave everything else -- that is the only place the
decision is expressed.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CreditTransaction, User

logger = logging.getLogger("sovereign.credit_guard")

CHARGE_TYPE = "generation_charge"


def already_charged(db: Session, related_id: str) -> bool:
    """True when `related_id` already carries a generation charge.

    The guard every charge path needs and only some had. Keyed the same way
    the existing callers key it, so it recognises charges they already wrote.
    """
    if not related_id:
        # No key means no way to detect a repeat; treat it as uncharged rather
        # than silently matching every other unkeyed row.
        return False
    existing = db.scalar(
        select(CreditTransaction).where(
            CreditTransaction.related_id == related_id,
            CreditTransaction.transaction_type == CHARGE_TYPE,
        )
    )
    return existing is not None


def _available(user: User) -> int:
    """Credits that may be taken. The one place the clamp is expressed."""
    return max(0, user.credits or 0)


def apply_charge(
    db: Session,
    user: User,
    amount: int,
    *,
    feature: str,
    related_id: str,
    provider: str,
    reason: str,
    skip_if_charged: bool = True,
) -> int:
    """Charge `user` and write the ledger row. Returns what was taken.

    Returns 0 when the charge was skipped as a repeat, or when the balance is
    already empty -- in both cases no ledger row is written, because a zero-
    amount row records nothing and makes the ledger harder to read.
    """
    if amount <= 0:
        return 0
    if skip_if_charged and already_charged(db, related_id):
        logger.info(
            "Skipping duplicate charge for %s (%s); already charged.",
            related_id, feature,
        )
        return 0

    taken = min(amount, _available(user))
    if taken < amount:
        # Visible because it means work was done that was not fully paid for,
        # which someone may want to reconcile.
        logger.warning(
            "Charging %s for %s short by %d credit(s): asked %d, balance %d.",
            user.id, feature, amount - taken, amount, user.credits,
        )
    if taken == 0:
        return 0

    user.credits = _available(user) - taken
    db.add(
        CreditTransaction(
            user_id=user.id,
            amount=-taken,
            reason=reason,
            transaction_type=CHARGE_TYPE,
            related_feature=feature,
            related_id=related_id,
            status="completed",
            note=f"{reason} via {provider}",
            balance_after=user.credits,
            generation_id=None,
        )
    )
    return taken
