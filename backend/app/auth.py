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
import os
import secrets as _secrets
import stat
import threading
import time
from pathlib import Path

from . import config

_PBKDF2_ITERATIONS = 200_000
_SEP = "."

# The secrets folder holds the session signing key and, via
# services/integrations.py, every cloud provider API key. Created under the
# default umask it comes out 0755 with 0644 files, so any local account could
# read the signing key and forge a session for any user -- the owner admin
# included -- and read the paid API keys alongside it.
SECRETS_DIR_MODE = 0o700
SECRET_FILE_MODE = 0o600

# get_session_secret() is on the hot path: read_session() runs for every
# authenticated request, so without this the server did a mkdir and a file read
# per request, and auth depended on the filesystem being healthy each time.
_secret_lock = threading.Lock()
_cached_secret: bytes | None = None


def _secret_path() -> Path:
    return config.SECRETS_DIR / "session_secret"


def reset_session_secret_cache() -> None:
    """Drop the cached key. For tests that repoint SECRETS_DIR."""
    global _cached_secret
    with _secret_lock:
        _cached_secret = None


def harden_secrets_dir() -> list[str]:
    """Restrict the secrets folder and its contents. Returns what it changed.

    Repairs files already on disk rather than only fixing the writers: a key
    written earlier under a loose umask stays loose otherwise, and this module
    does not own every writer in that folder.
    """
    changed: list[str] = []
    directory = config.SECRETS_DIR
    try:
        directory.mkdir(parents=True, exist_ok=True, mode=SECRETS_DIR_MODE)
    except OSError:
        return changed
    try:
        # mkdir's mode is masked by the umask, so set it explicitly.
        if stat.S_IMODE(directory.stat().st_mode) != SECRETS_DIR_MODE:
            directory.chmod(SECRETS_DIR_MODE)
            changed.append(str(directory))
        for child in directory.iterdir():
            if not child.is_file():
                continue
            if stat.S_IMODE(child.stat().st_mode) != SECRET_FILE_MODE:
                child.chmod(SECRET_FILE_MODE)
                changed.append(str(child))
    except OSError:  # noqa: PERF203 - a mode we cannot fix must not break boot
        pass
    return changed


def _read_secret(path: Path) -> bytes | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return data or None


def _create_secret(path: Path) -> bytes:
    """Create the key, or adopt the one a racing creator already wrote.

    O_EXCL is what makes this safe. The previous check-then-write let every
    concurrent caller generate its own key and the last write win, so callers
    that had already signed a cookie held a key no longer on disk -- the user
    logged in and was told immediately that the session was invalid. With
    seven worker threads plus the API, that was reachable on any first boot.
    """
    candidate = _secrets.token_bytes(32)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, SECRET_FILE_MODE)
    except FileExistsError:
        existing = _read_secret(path)
        if existing is None:
            raise RuntimeError(
                f"{path} exists but is empty; remove it so a new session key "
                "can be created (all current sessions will be signed out)."
            ) from None
        return existing
    with os.fdopen(fd, "wb") as handle:
        handle.write(candidate)
        handle.flush()
        os.fsync(handle.fileno())
    return candidate


def get_session_secret() -> bytes:
    global _cached_secret
    if _cached_secret is not None:
        return _cached_secret
    with _secret_lock:
        if _cached_secret is not None:   # another thread won while we waited
            return _cached_secret
        harden_secrets_dir()
        path = _secret_path()
        secret = _read_secret(path) or _create_secret(path)
        _cached_secret = secret
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
