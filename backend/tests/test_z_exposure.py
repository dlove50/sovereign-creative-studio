"""The combination nothing used to notice: anonymous owner admin, reachable.

OWNER_FALLBACK_ENABLED defaults to true, and config.py says what that means --
"anonymous requests get owner/admin access". On a machine listening only to
itself that is a local-first convenience. Bound to a LAN address or 0.0.0.0 it
is an open admin panel: cloud spending, every family member's work and the
admin tools are all behind require_admin, which that default nullifies, since
under it everyone is an admin.

The tests below are mostly about the *combination* rather than either setting,
because each is fine alone and only the pair is dangerous. The detection also
has to agree with how the server is actually launched, so the precedence rules
-- a --host argument beating the environment -- are pinned too.
"""
from __future__ import annotations

import os
import sys
import tempfile

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")

import pytest  # noqa: E402

from app.services import exposure  # noqa: E402


def _verdict(host="127.0.0.1", fallback=True, source="test"):
    return exposure.assess(fallback_enabled=fallback, host=host, source=source)


# --------------------------------------------------------------------------
# Which addresses mean "somewhere else can reach this"
# --------------------------------------------------------------------------

@pytest.mark.parametrize("host", [
    "127.0.0.1", "localhost", "::1", "[::1]", "", "LOCALHOST",
])
def test_loopback_addresses_are_not_exposed(host):
    assert exposure.is_exposed(host) is False


@pytest.mark.parametrize("host", [
    "0.0.0.0", "::", "*", "192.168.1.50", "10.0.0.4", "100.64.1.2",
    "studio.local", "[::ffff:0:0]",
])
def test_everything_else_is_exposed(host):
    assert exposure.is_exposed(host) is True, f"{host} was treated as local-only"


# --------------------------------------------------------------------------
# The dangerous pair
# --------------------------------------------------------------------------

def test_exposed_plus_anonymous_admin_is_critical():
    verdict = _verdict(host="0.0.0.0", fallback=True)
    assert verdict.level == exposure.CRITICAL
    assert verdict.is_dangerous
    assert "owner admin" in verdict.summary
    assert "OWNER_FALLBACK_ENABLED=false" in verdict.remedy, (
        "a critical finding has to name the fix, not just the problem")


def test_a_lan_address_is_just_as_critical_as_all_interfaces():
    """A single LAN address is the more likely accident, not a safer one."""
    assert _verdict(host="192.168.1.50", fallback=True).level == exposure.CRITICAL


def test_exposed_without_anonymous_admin_is_not_critical():
    verdict = _verdict(host="0.0.0.0", fallback=False)
    assert verdict.level == exposure.WARN
    assert not verdict.is_dangerous


def test_anonymous_admin_on_localhost_is_the_normal_local_first_setup():
    """This is the shipped default and must not be reported as an emergency."""
    verdict = _verdict(host="127.0.0.1", fallback=True)
    assert verdict.level == exposure.OK
    assert not verdict.is_dangerous
    assert "before letting anything else" in verdict.remedy


def test_locked_down_is_clean():
    verdict = _verdict(host="127.0.0.1", fallback=False)
    assert verdict.level == exposure.OK
    assert verdict.remedy == ""


def test_binding_everywhere_is_described_as_such():
    """"0.0.0.0" means nothing to most people; say what it does."""
    assert "every network interface" in _verdict(host="0.0.0.0", fallback=True).summary


# --------------------------------------------------------------------------
# Finding the bind address the way the server actually gets it
# --------------------------------------------------------------------------

def test_a_host_argument_is_found():
    host, source = exposure.configured_host(
        argv=["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"],
        env={})
    assert host == "0.0.0.0"
    assert "--host" in source


def test_the_equals_form_is_found_too():
    host, _ = exposure.configured_host(
        argv=["uvicorn", "--host=192.168.1.9"], env={})
    assert host == "192.168.1.9"


def test_the_command_line_beats_the_environment():
    """uvicorn takes the argument, so detecting the env value would be wrong."""
    host, source = exposure.configured_host(
        argv=["uvicorn", "--host", "0.0.0.0"],
        env={"BACKEND_HOST": "127.0.0.1"})
    assert host == "0.0.0.0", "the environment masked a --host that actually wins"
    assert "--host" in source


@pytest.mark.parametrize("name", [
    "SOVEREIGN_BIND_HOST", "BACKEND_HOST", "UVICORN_HOST", "HOST",
])
def test_the_environment_is_used_when_there_is_no_argument(name):
    host, source = exposure.configured_host(argv=["uvicorn"], env={name: "0.0.0.0"})
    assert host == "0.0.0.0"
    assert source == name


def test_the_default_matches_what_the_launcher_binds():
    """tools/start-sovereign-linux.sh passes --host 127.0.0.1."""
    host, source = exposure.configured_host(argv=["uvicorn"], env={})
    assert host == "127.0.0.1"
    assert source == "default"
    assert exposure.is_exposed(host) is False


def test_a_trailing_host_flag_with_no_value_does_not_crash():
    host, _ = exposure.configured_host(argv=["uvicorn", "--host"], env={})
    assert host == "127.0.0.1"


def test_an_empty_environment_value_does_not_win():
    host, source = exposure.configured_host(
        argv=["uvicorn"], env={"BACKEND_HOST": "   ", "HOST": "0.0.0.0"})
    assert host == "0.0.0.0" and source == "HOST"


# --------------------------------------------------------------------------
# Strict mode
# --------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_strict_mode_recognises_the_usual_spellings(value):
    assert exposure.strict_mode({"SOVEREIGN_STRICT_SECURITY": value}) is True


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "maybe"])
def test_strict_mode_is_off_unless_clearly_asked_for(value):
    assert exposure.strict_mode({"SOVEREIGN_STRICT_SECURITY": value}) is False


def test_strict_mode_is_off_when_unset():
    assert exposure.strict_mode({}) is False


# --------------------------------------------------------------------------
# Every verdict has to be actionable
# --------------------------------------------------------------------------

@pytest.mark.parametrize("host", ["127.0.0.1", "0.0.0.0", "192.168.1.5"])
@pytest.mark.parametrize("fallback", [True, False])
def test_a_verdict_always_explains_itself(host, fallback):
    verdict = _verdict(host=host, fallback=fallback)
    assert verdict.summary.strip()
    assert verdict.level in {exposure.OK, exposure.WARN, exposure.CRITICAL}
    assert verdict.host == host
    if verdict.level != exposure.OK:
        assert verdict.remedy.strip(), "a problem reported with no fix named"
