"""Shared auth / attribution dependencies.

Acting-user resolution order:
1. Valid signed session cookie -> that logged-in user (disabled -> 401).
   - If that user is an admin AND sends `X-SCS-Family-User-Id`, impersonate the
     target (admin-only). Non-admins always act as themselves; the header is
     ignored so a normal user cannot impersonate by changing headers.
2. No session cookie -> local owner fallback (the machine owner / first user),
   preserving the private local-first default. The fallback owner is an admin, so
   admin tools/tests may still impersonate via the header.
"""
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import auth, config
from .database import get_db
from .models import User
from .seed import ensure_owner_admin

ACTIVE_USER_HEADER = "X-SCS-Family-User-Id"
ADMIN_ROLE = "owner_admin"


def _impersonate(db: Session, header_id: str) -> User:
    user = db.get(User, header_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Active family user not found")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="Active family user is disabled")
    return user


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    x_scs_family_user_id: str | None = Header(default=None, alias=ACTIVE_USER_HEADER),
) -> User:
    session_uid = auth.read_session(request.cookies.get(config.SESSION_COOKIE_NAME))
    if session_uid:
        user = db.get(User, session_uid)
        if user is None or user.status != "active":
            raise HTTPException(status_code=401, detail="Session is no longer valid")
        # Only admins may impersonate via header; everyone else acts as themselves.
        if x_scs_family_user_id and user.role == ADMIN_ROLE:
            return _impersonate(db, x_scs_family_user_id)
        return user
    # No valid session. The local owner fallback is for private local-first use
    # only and must be disabled before any public exposure.
    if not config.OWNER_FALLBACK_ENABLED:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # Explicit local "act as" (admin tooling / tests) may target a family user.
    if x_scs_family_user_id:
        return _impersonate(db, x_scs_family_user_id)
    # Otherwise the fallback resolves to the owner/admin (David) only — never to
    # a family user, and never to an arbitrary first-created account.
    owner = db.scalars(
        select(User)
        .where(User.role == ADMIN_ROLE, User.status == "active")
        .order_by(User.created_at)
    ).first()
    if owner is None:
        raise HTTPException(status_code=503, detail="No owner_admin account configured.")
    return owner


def get_authenticated_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Strict variant: requires a valid session cookie (used by /api/auth/me)."""
    session_uid = auth.read_session(request.cookies.get(config.SESSION_COOKIE_NAME))
    if not session_uid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = db.get(User, session_uid)
    if user is None or user.status != "active":
        raise HTTPException(status_code=401, detail="Session is no longer valid")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != ADMIN_ROLE:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
