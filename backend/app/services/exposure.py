"""Notice when the studio is reachable from elsewhere while anonymous requests
still get owner admin.

`OWNER_FALLBACK_ENABLED` defaults to true, and config.py says plainly what that
means: "MUST be false before exposing the app beyond this machine -- otherwise
anonymous requests get owner/admin access." A request with no session cookie is
resolved to the owner admin, with no password.

On a machine that only listens on localhost that is a sensible local-first
convenience. The moment the server binds anything else -- a LAN address, 0.0.0.0,
a port forwarded from a router -- it stops being a convenience and becomes an
open admin panel. Cloud spending, every family member's work, and the admin
tools are all behind `require_admin`, which is correct and which that default
quietly nullifies, because under it everyone is an admin.

Nothing in the app noticed that combination. This module does.

It warns rather than refusing, because refusing would break a setup that is
already running and serving a LAN on purpose; taking someone's working studio
away is its own kind of failure. `SOVEREIGN_STRICT_SECURITY=true` opts into
refusing instead, and tools/preflight.py reports the same combination as a
blocking failure, since that is a check someone runs deliberately rather than a
line in a log they may never read.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

# Addresses that mean "this machine only". Anything else is reachable by
# something that is not this machine.
LOCAL_ONLY_HOSTS = frozenset({
    "127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1", "",
})

# Binding these means "every interface", which is the most exposed case and
# worth naming separately because it is the usual accident.
ALL_INTERFACES = frozenset({"0.0.0.0", "::", "*"})

CRITICAL, WARN, OK = "critical", "warn", "ok"


@dataclass(frozen=True)
class Verdict:
    level: str
    summary: str
    remedy: str = ""
    host: str = ""
    source: str = ""

    @property
    def is_dangerous(self) -> bool:
        return self.level == CRITICAL


def configured_host(argv: list[str] | None = None,
                    env: dict[str, str] | None = None) -> tuple[str, str]:
    """The address the server binds, and where that value came from.

    Checked in the order that actually wins at runtime: an explicit --host on
    the uvicorn command line beats the environment, which beats the default.
    """
    argv = sys.argv if argv is None else argv
    env = os.environ if env is None else env

    for index, item in enumerate(argv):
        if item == "--host" and index + 1 < len(argv):
            return argv[index + 1], "--host argument"
        if item.startswith("--host="):
            return item.split("=", 1)[1], "--host argument"

    for name in ("SOVEREIGN_BIND_HOST", "BACKEND_HOST", "UVICORN_HOST", "HOST"):
        value = (env.get(name) or "").strip()
        if value:
            return value, name

    # uvicorn's own default, and what tools/start-sovereign-linux.sh passes.
    return "127.0.0.1", "default"


def is_exposed(host: str) -> bool:
    """True when `host` is reachable from somewhere other than this machine."""
    cleaned = (host or "").strip().strip("[]").lower()
    if cleaned in ALL_INTERFACES:
        return True
    return cleaned not in LOCAL_ONLY_HOSTS


def strict_mode(env: dict[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return (env.get("SOVEREIGN_STRICT_SECURITY") or "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def assess(*, fallback_enabled: bool, host: str, source: str) -> Verdict:
    """Judge one combination of bind address and fallback setting."""
    exposed = is_exposed(host)
    everywhere = (host or "").strip().strip("[]").lower() in ALL_INTERFACES

    if exposed and fallback_enabled:
        where = "every network interface" if everywhere else f"{host}"
        return Verdict(
            CRITICAL,
            summary=(
                f"The backend is bound to {where} (from {source}) while "
                "OWNER_FALLBACK_ENABLED is true. Any request that arrives "
                "without a login cookie is treated as the owner admin -- no "
                "password. That includes spending cloud credits and reading "
                "every family member's work."
            ),
            remedy=(
                "Set OWNER_FALLBACK_ENABLED=false in backend/.env and create "
                "real logins, or bind the backend to 127.0.0.1 and reach it "
                "over a private network such as Tailscale."
            ),
            host=host, source=source,
        )

    if exposed:
        return Verdict(
            WARN,
            summary=(
                f"The backend is reachable beyond this machine on {host} "
                f"(from {source})."
            ),
            remedy=(
                "Anonymous admin access is off, which is the important part. "
                "Confirm the accounts that can reach it are ones you meant to "
                "give access."
            ),
            host=host, source=source,
        )

    if fallback_enabled:
        return Verdict(
            OK,
            summary=(
                "Local-first mode: anonymous requests act as the owner admin, "
                "and the backend only listens on this machine."
            ),
            remedy=(
                "Set OWNER_FALLBACK_ENABLED=false before letting anything else "
                "reach this port."
            ),
            host=host, source=source,
        )

    return Verdict(
        OK,
        summary="Listening on this machine only, with anonymous admin off.",
        host=host, source=source,
    )


def current_verdict(fallback_enabled: bool) -> Verdict:
    host, source = configured_host()
    return assess(fallback_enabled=fallback_enabled, host=host, source=source)
