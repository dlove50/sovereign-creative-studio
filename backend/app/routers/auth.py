"""Local account auth endpoints: signup, login, logout, me.

Sessions are signed HTTP-only cookies (SameSite=Lax). Passwords are PBKDF2-hashed
(never stored or returned in plaintext). Signup creates a family_user.
"""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import auth, config
from ..database import get_db
from ..deps import ADMIN_ROLE, get_authenticated_user
from ..models import User
from ..schemas import (
    AdminPasswordSetupIn,
    AdminSetupStatusOut,
    AuthStatusOut,
    LoginIn,
    SignupIn,
    UserOut,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _owner_admin(db: Session) -> User | None:
    return db.scalars(
        select(User).where(User.role == ADMIN_ROLE).order_by(User.created_at)
    ).first()


def _set_session_cookie(response: Response, user_id: str) -> None:
    response.set_cookie(
        key=config.SESSION_COOKIE_NAME,
        value=auth.sign_session(user_id),
        max_age=config.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        path="/",
    )


@router.get("/status", response_model=AuthStatusOut)
def auth_status() -> AuthStatusOut:
    return AuthStatusOut(
        public_signup_enabled=config.PUBLIC_SIGNUP_ENABLED,
        requires_admin_approval=config.SIGNUP_REQUIRES_ADMIN_APPROVAL,
    )


@router.get("/setup-status", response_model=AdminSetupStatusOut)
def setup_status(db: Session = Depends(get_db)) -> AdminSetupStatusOut:
    """Whether the owner/admin still needs to create a password (first-time setup)."""
    owner = _owner_admin(db)
    return AdminSetupStatusOut(
        owner_exists=owner is not None,
        needs_admin_password=owner is not None and not owner.password_hash,
        owner_name=owner.name if owner else None,
    )


@router.post("/setup-admin-password", response_model=UserOut)
def setup_admin_password(
    payload: AdminPasswordSetupIn, response: Response, db: Session = Depends(get_db)
) -> User:
    """First-time admin password creation. Only usable while the owner/admin has no
    password hash; afterwards it is locked (409). Passwords are hashed, never stored
    or returned in plaintext, never logged."""
    owner = _owner_admin(db)
    if owner is None:
        raise HTTPException(status_code=409, detail="No owner_admin account configured.")
    if owner.password_hash:
        raise HTTPException(status_code=409, detail="Administrator password is already set.")
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")
    owner.password_hash = auth.hash_password(payload.password)
    db.commit()
    db.refresh(owner)
    # Log the owner in immediately after creating the password.
    _set_session_cookie(response, owner.id)
    return owner


@router.post("/signup", response_model=UserOut, status_code=201)
def signup(payload: SignupIn, response: Response, db: Session = Depends(get_db)) -> User:
    if not config.PUBLIC_SIGNUP_ENABLED:
        raise HTTPException(status_code=403, detail="Public signup is disabled.")
    username = payload.username.strip().lower()
    if db.scalar(select(User).where(func.lower(User.username) == username)):
        raise HTTPException(status_code=409, detail="That username is already taken.")
    email = (payload.email or f"{username}@family.local").strip().lower()
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(status_code=409, detail="That email is already registered.")
    # Approval-required signups are created disabled until an admin activates them.
    status = "disabled" if config.SIGNUP_REQUIRES_ADMIN_APPROVAL else "active"
    user = User(
        username=username,
        email=email,
        name=(payload.name or payload.username).strip(),
        role="family_user",
        status=status,
        credits=config.DEFAULT_SIGNUP_CREDITS,
        password_hash=auth.hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    if status == "active":
        _set_session_cookie(response, user.id)
    return user


@router.post("/login", response_model=UserOut)
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)) -> User:
    username = payload.username.strip().lower()
    user = db.scalar(select(User).where(func.lower(User.username) == username))
    # Always run the hash check (even with no user) so timing doesn't reveal which
    # usernames exist; wrong password and unknown user both fail the same way.
    valid = auth.verify_password(payload.password, user.password_hash if user else None)
    if user is None or not valid:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="This account is disabled.")
    _set_session_cookie(response, user.id)
    return user


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(config.SESSION_COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_authenticated_user)) -> User:
    return user
