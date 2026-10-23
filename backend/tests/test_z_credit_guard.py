"""Credit charging: no double charges, and no balance that cannot exist.

Two bugs, both reproduced against a real session before being fixed.

Nothing floored the balance at zero. Every charge path did `user.credits -=
cost` with no check, so a user with 2 credits charged three times ended on
-4, and the ledger recorded `balance_after` of -2 and -4. The routers check
the balance before starting work, but that check and the charge are far apart
in time, so two requests arriving together both pass it and both subtract.

The idempotency guard was per-caller. `charge_for_avatar_job` checked for an
existing charge on the same related_id; `charge_for_voice`, directly below it
in the same module, did not. Whether a repeat charged twice depended on which
function was called.

The invariant worth more than any single assertion is the last one here: the
ledger must sum to the balance. A clamp that silently took credits without
writing a row, or wrote a row for credits it did not take, would satisfy the
individual checks and still leave the books wrong.
"""
from __future__ import annotations

import logging
import os
import sys
import tempfile

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")

import pytest  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402
from app.models import Base, CreditTransaction, User  # noqa: E402
from app.services import credit_guard  # noqa: E402

Base.metadata.create_all(engine)

@pytest.fixture
def charge(request):
    """Charge kwargs with a related_id unique to this test.

    The suite shares one database and these tests commit, so a fixed key let
    rows from an earlier test satisfy a later test's idempotency guard.
    """
    return dict(feature="voice_generation",
                related_id=f"rel-{request.node.name}",
                provider="piper:test", reason="voice generation")


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session
        session.rollback()


@pytest.fixture
def user(db):
    import uuid
    person = User(email=f"{uuid.uuid4().hex}@test.local", name="Charge Test",
                  role="family_user", status="active", credits=10)
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


def _rows(db, related_id):
    return db.query(CreditTransaction).filter(
        CreditTransaction.related_id == related_id).all()


# --------------------------------------------------------------------------
# The balance can never go negative
# --------------------------------------------------------------------------

def test_a_charge_larger_than_the_balance_takes_only_what_is_there(db, user, charge):
    user.credits = 3
    db.commit()

    taken = credit_guard.apply_charge(db, user, 10, **charge)
    db.commit()

    assert taken == 3, "it should report what it actually took"
    assert user.credits == 0
    assert user.credits >= 0


def test_repeated_charges_cannot_drive_the_balance_below_zero(db, user, charge):
    """The original reproduction: 2 credits, three charges of 2, ended at -4."""
    user.credits = 2
    db.commit()

    for n in range(3):
        credit_guard.apply_charge(db, user, 2, **{**charge, "related_id": f"r-{n}"})
        db.commit()
        assert user.credits >= 0, f"balance went negative after charge {n + 1}"

    assert user.credits == 0


def test_charging_an_empty_balance_writes_no_ledger_row(db, user, charge):
    """A zero-amount row records nothing and only makes the ledger harder to read."""
    user.credits = 0
    db.commit()

    assert credit_guard.apply_charge(db, user, 5, **charge) == 0
    db.commit()
    assert _rows(db, charge["related_id"]) == []


def test_an_already_negative_balance_is_not_made_worse(db, user, charge):
    """Defensive: a balance from before this fix must not keep sinking."""
    user.credits = -7
    db.commit()

    assert credit_guard.apply_charge(db, user, 5, **charge) == 0
    db.commit()
    assert user.credits == -7


def test_a_shortfall_is_logged_because_work_went_unpaid(db, user, charge):
    """Captured off the module's own logger, not caplog.

    caplog captures through the root logger, so whether it sees anything
    depends on global logging state other tests can change -- this assertion
    passed alone and failed in the full run for exactly that reason, the same
    way it did in test_z_worker_resilience.py.
    """
    user.credits = 1
    db.commit()

    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Capture(level=logging.WARNING)
    logger = credit_guard.logger
    prev_level, prev_disabled = logger.level, logger.disabled
    prev_manager = logging.root.manager.disable
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    logger.disabled = False
    logging.disable(logging.NOTSET)
    try:
        credit_guard.apply_charge(db, user, 4, **charge)
        db.commit()
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev_level)
        logger.disabled = prev_disabled
        logging.disable(prev_manager)

    assert any("short by 3" in r.getMessage() for r in records), (
        f"the shortfall was not reported: {[r.getMessage() for r in records]}")


# --------------------------------------------------------------------------
# Idempotency, for every caller rather than some of them
# --------------------------------------------------------------------------

def test_the_same_related_id_is_charged_once(db, user, charge):
    first = credit_guard.apply_charge(db, user, 2, **charge)
    db.commit()
    second = credit_guard.apply_charge(db, user, 2, **charge)
    db.commit()

    assert first == 2
    assert second == 0, "a repeat charged again"
    assert user.credits == 8
    assert len(_rows(db, charge["related_id"])) == 1


def test_different_related_ids_each_charge(db, user, charge):
    credit_guard.apply_charge(db, user, 2, **{**charge, "related_id": "a"})
    credit_guard.apply_charge(db, user, 2, **{**charge, "related_id": "b"})
    db.commit()
    assert user.credits == 6


def test_already_charged_recognises_rows_written_by_the_old_callers(db, user, charge):
    """The guard has to see charges the previous per-caller code wrote, or a
    completed job would be charged a second time after this change."""
    db.add(CreditTransaction(
        user_id=user.id, amount=-2, reason="voice generation",
        transaction_type="generation_charge", related_feature="voice_generation",
        related_id="legacy-1", status="completed", note="written by old code",
        balance_after=user.credits, generation_id=None,
    ))
    db.commit()

    assert credit_guard.already_charged(db, "legacy-1")
    assert credit_guard.apply_charge(
        db, user, 2, **{**charge, "related_id": "legacy-1"}) == 0


def test_unkeyed_charges_do_not_block_each_other(db, user, charge):
    """Treating "" as a key would make the first unkeyed charge block the rest.

    The first call charges either way, so the guard is only exercised by the
    second one -- which is what the earlier version of this test missed.
    """
    assert credit_guard.already_charged(db, "") is False
    first = credit_guard.apply_charge(db, user, 1, **{**charge, "related_id": ""})
    db.commit()
    second = credit_guard.apply_charge(db, user, 1, **{**charge, "related_id": ""})
    db.commit()

    assert first == 1
    assert second == 1, (
        'an unkeyed charge was blocked by an earlier one; "" is not a key')
    assert credit_guard.already_charged(db, "") is False


def test_the_guard_can_be_bypassed_deliberately(db, user, charge):
    """Some charges are genuinely repeatable; the caller says so explicitly."""
    credit_guard.apply_charge(db, user, 1, **charge)
    db.commit()
    again = credit_guard.apply_charge(db, user, 1, **charge, skip_if_charged=False)
    db.commit()
    assert again == 1
    assert len(_rows(db, charge["related_id"])) == 2


# --------------------------------------------------------------------------
# Degenerate amounts
# --------------------------------------------------------------------------

@pytest.mark.parametrize("amount", [0, -1, -100])
def test_a_non_positive_charge_is_a_no_op(db, user, charge, amount):
    before = user.credits
    assert credit_guard.apply_charge(db, user, amount, **charge) == 0
    db.commit()
    assert user.credits == before
    assert _rows(db, charge["related_id"]) == []


# --------------------------------------------------------------------------
# The invariant that catches what the individual checks would not
# --------------------------------------------------------------------------

def test_the_ledger_always_sums_to_the_balance(db, user, charge):
    """Every credit taken is recorded, and every row recorded was taken."""
    user.credits = 7
    db.commit()
    opening = user.credits

    for n, amount in enumerate([2, 3, 5, 1, 4]):
        credit_guard.apply_charge(db, user, amount,
                                  **{**charge, "related_id": f"sum-{n}"})
        db.commit()

    charged = sum(
        row.amount for row in db.query(CreditTransaction)
        .filter(CreditTransaction.related_id.like("sum-%")).all()
    )
    assert opening + charged == user.credits, (
        f"books do not balance: opened {opening}, ledger {charged}, "
        f"balance {user.credits}")
    assert user.credits == 0


def test_balance_after_is_never_an_impossible_number(db, user, charge):
    user.credits = 3
    db.commit()
    credit_guard.apply_charge(db, user, 2, **{**charge, "related_id": "b1"})
    credit_guard.apply_charge(db, user, 2, **{**charge, "related_id": "b2"})
    db.commit()

    recorded = [r.balance_after for r in db.query(CreditTransaction)
                .filter(CreditTransaction.related_id.in_(["b1", "b2"])).all()]
    assert all(value >= 0 for value in recorded), (
        f"the ledger records a balance that cannot exist: {recorded}")
