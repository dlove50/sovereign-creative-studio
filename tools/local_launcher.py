"""Windows-safe local launcher for Sovereign Creative Studio.

PowerShell can fail when the inherited environment contains both PATH and Path.
This helper normalizes the environment before spawning services and avoids
PowerShell for health checks / port stops.

Commands
--------
  python tools/local_launcher.py start          Start all services
  python tools/local_launcher.py stop           Stop all services
  python tools/local_launcher.py status         Print full health/readiness report
  python tools/local_launcher.py clean          Rebuild frontend, restart
  python tools/local_launcher.py smoke          Fast smoke test (MVP routes + readiness)
  python tools/local_launcher.py smoke --full   Smoke test + Playwright browser test
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
COMFY_DIR = Path(r"C:\Users\David\ComfyUI-Installs\ComfyUI\ComfyUI")
COMFY_PY = Path(r"C:\Users\David\Documents\ComfyUI\.venv\Scripts\python.exe")
COMFY_MODELS = Path(r"C:\Users\David\AppData\Roaming\Comfy Desktop\shared_model_paths.yaml")
COMFY_USER = Path(r"C:\Users\David\Documents\ComfyUI\user")
COMFY_BASE = Path(r"C:\Users\David\Documents\ComfyUI")
COMFY_INPUT = Path(r"C:\Users\David\Documents\ComfyUI\input")
COMFY_OUTPUT = Path(r"C:\Users\David\Documents\ComfyUI\output")

SERVICES = {
    "comfyui": {
        "label": "ComfyUI",
        "port": 8001,
        "health": "http://127.0.0.1:8001/system_stats",
    },
    "backend": {
        "label": "Backend",
        "port": 8002,
        "health": "http://127.0.0.1:8002/api/generations/presets",
    },
    "frontend": {
        "label": "Frontend",
        "port": 3000,
        "health": "http://localhost:3000",
    },
}

APP_BACKEND_ENV_KEYS = {
    "COMFYUI_BASE_URL",
    "COMFYUI_PRODUCT_SCENE_MODE",
    "COMFYUI_PRODUCT_SCENE_WORKFLOW_PATH",
    "COMFYUI_VIDEO_ENGINE",
    "COMFYUI_VIDEO_MODEL_NAME",
    "COMFYUI_VIDEO_WORKFLOW_PATH",
    "COMFYUI_WAN_VIDEO_MODEL_NAME",
    "COMFYUI_WAN_VIDEO_WORKFLOW_PATH",
    "COPY_BACKEND",
    "GENERATOR_BACKEND",
    "PRODUCT_SCENE_BACKEND",
    "PRODUCT_SCENE_MODEL",
    "VIDEO_BACKEND",
}

BACKEND_PORT = 8002
OLLAMA_PORT = 11434


# ── Environment helpers ───────────────────────────────────────────────────────

def clean_env() -> dict[str, str]:
    env: dict[str, str] = {}
    path_value = None
    for key, value in os.environ.items():
        if key.lower() == "path":
            path_value = value if path_value is None else f"{path_value};{value}"
        else:
            env[key] = value
    if path_value is not None:
        env["Path"] = path_value
    return env


def backend_env() -> dict[str, str]:
    """Launch the app backend from backend/.env, not stale shell overrides."""
    env = clean_env()
    lower_keys = {key.lower() for key in APP_BACKEND_ENV_KEYS}
    for key in list(env):
        if key.lower() in lower_keys:
            env.pop(key, None)
    return env


# ── Network helpers ───────────────────────────────────────────────────────────

def http_ready(url: str, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 500
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _fetch_json(url: str, timeout: float = 5.0) -> dict | list | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception:  # noqa: BLE001
        return None


def _is_sovereign_backend() -> bool:
    """Return True only if port 8002 serves the Sovereign backend."""
    body = _fetch_json(f"http://127.0.0.1:{BACKEND_PORT}/api/generations/presets")
    return bool(body and "quality_presets" in body and "image_modes" in body)


def _check_proxy() -> bool:
    """Return True if the frontend proxy correctly forwards to backend port 8002."""
    body = _fetch_json("http://localhost:3000/api/generations/presets")
    return bool(body and "quality_presets" in body)


def port_pids(port: int) -> list[int]:
    output = subprocess.run(
        ["netstat", "-ano"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    pids: set[int] = set()
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        local = parts[1]
        state = parts[-2] if parts[0].upper() == "TCP" else ""
        pid = parts[-1]
        if local.endswith(f":{port}") and state.upper() == "LISTENING":
            try:
                pids.add(int(pid))
            except ValueError:
                pass
    return sorted(pids)


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def wait_url(label: str, url: str, attempts: int, delay: float = 2.0) -> bool:
    print(f"Waiting for {label} at {url}...")
    for _ in range(attempts):
        if http_ready(url):
            print(f"{label} is ready.")
            return True
        time.sleep(delay)
    print(f"[ERROR] {label} did not become ready at {url}.")
    return False


# ── Frontend process helpers ──────────────────────────────────────────────────

_FRONTEND_MARKER = str(FRONTEND).lower()


def _frontend_processes() -> list[dict]:
    script = (
        "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine } | "
        "Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            env=clean_env(),
            timeout=20,
            check=False,
        )
        data = json.loads(result.stdout) if result.stdout.strip() else []
    except Exception:  # noqa: BLE001
        return []
    if isinstance(data, dict):
        data = [data]
    procs: list[dict] = []
    for item in data:
        cmd = item.get("CommandLine") or ""
        name = (item.get("Name") or "").lower()
        if name in {"node.exe", "cmd.exe"} and _FRONTEND_MARKER in cmd.lower():
            procs.append({"pid": item.get("ProcessId"), "name": name, "cmd": cmd})
    return procs


def _frontend_dev_processes() -> list[dict]:
    dev: list[dict] = []
    for proc in _frontend_processes():
        low = proc["cmd"].lower().rstrip()
        if low.endswith(" dev") or "next dev" in low or "run dev" in low:
            dev.append(proc)
    return dev


def _project_pids_on(port: int) -> list[int]:
    project_pids = {p["pid"] for p in _frontend_processes()}
    return [pid for pid in port_pids(port) if pid in project_pids]


def _guard_no_dev() -> bool:
    dev = _frontend_dev_processes()
    project_3001 = _project_pids_on(3001)
    if not dev and not project_3001:
        return True
    print("")
    print("BLOCKED: next dev is running for Sovereign Creative Studio. Dev mode")
    print("corrupts the production .next build. Close the dev terminal or run")
    print("`python tools/local_launcher.py clean`.")
    for proc in dev:
        print(f"  dev PID {proc['pid']}: {proc['cmd'][:120]}")
    if project_3001:
        print(f"  project Next server on port 3001 (PID {project_3001[0]}); production runs only on 3000.")
    print("")
    return False


# ── Process spawning ──────────────────────────────────────────────────────────

def popen(
    command: list[str],
    cwd: Path,
    title: str,
    hidden: bool,
    env: dict[str, str] | None = None,
) -> subprocess.Popen | None:
    process_env = env or clean_env()
    if os.name == "nt":
        return subprocess.Popen(
            command,
            cwd=str(cwd),
            env=process_env,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
    flags = 0
    stdout = subprocess.DEVNULL if hidden else None
    stderr = subprocess.DEVNULL if hidden else None
    return subprocess.Popen(
        command,
        cwd=str(cwd),
        env=process_env,
        stdout=stdout,
        stderr=stderr,
        stdin=subprocess.DEVNULL,
        creationflags=flags,
    )


def _start_backend(backend_py: Path) -> None:
    pids = port_pids(BACKEND_PORT)
    if pids:
        print(f"  Evicting process(es) on port {BACKEND_PORT}: PIDs {pids}")
        for pid in pids:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True)
        time.sleep(1)
    print(f"[backend] Starting Sovereign backend on http://127.0.0.1:{BACKEND_PORT}")
    popen(
        [str(backend_py), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(BACKEND_PORT)],
        BACKEND,
        "Sovereign Backend",
        True,
        env=backend_env(),
    )


def ensure_paths(skip_comfy: bool) -> None:
    if not skip_comfy:
        if not (COMFY_DIR / "main.py").is_file():
            raise SystemExit(f"[ERROR] ComfyUI main.py not found: {COMFY_DIR / 'main.py'}")
        if not COMFY_PY.is_file():
            raise SystemExit(f"[ERROR] ComfyUI Python not found: {COMFY_PY}")
    backend_py = BACKEND / ".venv" / "Scripts" / "python.exe"
    if not backend_py.is_file():
        raise SystemExit(f"[ERROR] Backend Python venv not found: {backend_py}")
    if not (FRONTEND / "package.json").is_file():
        raise SystemExit(f"[ERROR] Frontend package.json not found: {FRONTEND / 'package.json'}")


def ensure_frontend_build() -> None:
    build_id = FRONTEND / ".next" / "BUILD_ID"
    if build_id.is_file():
        return
    print("Frontend production build not found. Building frontend once...")
    build_env = clean_env()
    # CRITICAL: always bake BACKEND_ORIGIN so the proxy points to port 8002,
    # not Next's default 8000. Running `npx next build` without this env var
    # bakes the wrong port into routes-manifest.json and causes 500 proxy errors.
    build_env["BACKEND_ORIGIN"] = f"http://127.0.0.1:{BACKEND_PORT}"
    result = subprocess.run(
        ["npm.cmd", "run", "build"],
        cwd=str(FRONTEND),
        env=build_env,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit("[ERROR] Frontend production build failed.")


# ── Status helpers ────────────────────────────────────────────────────────────

def _ok(label: str, ok: bool, note: str = "") -> None:
    mark = "✓" if ok else "✗"
    suffix = f"  {note}" if note else ""
    print(f"  {mark}  {label}{suffix}")


def _last_backup() -> str | None:
    backup_dir = ROOT.parent
    zips = sorted(backup_dir.glob("sovereign_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    return zips[0].name if zips else None


def _git_info() -> None:
    git = shutil.which("git")
    if not git:
        print("  git not found on PATH")
        return
    try:
        branch = subprocess.check_output(
            [git, "branch", "--show-current"], cwd=str(ROOT), text=True, timeout=5,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # noqa: BLE001
        print("  Not a git repository (run: git init && git commit)")
        return
    print(f"  Branch:  {branch or '(detached)'}")
    try:
        remote = subprocess.check_output(
            [git, "remote", "get-url", "origin"], cwd=str(ROOT), text=True, timeout=5,
            stderr=subprocess.DEVNULL,
        ).strip()
        print(f"  Remote:  {remote}")
    except Exception:  # noqa: BLE001
        print("  Remote:  (none — push to GitHub to enable restore on new machine)")
    try:
        porcelain = subprocess.check_output(
            [git, "status", "--porcelain"], cwd=str(ROOT), text=True, timeout=5,
            stderr=subprocess.DEVNULL,
        ).strip()
        if porcelain:
            print(f"  Changes: {len(porcelain.splitlines())} uncommitted file(s)")
        else:
            print("  Changes: working tree clean")
    except Exception:  # noqa: BLE001
        pass


# ── Commands ──────────────────────────────────────────────────────────────────

def start(args: argparse.Namespace) -> int:
    ensure_paths(args.skip_comfy)
    if not _guard_no_dev():
        return 1
    backend_py = BACKEND / ".venv" / "Scripts" / "python.exe"
    started: list[tuple[str, subprocess.Popen]] = []

    if not args.skip_comfy:
        if port_open(8001):
            print("ComfyUI already appears to be running on port 8001.")
        else:
            print("[1/3] Starting ComfyUI on http://127.0.0.1:8001")
            started.append((
                "ComfyUI",
                popen(
                    [
                        str(COMFY_PY), "-s", "main.py",
                        "--feature-flag", "show_signin_button=true",
                        "--base-directory", str(COMFY_BASE),
                        "--user-directory", str(COMFY_USER),
                        "--database-url", f"sqlite:///{COMFY_USER / 'comfyui.db'}",
                        "--port", "8001",
                        "--enable-manager",
                        "--extra-model-paths-config", str(COMFY_MODELS),
                        "--input-directory", str(COMFY_INPUT),
                        "--output-directory", str(COMFY_OUTPUT),
                    ],
                    COMFY_DIR, "ComfyUI - Sovereign Creative Studio", args.hidden,
                ),
            ))
        if not wait_url("ComfyUI", SERVICES["comfyui"]["health"], 90):
            return 1

    if _is_sovereign_backend():
        print(f"Backend already running on port {BACKEND_PORT}.")
    else:
        print(f"[2/3] Starting backend on http://127.0.0.1:{BACKEND_PORT}")
        _start_backend(backend_py)
    if not wait_url("Backend", SERVICES["backend"]["health"], 45):
        return 1

    if port_open(3000):
        print("Frontend already appears to be running on port 3000.")
    else:
        if args.frontend_dev:
            frontend_command = ["npm.cmd", "run", "dev"]
            frontend_label = "development"
        else:
            ensure_frontend_build()
            frontend_command = ["npm.cmd", "run", "start"]
            frontend_label = "production"
        print(f"[3/3] Starting frontend ({frontend_label}) on http://localhost:3000")
        frontend_env = clean_env()
        frontend_env["BACKEND_ORIGIN"] = f"http://127.0.0.1:{BACKEND_PORT}"
        started.append((
            "Frontend",
            popen(frontend_command, FRONTEND, "Sovereign Frontend", args.hidden, env=frontend_env),
        ))
    if not wait_url("Frontend", SERVICES["frontend"]["health"], 60):
        return 1

    print("")
    print("All services are ready.")
    print("  ComfyUI:  http://127.0.0.1:8001")
    print(f"  Backend:  http://127.0.0.1:{BACKEND_PORT}")
    print("  Frontend: http://localhost:3000")

    ollama_up = port_open(OLLAMA_PORT)
    if not ollama_up:
        print("")
        print("  WARNING: Ollama is not running on port 11434.")
        print("  Voice summaries (Qwen/qwen3:4b) will not work until Ollama is started.")
        print("  Start Ollama: run `ollama serve` in a terminal.")

    if args.open_browser:
        if not args.skip_comfy:
            webbrowser.open("http://127.0.0.1:8001")
        webbrowser.open("http://localhost:3000/status")
    return 0


def stop(_: argparse.Namespace) -> int:
    for key in ("frontend", "backend", "comfyui"):
        service = SERVICES[key]
        pids = port_pids(service["port"])
        if not pids:
            print(f"{service['label']}: no listener on port {service['port']}.")
            continue
        for pid in pids:
            print(f"{service['label']}: stopping PID {pid} on port {service['port']}.")
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False)
    return 0


def status(_: argparse.Namespace) -> int:
    print("")
    print("═══════════════════════════════════════════════════")
    print("  Sovereign Creative Studio — Status Report")
    print("═══════════════════════════════════════════════════")

    # 1. Services
    print("")
    print("── Services ────────────────────────────────────────")
    backend_up = http_ready(SERVICES["backend"]["health"])
    frontend_up = http_ready(SERVICES["frontend"]["health"])
    comfyui_up = http_ready(SERVICES["comfyui"]["health"])
    ollama_up = port_open(OLLAMA_PORT)
    backend_pids = port_pids(BACKEND_PORT)
    frontend_pids = port_pids(3000)

    _ok("Backend  (port 8002)", backend_up,
        f"PIDs {backend_pids}" if backend_up else "not running — start with: python tools/local_launcher.py start")
    _ok("Frontend (port 3000)", frontend_up,
        f"PIDs {frontend_pids}" if frontend_up else "not running")
    _ok("ComfyUI  (port 8001)", comfyui_up,
        "running" if comfyui_up else "not running — image/video generation unavailable")
    _ok("Ollama   (port 11434)", ollama_up,
        "running" if ollama_up else "not running — summaries unavailable; run: ollama serve")

    # 2. Components (requires backend)
    print("")
    print("── Components ──────────────────────────────────────")
    if backend_up:
        audio = _fetch_json(f"http://127.0.0.1:{BACKEND_PORT}/api/audio-merge/readiness")
        if audio:
            _ok("Piper TTS", audio.get("piper", False),
                audio.get("piper_detail", "see docs/MODEL_AND_DEPENDENCY_MANIFEST.md"))
            _ok("FFmpeg", audio.get("ffmpeg", False),
                "required for voice narration" if audio.get("ffmpeg") else "install from https://ffmpeg.org/")
            _ok("Audio merge", audio.get("ready", False), audio.get("detail", ""))
        else:
            print("  ! Could not reach audio-merge readiness endpoint")

        presets = _fetch_json(f"http://127.0.0.1:{BACKEND_PORT}/api/generations/presets")
        if presets:
            for p in presets.get("quality_presets", []):
                if p["id"] == "krea2_turbo_fp8":
                    _ok("Krea 2 Turbo FP8", p["ready"],
                        "recommended for Quick Chain" if p["ready"] else "model file not found in ComfyUI")
                elif p["id"] == "flux1_krea":
                    _ok("FLUX.1 Krea Dev", p["ready"],
                        "fallback image model" if p["ready"] else "model file not found")
        else:
            print("  ! Could not reach presets endpoint")

        modes = _fetch_json(f"http://127.0.0.1:{BACKEND_PORT}/api/videos/modes")
        if modes:
            for m in modes:
                if m["id"] == "video_upscale":
                    note = "" if m["available"] else (m.get("note") or "ComfyUI unavailable")
                    _ok("Video upscale", m["available"], note)
                    break
        else:
            print("  ! Could not reach video modes endpoint")
    else:
        print("  (backend offline — skipping component checks)")

    # 3. Proxy
    print("")
    print("── Proxy ───────────────────────────────────────────")
    if frontend_up and backend_up:
        proxy_ok = _check_proxy()
        _ok("Frontend proxy → backend 8002", proxy_ok,
            "OK — /api routes forwarded correctly" if proxy_ok else
            "WRONG — rebuild with: python tools/local_launcher.py clean")
    elif not frontend_up:
        print("  (frontend offline — proxy not checked)")
    else:
        print("  (backend offline — proxy not checked)")

    # 4. Git
    print("")
    print("── Git ─────────────────────────────────────────────")
    _git_info()

    # 5. Last backup
    print("")
    print("── Backups ─────────────────────────────────────────")
    last = _last_backup()
    if last:
        print(f"  Last backup: {last}")
    else:
        print("  No backups found in parent directory.")

    print("")
    return 0


def clean(args: argparse.Namespace) -> int:
    """Stop project Next processes, clear ports 3000/3001, rebuild, start production."""
    print("Stopping project-owned frontend Next processes...")
    for proc in _frontend_processes():
        print(f"  killing PID {proc['pid']} ({proc['name']})")
        subprocess.run(
            ["taskkill", "/PID", str(proc["pid"]), "/T", "/F"],
            env=clean_env(), check=False, capture_output=True,
        )
    for port in (3000, 3001):
        for pid in port_pids(port):
            print(f"  clearing port {port}: PID {pid}")
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                env=clean_env(), check=False, capture_output=True,
            )
    time.sleep(2)
    for port in (3000, 3001):
        print(f"  port {port}: {'still in use' if port_open(port) else 'clear'}")
    if port_open(3000) or port_open(3001):
        print("[ERROR] Could not clear ports 3000/3001; aborting.")
        return 1

    next_dir = FRONTEND / ".next"
    if next_dir.exists():
        print("Deleting frontend/.next ...")
        shutil.rmtree(next_dir, ignore_errors=True)
    dev_dir = FRONTEND / ".next-dev"
    if dev_dir.exists():
        print("Deleting frontend/.next-dev ...")
        shutil.rmtree(dev_dir, ignore_errors=True)

    backend_py = BACKEND / ".venv" / "Scripts" / "python.exe"
    if _is_sovereign_backend():
        print(f"Backend already running on port {BACKEND_PORT}.")
    else:
        _start_backend(backend_py)
        if not wait_url("Backend", SERVICES["backend"]["health"], 30):
            print("[ERROR] Backend did not start. Frontend may show 'Loading…' for model data.")

    print("Rebuilding production .next (npm run build)...")
    build_env = clean_env()
    build_env["BACKEND_ORIGIN"] = f"http://127.0.0.1:{BACKEND_PORT}"
    if subprocess.run(["npm.cmd", "run", "build"], cwd=str(FRONTEND), env=build_env, check=False).returncode != 0:
        print("[ERROR] Frontend production build failed.")
        return 1
    if not (next_dir / "BUILD_ID").is_file():
        print("[ERROR] .next/BUILD_ID missing after build.")
        return 1

    print("Starting production frontend (npm run start) on http://localhost:3000")
    frontend_env = clean_env()
    frontend_env["BACKEND_ORIGIN"] = f"http://127.0.0.1:{BACKEND_PORT}"
    popen(["npm.cmd", "run", "start"], FRONTEND, "Sovereign Frontend", args.hidden, env=frontend_env)
    if not wait_url("Frontend", SERVICES["frontend"]["health"], 60):
        return 1
    print("Frontend is ready on http://localhost:3000.")
    return 0


def smoke(args: argparse.Namespace) -> int:
    """Fast smoke test to verify the MVP is working end-to-end."""
    passed: list[str] = []
    failed: list[str] = []

    def check(label: str, ok: bool, note: str = "") -> None:
        mark = "PASS" if ok else "FAIL"
        suffix = f"  ({note})" if note else ""
        print(f"  [{mark}]  {label}{suffix}")
        (passed if ok else failed).append(label)

    print("")
    print("═══════════════════════════════════════════════════")
    print("  Sovereign Creative Studio — Smoke Test")
    print("═══════════════════════════════════════════════════")
    print("")

    # 1. Backend health
    backend_up = _is_sovereign_backend()
    check("Backend health", backend_up, "http://127.0.0.1:8002")

    # 2. Frontend health
    frontend_up = http_ready(SERVICES["frontend"]["health"])
    check("Frontend health", frontend_up, "http://localhost:3000")

    # 3. Proxy (only meaningful if both are up)
    if frontend_up and backend_up:
        proxy_ok = _check_proxy()
        check("Frontend proxy → backend 8002", proxy_ok,
              "rebuild if FAIL: python tools/local_launcher.py clean")
    else:
        print("  [SKIP]  Frontend proxy (services offline)")

    # 4. Krea 2 preset ready
    presets = _fetch_json(f"http://127.0.0.1:{BACKEND_PORT}/api/generations/presets") if backend_up else None
    krea2_ready = any(
        p["id"] == "krea2_turbo_fp8" and p["ready"]
        for p in (presets or {}).get("quality_presets", [])
    )
    check("Krea 2 Turbo FP8 image preset", krea2_ready,
          "required for Quick Chain — see docs/MODEL_AND_DEPENDENCY_MANIFEST.md if FAIL")

    # 5. Audio merge (Piper + FFmpeg)
    audio = _fetch_json(f"http://127.0.0.1:{BACKEND_PORT}/api/audio-merge/readiness") if backend_up else None
    audio_ok = bool(audio and audio.get("ready"))
    check("Audio merge (Piper + FFmpeg)", audio_ok,
          "required for voice narration")

    # 6. Ollama (for summaries)
    ollama_up = port_open(OLLAMA_PORT)
    check("Ollama (summaries)", ollama_up,
          "optional — summaries unavailable if offline; run: ollama serve")

    # 7. Route checks
    print("")
    print("  Route checks:")
    routes = ["/create", "/videos", "/video-to-text", "/assets-library", "/chain", "/status"]
    for route in routes:
        ok = http_ready(f"http://localhost:3000{route}") if frontend_up else False
        check(f"  {route}", ok)

    # Summary
    total = len(passed) + len(failed)
    print("")
    if not failed:
        print(f"  RESULT:  PASS — {len(passed)}/{total} checks passed.")
    else:
        print(f"  RESULT:  FAIL — {len(passed)}/{total} passed, {len(failed)} failed:")
        for f in failed:
            print(f"           ✗ {f}")
    print("")

    # 8. Optional: full Playwright test
    if args.full:
        print("── Full Playwright Test ────────────────────────────────")
        if not ollama_up:
            print("  WARNING: Ollama is not running. The Summarize step will fail.")
            print("           Run `ollama serve` and warm qwen3:4b before --full.")
        npx = shutil.which("npx") or "npx"
        result = subprocess.run(
            [npx, "playwright", "test", "e2e/quick-chain.spec.ts", "--reporter=line"],
            cwd=str(FRONTEND),
            env=clean_env(),
            check=False,
        )
        playwright_ok = result.returncode == 0
        if playwright_ok:
            print("  Playwright: PASS")
        else:
            print("  Playwright: FAIL")
            return 1

    return 0 if not failed else 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Sovereign Creative Studio local launcher",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start", help="Start all services")
    p_start.add_argument("--skip-comfy", action="store_true")
    p_start.add_argument("--hidden", action="store_true")
    p_start.add_argument("--open-browser", action="store_true")
    p_start.add_argument("--frontend-dev", action="store_true",
                         help="Use Next.js dev server instead of production.")
    p_start.set_defaults(func=start)

    p_stop = sub.add_parser("stop", help="Stop all project services")
    p_stop.set_defaults(func=stop)

    p_status = sub.add_parser("status", help="Full health and readiness report")
    p_status.set_defaults(func=status)

    p_clean = sub.add_parser("clean",
                              help="Stop Next processes, rebuild frontend, restart production.")
    p_clean.add_argument("--hidden", action="store_true")
    p_clean.set_defaults(func=clean)

    p_smoke = sub.add_parser("smoke", help="Fast smoke test for MVP readiness")
    p_smoke.add_argument("--full", action="store_true",
                         help="Also run Playwright browser tests (needs Ollama warm for summary step).")
    p_smoke.set_defaults(func=smoke)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
