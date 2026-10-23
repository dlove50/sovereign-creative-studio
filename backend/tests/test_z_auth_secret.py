"""The session signing key: who can read it, and whether everyone agrees on it.

Two real bugs lived here, both verified by experiment before being fixed.

1. The folder was created under the default umask, so it came out 0755 with
   0644 files. That folder holds the session signing key *and*
   integrations.json, which carries the HeyGen, OpenAI and ElevenLabs API
   keys. Any local account could read the key and forge a session cookie for
   any user, the owner admin included.

2. get_session_secret() checked for the file and then wrote it, with nothing
   making that atomic. Eight concurrent callers produced seven different keys
   and the last write won, so callers that had already signed a cookie held a
   key no longer on disk: the user logged in and was told immediately that
   the session was invalid. With seven worker threads plus the API, that was
   reachable on any first boot.

The permission test asserts on the mode rather than on "did it call chmod",
because the mode is the property that matters and chmod is only one way to
reach it.
"""
from __future__ import annotations

import os
import stat
import sys
import tempfile
import threading

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")

import pytest  # noqa: E402

from app import auth, config  # noqa: E402


@pytest.fixture
def secrets_dir(tmp_path, monkeypatch):
    """Point auth at a fresh folder and clear the cached key around the test."""
    target = tmp_path / "secrets"
    monkeypatch.setattr(config, "SECRETS_DIR", target)
    auth.reset_session_secret_cache()
    yield target
    auth.reset_session_secret_cache()


def _mode(path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


# --------------------------------------------------------------------------
# Bug 1: the key was world-readable
# --------------------------------------------------------------------------

def test_the_secrets_folder_is_not_readable_by_other_accounts(secrets_dir):
    auth.get_session_secret()
    assert _mode(secrets_dir) == 0o700, (
        f"secrets folder is {oct(_mode(secrets_dir))}; another local account "
        "can list the signing key and the provider API keys")


def test_the_key_file_is_not_readable_by_other_accounts(secrets_dir):
    auth.get_session_secret()
    key = secrets_dir / "session_secret"
    assert _mode(key) == 0o600, (
        f"signing key is {oct(_mode(key))}; anyone who can read it can forge "
        "a session for any user, including the owner admin")


def test_a_restrictive_umask_is_not_what_saves_us(secrets_dir, monkeypatch):
    """mkdir's mode argument is masked by the umask, so the mode has to be set
    explicitly. Under a permissive umask the old code produced 0755."""
    previous = os.umask(0o000)
    try:
        auth.reset_session_secret_cache()
        auth.get_session_secret()
        assert _mode(secrets_dir) == 0o700
        assert _mode(secrets_dir / "session_secret") == 0o600
    finally:
        os.umask(previous)


def test_permissions_already_on_disk_are_repaired(secrets_dir):
    """A key written by an earlier version stays loose unless fixed in place.

    integrations.json is the case that matters most: it holds the paid API
    keys, and this module does not own the code that writes it.
    """
    secrets_dir.mkdir(parents=True)
    stale_key = secrets_dir / "session_secret"
    stale_key.write_bytes(b"x" * 32)
    stale_key.chmod(0o644)
    providers = secrets_dir / "integrations.json"
    providers.write_text('{"heygen": {"api_key": "redacted"}}')
    providers.chmod(0o644)
    secrets_dir.chmod(0o755)

    changed = auth.harden_secrets_dir()

    assert _mode(secrets_dir) == 0o700
    assert _mode(stale_key) == 0o600
    assert _mode(providers) == 0o600, "the provider API keys were left readable"
    assert len(changed) == 3, f"should report each path it tightened: {changed}"


def test_hardening_is_idempotent_and_reports_nothing_when_already_tight(secrets_dir):
    auth.get_session_secret()
    assert auth.harden_secrets_dir() == []


def test_hardening_never_raises_when_the_folder_cannot_be_made(monkeypatch, tmp_path):
    """A permissions problem must not stop the app booting."""
    blocked = tmp_path / "file-not-a-dir"
    blocked.write_text("in the way")
    monkeypatch.setattr(config, "SECRETS_DIR", blocked / "secrets")
    assert auth.harden_secrets_dir() == []


# --------------------------------------------------------------------------
# Bug 2: concurrent callers disagreed about the key
# --------------------------------------------------------------------------

def test_racing_callers_all_get_the_same_key(secrets_dir):
    """The original failure: 8 callers, 7 distinct keys, 7 of them orphaned."""
    results: list[bytes] = []
    lock = threading.Lock()
    barrier = threading.Barrier(8)

    def race():
        barrier.wait()
        value = auth.get_session_secret()
        with lock:
            results.append(value)

    threads = [threading.Thread(target=race) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    on_disk = (secrets_dir / "session_secret").read_bytes()
    assert len({r.hex() for r in results}) == 1, (
        f"callers disagreed about the signing key: "
        f"{len({r.hex() for r in results})} distinct values")
    assert all(r == on_disk for r in results), (
        "a caller held a key that is not the one on disk; any cookie it signed "
        "would be rejected on the next request")


def test_an_existing_key_is_adopted_not_replaced(secrets_dir):
    """Regenerating would sign out every existing session."""
    first = auth.get_session_secret()
    auth.reset_session_secret_cache()
    assert auth.get_session_secret() == first


def test_an_empty_key_file_fails_loudly_rather_than_diverging(secrets_dir):
    """Returning a fresh key here is what produced instantly-invalid cookies."""
    secrets_dir.mkdir(parents=True)
    (secrets_dir / "session_secret").write_bytes(b"")

    # Simulate losing the create race against a writer that left it empty.
    import app.auth as mod
    real_open = mod.os.open

    def failing_open(path, flags, mode=0o777, **kwargs):
        if flags & os.O_EXCL:
            raise FileExistsError(path)
        return real_open(path, flags, mode, **kwargs)

    original = mod.os.open
    mod.os.open = failing_open
    try:
        with pytest.raises(RuntimeError, match="empty"):
            auth.get_session_secret()
    finally:
        mod.os.open = original


# --------------------------------------------------------------------------
# Caching: auth must not hit the filesystem on every request
# --------------------------------------------------------------------------

def test_the_key_is_read_from_disk_once_not_per_request(secrets_dir, monkeypatch):
    """read_session() runs for every authenticated request. Before caching,
    each one did a mkdir and a file read."""
    auth.get_session_secret()
    calls = {"n": 0}
    real = auth._read_secret

    def counting(path):
        calls["n"] += 1
        return real(path)

    monkeypatch.setattr(auth, "_read_secret", counting)
    token = auth.sign_session("user-1")
    for _ in range(25):
        auth.read_session(token)

    assert calls["n"] == 0, (
        f"the key was re-read {calls['n']} time(s) across 25 requests")


# --------------------------------------------------------------------------
# The behaviour all of the above must not have broken
# --------------------------------------------------------------------------

def test_a_signed_session_round_trips(secrets_dir):
    assert auth.read_session(auth.sign_session("user-42")) == "user-42"


def test_a_tampered_signature_is_rejected(secrets_dir):
    token = auth.sign_session("user-42")
    flipped = token[:-1] + ("a" if token[-1] != "a" else "b")
    assert auth.read_session(flipped) is None


def test_a_token_signed_with_another_key_is_rejected(secrets_dir, tmp_path, monkeypatch):
    """The forgery the loose permissions enabled: a key from elsewhere."""
    token = auth.sign_session("user-42")
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path / "other")
    auth.reset_session_secret_cache()
    assert auth.read_session(token) is None


@pytest.mark.parametrize("junk", [
    None, "", "not-a-token", "a.b", "a.b.c.d", "user.notanumber.deadbeef",
])
def test_malformed_tokens_fail_closed(secrets_dir, junk):
    assert auth.read_session(junk) is None


def test_an_expired_token_is_rejected(secrets_dir, monkeypatch):
    token = auth.sign_session("user-42")
    monkeypatch.setattr(
        config, "SESSION_MAX_AGE_SECONDS", -1)
    assert auth.read_session(token) is None
