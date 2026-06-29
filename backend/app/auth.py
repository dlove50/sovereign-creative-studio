"""Local account auth: password hashing + signed session tokens.

Stdlib only (hashlib/hmac/secrets) — no plaintext passwords, no extra deps. The
session token is an HMAC-signed `user_id.issued.signature` string carried in an
HTTP-only cookie. The signing key is generated once and stored in the backend
secrets folder (never served to the browser, redacted from backups, gitignored).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets as _secrets
import time
from pathlib import Path

from . import config

_PBKDF2_ITERATIONS = 200_000
_SEP = "."


def _secret_path() -> Path:
    return config.SECRETS_DIR / "session_secret"


def get_session_secret() -> bytes:
    config.SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    path = _secret_path()
    if path.is_file():
        data = path.read_bytes()
        if data:
            return data
    secret = _secrets.token_bytes(32)
    path.write_bytes(secret)
    return secret


# --- passwords ---------------------------------------------------------------
def hash_password(password: str) -> str:
    salt = _secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return (
        f"pbkdf2_sha256${_PBKDF2_ITERATIONS}$"
        f"{base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"
    )


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iters))
        return hmac.compare_digest(dk, expected)
    except Exception:  # noqa: BLE001 - any malformed hash fails closed.
        return False


# --- sessions ----------------------------------------------------------------
def sign_session(user_id: str) -> str:
    issued = str(int(time.time()))
    payload = f"{user_id}{_SEP}{issued}"
    sig = hmac.new(get_session_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}{_SEP}{sig}"


def read_session(token: str | None) -> str | None:
    """Return the user_id from a valid, unexpired token, else None."""
    if not token:
        return None
    try:
        user_id, issued, sig = token.split(_SEP)
    except ValueError:
        return None
    payload = f"{user_id}{_SEP}{issued}"
    expected = hmac.new(get_session_secret(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        if int(issued) + config.SESSION_MAX_AGE_SECONDS < int(time.time()):
            return None
    except ValueError:
        return None
    return user_id
