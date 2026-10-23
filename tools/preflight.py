#!/usr/bin/env python3
"""Why won't this generate? Check the whole chain before blaming the GPU.

The studio has not produced an image on the R9700 yet, and the reason turned
out to be one line of configuration: the backend dials ComfyUI on port 8001
(the repo's convention, consistent across every branch) while ComfyUI on that
machine answers on 8188. Nothing reported that. The backend simply failed to
connect, several layers from where anyone was looking.

This script checks each link in the chain and names what is wrong, in the
order a render actually depends on them. It is READ-ONLY: it opens sockets and
reads files, starts nothing, writes nothing, and never touches the GPU.

The port check is the one that matters most, and it does more than test the
configured address. When the configured port does not answer it scans the ports
ComfyUI is commonly started on and reports where it actually found it, with the
exact line to put in backend/.env. A check that says only "cannot connect"
would have left this blocker exactly as unresolved as it was.

Usage:
    python3 tools/preflight.py
    python3 tools/preflight.py --models-dir /path/to/ComfyUI/models
    python3 tools/preflight.py --json

Exit status: 0 when nothing blocks a render, 1 when something does. Warnings
alone do not fail, so this is safe in a pre-render hook.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BACKEND = REPO / "backend"

# Ports ComfyUI is commonly started on. 8188 is its own default; 8001 is this
# repo's convention; 8000 collides with the backend and is included so the
# scan can say so rather than appearing to find nothing.
COMFY_CANDIDATE_PORTS = (8188, 8001, 8189, 8000)

OK, WARN, FAIL = "ok", "warn", "fail"


class Report:
    """Collects findings. Only FAIL affects the exit status."""

    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, status: str, check: str, detail: str, fix: str = "") -> None:
        self.rows.append(
            {"status": status, "check": check, "detail": detail, "fix": fix}
        )

    @property
    def blocked(self) -> bool:
        return any(r["status"] == FAIL for r in self.rows)

    def print_human(self) -> None:
        mark = {OK: "  ok  ", WARN: " warn ", FAIL: " FAIL "}
        width = max((len(r["check"]) for r in self.rows), default=0)
        for row in self.rows:
            print(f"[{mark[row['status']]}] {row['check']:<{width}}  {row['detail']}")
            if row["fix"]:
                print(f"{'':>9}{'':<{width}}  -> {row['fix']}")
        print()
        fails = sum(1 for r in self.rows if r["status"] == FAIL)
        warns = sum(1 for r in self.rows if r["status"] == WARN)
        if fails:
            print(f"{fails} blocking problem(s), {warns} warning(s). "
                  "A render will not succeed until the blockers are fixed.")
        elif warns:
            print(f"Nothing blocking, {warns} warning(s).")
        else:
            print("Everything checked is in order.")


# --------------------------------------------------------------------------
# env
# --------------------------------------------------------------------------

def read_env_file(path: Path) -> dict[str, str]:
    """Parse backend/.env well enough to read our own settings.

    Deliberately not python-dotenv: this script must run with no dependencies
    installed, since "the venv is broken" is one of the things it diagnoses.
    """
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        # An inline comment after a value is common and would otherwise end up
        # inside the URL.
        if " #" in value:
            value = value.split(" #", 1)[0].strip()
        values[key.strip()] = value
    return values


def setting(env: dict[str, str], key: str, default: str) -> tuple[str, str]:
    """Resolve a setting and say where it came from. Process env wins."""
    if key in os.environ and os.environ[key].strip():
        return os.environ[key].strip(), "environment"
    if key in env and env[key].strip():
        return env[key].strip(), "backend/.env"
    return default, "repo default"


# --------------------------------------------------------------------------
# probes
# --------------------------------------------------------------------------

def port_open(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ValueError, OverflowError):
        return False


def http_ok(url: str, timeout: float = 4.0) -> bool:
    """True when the URL answers with any HTTP status at all."""
    try:
        with urllib.request.urlopen(url, timeout=timeout):
            return True
    except urllib.error.HTTPError:
        return True          # answered, just not 200 -- something is listening
    except Exception:        # noqa: BLE001 - reachability probe only
        return False


def split_host_port(url: str, default_port: int) -> tuple[str, int]:
    rest = url.split("://", 1)[-1].split("/", 1)[0]
    host, _, port = rest.partition(":")
    try:
        return (host or "127.0.0.1"), (int(port) if port else default_port)
    except ValueError:
        return (host or "127.0.0.1"), default_port


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------

def check_comfyui(report: Report, env: dict[str, str]) -> None:
    """The blocker that stopped this project. Find where ComfyUI really is."""
    url, origin = setting(env, "COMFYUI_BASE_URL", "http://127.0.0.1:8001")
    host, port = split_host_port(url, 8001)

    if http_ok(f"{url.rstrip('/')}/system_stats") or port_open(host, port):
        report.add(OK, "ComfyUI", f"answering at {url} (from {origin})")
        return

    # Configured address is dead. Say where it actually is, not just that it
    # is not here -- that difference is the whole point of this script.
    found = [p for p in COMFY_CANDIDATE_PORTS if p != port and port_open(host, p)]
    if found:
        actual = found[0]
        note = ""
        if actual == 8000:
            note = (" (note: 8000 is the backend's own port, so this may be "
                    "the backend answering, not ComfyUI)")
        report.add(
            FAIL, "ComfyUI",
            f"nothing on port {port} (configured, from {origin}), but "
            f"something is listening on {actual}{note}",
            f"set COMFYUI_BASE_URL=http://{host}:{actual} in backend/.env",
        )
    else:
        report.add(
            FAIL, "ComfyUI",
            f"nothing listening at {url} (from {origin}), and no ComfyUI found "
            f"on {', '.join(str(p) for p in COMFY_CANDIDATE_PORTS)}",
            "start it with tools/start-comfyui-rocm.sh",
        )


def check_exposure(report: Report, env: dict[str, str]) -> None:
    """Anonymous owner-admin plus a non-local bind address is an open admin panel.

    Reported as blocking here, while app startup only warns. Startup must not
    take away a studio that is already running and serving a LAN on purpose;
    this is a check someone runs deliberately, so it can be blunt.

    The detection is duplicated from backend/app/services/exposure.py rather
    than imported, because this script deliberately runs with no dependencies
    and no app import -- a broken venv is one of the things it diagnoses.
    """
    local_only = {"127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1", ""}
    everywhere = {"0.0.0.0", "::", "*"}

    raw, host_origin = setting(env, "BACKEND_HOST", "127.0.0.1")
    host = raw.strip().strip("[]").lower()
    exposed = host in everywhere or host not in local_only

    flag, flag_origin = setting(env, "OWNER_FALLBACK_ENABLED", "true")
    fallback = flag.strip().lower() in {"1", "true", "yes", "on"}

    if exposed and fallback:
        where = "every interface" if host in everywhere else host
        report.add(
            FAIL, "Anonymous admin",
            f"backend binds {where} (from {host_origin}) while "
            f"OWNER_FALLBACK_ENABLED is true (from {flag_origin}): any request "
            "with no login cookie is treated as the owner admin",
            "set OWNER_FALLBACK_ENABLED=false in backend/.env, or bind 127.0.0.1 "
            "and reach it over a private network",
        )
    elif exposed:
        report.add(OK, "Anonymous admin",
                   f"off; backend reachable on {host} (from {host_origin})")
    elif fallback:
        report.add(OK, "Anonymous admin",
                   "local-first: on, but the backend listens on this machine only")
    else:
        report.add(OK, "Anonymous admin", "off, and listening on this machine only")


def check_secrets_are_not_served(report: Report, env: dict[str, str]) -> None:
    """SECRETS_DIR defaults inside STORAGE_DIR, which is mounted at /storage.

    So GET /storage/secrets/session_secret returns the key that signs every
    session cookie, and integrations.json returns the cloud API keys, to
    anyone who can reach the port. Verified by request, not inferred.
    """
    storage_raw, _ = setting(env, "STORAGE_DIR", str(BACKEND / "storage"))
    secrets_raw, origin = setting(
        env, "SECRETS_DIR", str(Path(storage_raw) / "secrets"))
    try:
        storage = Path(storage_raw).resolve()
        secrets = Path(secrets_raw).resolve()
        inside = secrets.is_relative_to(storage)
    except (OSError, ValueError):
        report.add(WARN, "Secrets exposure", "could not resolve the secrets path")
        return

    if inside:
        rel = secrets.relative_to(storage).as_posix()
        report.add(
            FAIL, "Secrets exposure",
            f"{secrets} is inside the folder served at /storage (from {origin}), "
            f"so GET /storage/{rel}/session_secret returns the session signing "
            "key and .../integrations.json returns the provider API keys",
            "run tools/harden-sovereign.sh --apply, which moves them and sets "
            "SECRETS_DIR in backend/.env",
        )
    else:
        report.add(OK, "Secrets exposure",
                   f"secrets are outside the served tree ({secrets})")


def check_backups_are_not_served(report: Report, env: dict[str, str]) -> None:
    """Backups default to STORAGE_DIR/backups, which is served at /storage.

    A backup zip holds the database -- every account, password hash and credit
    balance. Its name is a timestamp rather than a UUID, so it can be guessed
    instead of having to leak.
    """
    storage_raw, _ = setting(env, "STORAGE_DIR", str(BACKEND / "storage"))
    backups_raw, origin = setting(
        env, "BACKUP_DIR", str(Path(storage_raw) / "backups"))
    try:
        storage = Path(storage_raw).resolve()
        backups = Path(backups_raw).resolve()
        inside = backups.is_relative_to(storage)
    except (OSError, ValueError):
        report.add(WARN, "Backup exposure", "could not resolve the backup path")
        return

    if inside:
        rel = backups.relative_to(storage).as_posix()
        report.add(
            FAIL, "Backup exposure",
            f"{backups} is served at /storage/{rel} (from {origin}); a backup "
            "zip holds the database, and its name is a guessable timestamp",
            "run tools/harden-sovereign.sh --apply, which moves it and sets "
            "BACKUP_DIR in backend/.env",
        )
    else:
        report.add(OK, "Backup exposure",
                   f"backups are outside the served tree ({backups})")


def check_backend_and_frontend(report: Report, env: dict[str, str]) -> None:
    for label, key, default in (
        # 8002 is what tools/start-sovereign-linux.sh binds. next.config.mjs
        # still defaults to 8000, which is a separate inconsistency worth
        # knowing about; this follows the launcher, since that is what runs.
        ("Backend", "BACKEND_PORT", "8002"),
        ("Frontend", "FRONTEND_PORT", "3000"),
    ):
        raw, origin = setting(env, key, default)
        try:
            port = int(raw)
        except ValueError:
            report.add(FAIL, label, f"{key}={raw!r} is not a port number",
                       f"set {key} to a number in backend/.env")
            continue
        if port_open("127.0.0.1", port):
            report.add(OK, label, f"serving on {port} (from {origin})")
        else:
            report.add(WARN, label, f"not running on {port} (from {origin})",
                       "start it with tools/start-sovereign-linux.sh")


def check_workflows(report: Report, env: dict[str, str]) -> None:
    """A workflow path that does not resolve fails at render time, not startup."""
    checks = (
        ("COMFYUI_WORKFLOW_PATH", "workflows/text_to_image.json"),
        ("COMFYUI_IMAGE_EDIT_WORKFLOW_PATH", "workflows/image_edit_qwen_2509.json"),
        ("COMFYUI_VIDEO_WORKFLOW_PATH", "workflows/image_to_video.json"),
    )
    missing: list[str] = []
    for key, default in checks:
        raw, _ = setting(env, key, default)
        path = Path(raw)
        if not path.is_absolute():
            path = BACKEND / path
        if not path.is_file():
            missing.append(f"{key} -> {raw}")
    if missing:
        report.add(FAIL, "Workflows", f"{len(missing)} path(s) do not resolve: "
                   + "; ".join(missing),
                   "check the paths in backend/.env against backend/workflows/")
    else:
        report.add(OK, "Workflows", f"all {len(checks)} configured paths resolve")


def check_models_dir(report: Report, models_dir: Path | None) -> None:
    if models_dir is None:
        report.add(WARN, "Models", "not checked; pass --models-dir to verify "
                   "the weights a workflow asks for are installed")
        return
    if not models_dir.is_dir():
        report.add(FAIL, "Models", f"{models_dir} is not a directory",
                   "point --models-dir at ComfyUI's models folder")
        return
    try:
        weights = [p for p in models_dir.rglob("*")
                   if p.suffix in {".safetensors", ".gguf", ".ckpt", ".pt"}]
    except OSError as exc:
        report.add(WARN, "Models", f"{models_dir} could not be walked: {exc}")
        return
    if not weights:
        report.add(FAIL, "Models", f"no weight files under {models_dir}",
                   "check the path; a render cannot load anything from here")
    else:
        total = sum(p.stat().st_size for p in weights if p.is_file())
        report.add(OK, "Models",
                   f"{len(weights)} weight file(s), {total / 1024**3:.1f} GiB on "
                   f"disk under {models_dir}")


def check_storage(report: Report, env: dict[str, str]) -> None:
    """Generations are written here; read-only storage fails mid-job."""
    raw, origin = setting(env, "STORAGE_DIR", str(BACKEND / "storage"))
    path = Path(raw)
    if not path.is_dir():
        report.add(WARN, "Storage", f"{path} does not exist yet (from {origin})",
                   "it is created on first write; no action needed if that is expected")
        return
    if os.access(path, os.W_OK):
        report.add(OK, "Storage", f"{path} is writable")
    else:
        report.add(FAIL, "Storage", f"{path} is not writable",
                   "a render will fail when it writes its output")


def check_tools(report: Report) -> None:
    """ffmpeg/ffprobe are needed by video, transcription and codec matching."""
    missing = [name for name in ("ffmpeg", "ffprobe") if shutil.which(name) is None]
    if missing:
        report.add(WARN, "Media tools", f"not on PATH: {', '.join(missing)}",
                   "video import, transcription and codec matching need these")
    else:
        report.add(OK, "Media tools", "ffmpeg and ffprobe present")


def check_backend_venv(report: Report) -> None:
    """A missing venv is why 'it worked yesterday' stops being true."""
    for candidate in (BACKEND / ".venv" / "bin" / "python",
                      BACKEND / ".venv" / "Scripts" / "python.exe"):
        if candidate.is_file():
            report.add(OK, "Backend venv", f"{candidate}")
            return
    report.add(FAIL, "Backend venv", f"no interpreter under {BACKEND / '.venv'}",
               "create it and install backend/requirements.txt")


# --------------------------------------------------------------------------

def run(models_dir: Path | None) -> Report:
    report = Report()
    env = read_env_file(BACKEND / ".env")
    if not (BACKEND / ".env").is_file():
        report.add(WARN, "backend/.env", "not present; repo defaults are in use",
                   "copy backend/.env.example to backend/.env")
    # Ordered the way a render depends on them.
    check_backend_venv(report)
    check_exposure(report, env)
    check_secrets_are_not_served(report, env)
    check_backups_are_not_served(report, env)
    check_comfyui(report, env)
    check_backend_and_frontend(report, env)
    check_workflows(report, env)
    check_models_dir(report, models_dir)
    check_storage(report, env)
    check_tools(report)
    return report


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only check of everything a render depends on.")
    parser.add_argument("--models-dir", type=Path, default=None,
                        help="ComfyUI models folder, to verify weights exist")
    parser.add_argument("--json", action="store_true",
                        help="machine-readable output")
    args = parser.parse_args(argv)

    report = run(args.models_dir)
    if args.json:
        print(json.dumps({"blocked": report.blocked, "checks": report.rows},
                         indent=2))
    else:
        report.print_human()
    return 1 if report.blocked else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
