"""Phase 13: real accounts, sessions, role separation, and data isolation."""
import os
import sys
import tempfile

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")
    os.environ["DEFAULT_CREDITS"] = "100"
    os.environ["DEFAULT_SIGNUP_CREDITS"] = "20"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal
from app.main import app
from app.models import User

HEADER = "X-SCS-Family-User-Id"


@pytest.fixture(scope="module", autouse=True)
def _app_ready():
    # Enter the app lifespan once so migrations + seed run; the per-user bare
    # clients below then share the migrated DB with their own cookie jars.
    with TestClient(app):
        yield


def _client():
    return TestClient(app)


def _signup(client, username, password="secret123", name=None):
    return client.post(
        "/api/auth/signup",
        json={"username": username, "password": password, "name": name or username},
    )


def _owner_id():
    with SessionLocal() as db:
        return db.scalars(select(User).where(User.role == "owner_admin")).first().id


def test_signup_creates_family_user_with_default_credits():
    c = _client()
    r = _signup(c, "alice")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["role"] == "family_user"
    assert body["credits"] == 20
    assert body["username"] == "alice"


def test_password_is_hashed_not_plaintext():
    c = _client()
    _signup(c, "hashcheck", password="topsecret")
    with SessionLocal() as db:
        u = db.scalar(select(User).where(func.lower(User.username) == "hashcheck"))
    assert u.password_hash and u.password_hash.startswith("pbkdf2_sha256$")
    assert "topsecret" not in (u.password_hash or "")


def test_login_logout_and_me():
    c = _client()
    _signup(c, "bob", password="bobpass1")
    c.post("/api/auth/logout")
    assert c.get("/api/auth/me").status_code == 401
    bad = c.post("/api/auth/login", json={"username": "bob", "password": "wrong"})
    assert bad.status_code == 401
    ok = c.post("/api/auth/login", json={"username": "bob", "password": "bobpass1"})
    assert ok.status_code == 200
    me = c.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["username"] == "bob"
    c.post("/api/auth/logout")
    assert c.get("/api/auth/me").status_code == 401


def test_disabled_user_cannot_log_in():
    c = _client()
    _signup(c, "carol", password="carolpw1")
    with SessionLocal() as db:
        u = db.scalar(select(User).where(func.lower(User.username) == "carol"))
        u.status = "disabled"
        db.commit()
    c.post("/api/auth/logout")
    r = c.post("/api/auth/login", json={"username": "carol", "password": "carolpw1"})
    assert r.status_code == 403


def test_user_a_cannot_see_or_impersonate_user_b():
    ca = _client(); _signup(ca, "ua_a")
    cb = _client(); _signup(cb, "ua_b")
    pa = ca.post("/api/projects", json={"name": "A-proj", "description": None}).json()["id"]
    pb = cb.post("/api/projects", json={"name": "B-proj", "description": None}).json()["id"]
    # A sees only A's projects.
    a_projects = {p["id"] for p in ca.get("/api/projects").json()}
    assert pa in a_projects and pb not in a_projects
    # A cannot impersonate B via header (non-admin -> header ignored).
    a_projects_hdr = {p["id"] for p in ca.get("/api/projects", headers={HEADER: cb.get('/api/auth/me').json()['id']}).json()}
    assert pb not in a_projects_hdr
    # A's library/jobs do not include B's.
    a_lib = {it["id"] for it in ca.get("/api/library").json()}
    assert not any(it.endswith(pb) for it in a_lib)


def test_admin_can_access_any_user_via_impersonation():
    ca = _client(); _signup(ca, "iso_a")
    a_id = ca.get("/api/auth/me").json()["id"]
    pa = ca.post("/api/projects", json={"name": "iso-A", "description": None}).json()["id"]
    # Owner (no cookie -> local owner admin) can impersonate any user to see data.
    owner = _client()
    seen = {p["id"] for p in owner.get("/api/projects", headers={HEADER: a_id}).json()}
    assert pa in seen
    # Admin dashboard endpoints work for the owner.
    assert owner.get("/api/admin/jobs").status_code == 200


def test_family_user_blocked_from_admin_endpoints():
    c = _client(); _signup(c, "nonadmin")
    assert c.get("/api/admin/jobs").status_code == 403
    assert c.get("/api/admin/integrations").status_code == 403


def test_owner_admin_default_still_works():
    # No cookie -> local owner fallback (owner_admin) keeps full access.
    c = _client()
    assert c.get("/api/admin/family-users").status_code == 200
    assert c.get("/api/projects").status_code == 200


def test_owner_fallback_can_be_disabled(monkeypatch):
    # With the fallback off, no-cookie requests are unauthenticated on protected
    # routes, while public auth routes still work.
    from app import config as appconfig

    monkeypatch.setattr(appconfig, "OWNER_FALLBACK_ENABLED", False)
    c = _client()
    assert c.get("/api/projects").status_code == 401
    assert c.get("/api/admin/jobs").status_code == 401
    assert c.get("/api/auth/status").status_code == 200
    # A logged-in user still works with the fallback disabled.
    signed = _client()
    _signup(signed, "fallback_user")
    assert signed.get("/api/projects").status_code == 200
