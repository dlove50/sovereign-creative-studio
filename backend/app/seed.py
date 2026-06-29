"""Owner/admin bootstrap.

David is the single owner/admin. `ensure_owner_admin` is idempotent: it creates
the `david` owner_admin if missing (with no password — first-time setup happens
via /api/auth/setup-admin-password), normalizes his role/status, and demotes any
other owner_admin to a normal family_user so David is the only administrator.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import DEFAULT_CREDITS
from .models import User

OWNER_USERNAME = "david"
OWNER_NAME = "David"
OWNER_EMAIL = "david@family.local"

# Legacy seed identity kept only so old references resolve; David is the owner now.
DEMO_EMAIL = "demo@sovereign.studio"


def ensure_owner_admin(db: Session) -> User:
    david = db.scalar(select(User).where(func.lower(User.username) == OWNER_USERNAME))
    if david is None:
        david = db.scalar(select(User).where(func.lower(User.name) == OWNER_NAME.lower()))
    if david is None:
        david = User(
            username=OWNER_USERNAME,
            name=OWNER_NAME,
            email=OWNER_EMAIL,
            role="owner_admin",
            status="active",
            credits=DEFAULT_CREDITS,
        )
        db.add(david)
        db.flush()

    # Normalize the owner identity (never overwrites an existing password hash).
    david.username = OWNER_USERNAME
    david.name = OWNER_NAME
    david.role = "owner_admin"
    david.status = "active"

    # Exactly one owner/admin: demote any other owner_admin to a family user.
    for other in db.scalars(
        select(User).where(User.role == "owner_admin", User.id != david.id)
    ).all():
        other.role = "family_user"

    db.commit()
    db.refresh(david)
    return david


# Backwards-compatible alias for older imports.
def ensure_demo_user(db: Session) -> User:
    return ensure_owner_admin(db)
