"""David is the single owner/admin; first-time admin password setup + owner fallback."""
import os
import sys
import tempfile

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")
    os.environ["DEFAULT_CREDITS"] = "100"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.main import app
from app.models import User


@pytest.fixture(scope="module", autouse=True)
def _app_ready():
    with TestClient(app):  # runs lifespan -> ensure_owner_admin creates David
        yield


def _client():
    return TestClient(app)


def _owner():
    with SessionLocal() as db:
        return db.scalars(select(User).where(User.role == "owner_admin")).first()


def _clear_owner_password():
    with SessionLocal() as db:
        owner = db.scalars(select(User).where(User.role == "owner_admin")).first()
        owner.password_hash = None
        db.commit()


def test_david_is_the_only_owner_admin():
    owner = _owner()
    assert owner is not None
    assert owner.username == "david" and owner.name == "David" and owner.status == "active"
    with SessionLocal() as db:
        admins = db.scalars(select(User).where(User.role == "owner_admin")).all()
    assert len(admins) == 1


def test_setup_status_and_password_creation_flow():
    _clear_owner_password()
    c = _client()
    status = c.get("/api/auth/setup-status").json()
    assert status["owner_exists"] is True and status["needs_admin_password"] is True
    assert status["owner_name"] == "David"

    # Mismatch is rejected.
    assert c.post(
        "/api/auth/setup-admin-password",
        json={"password": "DavidStrong123", "confirm_password": "different999"},
    ).status_code == 400

    # Create the password -> stored hashed (never plaintext), and logs David in.
    r = c.post(
        "/api/auth/setup-admin-password",
        json={"password": "DavidStrong123", "confirm_password": "DavidStrong123"},
    )
    assert r.status_code == 200 and r.json()["role"] == "owner_admin"
    owner = _owner()
    assert owner.password_hash and "DavidStrong123" not in owner.password_hash

    # Setup is now locked.
    assert c.post(
        "/api/auth/setup-admin-password",
        json={"password": "AnotherPass123", "confirm_password": "AnotherPass123"},
    ).status_code == 409
    assert c.get("/api/auth/setup-status").json()["needs_admin_password"] is False


def test_david_can_log_in_with_created_password():
    # Ensure the password exists (independent of test ordering).
    setup = _client()
    if setup.get("/api/auth/setup-status").json()["needs_admin_password"]:
        setup.post(
            "/api/auth/setup-admin-password",
            json={"password": "DavidStrong123", "confirm_password": "DavidStrong123"},
        )
    c = _client()
    r = c.post("/api/auth/login", json={"username": "david", "password": "DavidStrong123"})
    assert r.status_code == 200 and r.json()["username"] == "david"
    me = c.get("/api/auth/me").json()
    assert me["name"] == "David" and me["role"] == "owner_admin"


def test_owner_fallback_resolves_to_david_only():
    # No session, no act-as header -> the owner/admin (David), never a family user.
    me = _client().get("/api/me").json()
    assert me["role"] == "owner_admin" and me["name"] == "David"


def test_fallback_errors_clearly_when_no_owner_admin():
    with SessionLocal() as db:
        owner = db.scalars(select(User).where(User.role == "owner_admin")).first()
        owner.role = "family_user"
        db.commit()
    try:
        r = _client().get("/api/me")
        assert r.status_code == 503
        assert "no owner_admin account configured" in r.json()["detail"].lower()
    finally:
        with SessionLocal() as db:
            u = db.scalars(select(User).where(User.username == "david")).first()
            u.role = "owner_admin"
            db.commit()
